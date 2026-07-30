import argparse
import asyncio
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from math import log2
from pathlib import Path
from typing import Protocol
from uuid import UUID

from ask_about_me.rag import (
    CALIBRATED_RETRIEVAL_PROFILE,
    CalibratedEvidenceSupportEvaluator,
    ConversationMessage,
    ConversationRole,
    DeterministicRetrievalQueryBuilder,
    EvidenceSupportEvaluator,
    RetrievedChunk,
)

SCHEMA_VERSION = 1
DEFAULT_GOLDEN_DATASET = Path("evals/retrieval/golden.jsonl")
RANKING_CUTOFFS = (1, 3, 5, 8)
EVALUATION_CANDIDATE_LIMIT = 32
GENERATION_RESULT_LIMIT = 8


@dataclass(frozen=True, slots=True)
class RelevantSource:
    slug: str
    sections: tuple[str, ...]
    relevance: int


@dataclass(frozen=True, slots=True)
class GoldenCase:
    schema_version: int
    id: str
    split: str
    locale: str
    question: str
    history: tuple[ConversationMessage, ...]
    expected_support: str
    relevant_sources: tuple[RelevantSource, ...]
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ChannelMetrics:
    recall_at: Mapping[int, float]
    mrr: float
    ndcg_at_5: float


@dataclass(frozen=True, slots=True)
class GateMetrics:
    supported_precision: float
    supported_recall: float
    false_acceptances: int
    false_rejections: int


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    schema_version: int
    case_count: int
    channels: Mapping[str, ChannelMetrics]
    gate: GateMetrics
    generation_calls: int
    passed: bool
    critical_failures: tuple[str, ...]


class RetrievalSearcher(Protocol):
    async def search_for_evaluation(
        self,
        question: str,
        history: tuple[ConversationMessage, ...],
        *,
        generation_id: UUID | None,
        candidate_limit: int,
    ) -> tuple[RetrievedChunk, ...]: ...


def load_golden_dataset(path: Path = DEFAULT_GOLDEN_DATASET) -> tuple[GoldenCase, ...]:
    cases: list[GoldenCase] = []
    case_ids: set[str] = set()
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}:{line_number}: invalid JSON") from error
        case = _parse_case(payload, path=path, line_number=line_number)
        if case.id in case_ids:
            raise ValueError(f"{path}:{line_number}: duplicate case id {case.id!r}")
        case_ids.add(case.id)
        cases.append(case)
    if not cases:
        raise ValueError(f"{path}: Golden Dataset must contain at least one case")
    return tuple(cases)


def _parse_case(payload: object, *, path: Path, line_number: int) -> GoldenCase:
    if not isinstance(payload, dict):
        raise ValueError(f"{path}:{line_number}: each case must be an object")
    try:
        schema_version = int(payload["schemaVersion"])
        history_payload = payload.get("history", [])
        relevant_payload = payload.get("relevantSources", [])
        history = tuple(
            ConversationMessage(
                role=ConversationRole(message["role"]),
                content=str(message["content"]).strip(),
            )
            for message in history_payload
        )
        relevant_sources = tuple(
            RelevantSource(
                slug=str(source["slug"]),
                sections=tuple(str(section) for section in source.get("sections", [])),
                relevance=int(source["relevance"]),
            )
            for source in relevant_payload
        )
        case = GoldenCase(
            schema_version=schema_version,
            id=str(payload["id"]),
            split=str(payload["split"]),
            locale=str(payload["locale"]),
            question=str(payload["question"]),
            history=history,
            expected_support=str(payload["expectedSupport"]),
            relevant_sources=relevant_sources,
            tags=tuple(str(tag) for tag in payload.get("tags", [])),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{path}:{line_number}: invalid Golden Dataset case") from error
    if case.schema_version != SCHEMA_VERSION:
        raise ValueError(f"{path}:{line_number}: unsupported schemaVersion {case.schema_version}")
    if case.split not in {"calibration", "holdout"}:
        raise ValueError(f"{path}:{line_number}: split must be calibration or holdout")
    if case.locale not in {"pt-BR", "en-US"}:
        raise ValueError(f"{path}:{line_number}: unsupported locale")
    if case.expected_support not in {"supported", "partial", "unsupported"}:
        raise ValueError(f"{path}:{line_number}: invalid expectedSupport")
    if any(not message.content for message in case.history):
        raise ValueError(f"{path}:{line_number}: history messages must not be empty")
    if any(source.relevance not in {1, 2, 3} for source in case.relevant_sources):
        raise ValueError(f"{path}:{line_number}: relevance must be 1, 2, or 3")
    return case


async def evaluate_retrieval(
    *,
    searcher: RetrievalSearcher,
    cases: Sequence[GoldenCase],
    support_evaluator: EvidenceSupportEvaluator | None = None,
    generation_id: UUID | None = None,
) -> EvaluationReport:
    evaluator = support_evaluator or CalibratedEvidenceSupportEvaluator()
    query_builder = DeterministicRetrievalQueryBuilder()
    channel_rankings: dict[str, list[tuple[GoldenCase, tuple[RetrievedChunk, ...]]]] = {
        "vector": [],
        "text": [],
        "hybrid": [],
    }
    true_positives = false_positives = false_negatives = 0
    critical_failures: list[str] = []
    for case in cases:
        chunks = await searcher.search_for_evaluation(
            case.question,
            case.history,
            generation_id=generation_id,
            candidate_limit=EVALUATION_CANDIDATE_LIMIT,
        )
        channel_rankings["hybrid"].append((case, chunks))
        channel_rankings["vector"].append(
            (
                case,
                tuple(
                    sorted(
                        (chunk for chunk in chunks if chunk.signals.vector_rank is not None),
                        key=lambda chunk: (chunk.signals.vector_rank or 0, chunk.id),
                    )
                ),
            )
        )
        channel_rankings["text"].append(
            (
                case,
                tuple(
                    sorted(
                        (chunk for chunk in chunks if chunk.signals.text_rank is not None),
                        key=lambda chunk: (chunk.signals.text_rank or 0, chunk.id),
                    )
                ),
            )
        )
        retrieval_query = query_builder.build(case.question, case.history)
        gate_chunks = chunks[:GENERATION_RESULT_LIMIT]
        retrieval_profile = (
            gate_chunks[0].signals.retrieval_profile
            if gate_chunks
            else CALIBRATED_RETRIEVAL_PROFILE
        )
        decision = evaluator.evaluate(
            question=case.question,
            retrieval_query=retrieval_query,
            chunks=gate_chunks,
            retrieval_profile=retrieval_profile,
        )
        expected_supported = case.expected_support in {"supported", "partial"}
        if decision.supported and expected_supported:
            true_positives += 1
        elif decision.supported:
            false_positives += 1
        elif expected_supported:
            false_negatives += 1
        if "critical" in case.tags and (
            decision.supported != expected_supported
            or (case.relevant_sources and _recall(case, chunks[:5]) == 0.0)
        ):
            critical_failures.append(case.id)

    precision_denominator = true_positives + false_positives
    recall_denominator = true_positives + false_negatives
    gate_precision = true_positives / precision_denominator if precision_denominator else 1.0
    gate_recall = true_positives / recall_denominator if recall_denominator else 1.0
    channels = {
        channel: _channel_metrics(rankings) for channel, rankings in channel_rankings.items()
    }
    passed = (
        channels["hybrid"].recall_at[5] >= 0.95
        and gate_precision >= 0.95
        and gate_recall >= 0.95
        and false_positives == 0
        and not critical_failures
    )
    return EvaluationReport(
        schema_version=SCHEMA_VERSION,
        case_count=len(cases),
        channels=channels,
        gate=GateMetrics(
            supported_precision=gate_precision,
            supported_recall=gate_recall,
            false_acceptances=false_positives,
            false_rejections=false_negatives,
        ),
        generation_calls=0,
        passed=passed,
        critical_failures=tuple(critical_failures),
    )


def _channel_metrics(
    rankings: Iterable[tuple[GoldenCase, tuple[RetrievedChunk, ...]]],
) -> ChannelMetrics:
    eligible = [(case, chunks) for case, chunks in rankings if case.relevant_sources]
    if not eligible:
        return ChannelMetrics(
            recall_at={cutoff: 1.0 for cutoff in RANKING_CUTOFFS},
            mrr=1.0,
            ndcg_at_5=1.0,
        )
    recall_at = {
        cutoff: sum(_recall(case, chunks[:cutoff]) for case, chunks in eligible) / len(eligible)
        for cutoff in RANKING_CUTOFFS
    }
    reciprocal_ranks = [_reciprocal_rank(case, chunks) for case, chunks in eligible]
    ndcgs = [_ndcg(case, chunks[:5]) for case, chunks in eligible]
    return ChannelMetrics(
        recall_at=recall_at,
        mrr=sum(reciprocal_ranks) / len(reciprocal_ranks),
        ndcg_at_5=sum(ndcgs) / len(ndcgs),
    )


def _relevant_source(case: GoldenCase, chunk: RetrievedChunk) -> RelevantSource | None:
    for source in case.relevant_sources:
        section_matches = not source.sections or chunk.section in source.sections
        if chunk.source_slug == source.slug and section_matches:
            return source
    return None


def _recall(case: GoldenCase, chunks: Sequence[RetrievedChunk]) -> float:
    expected = {
        (source.slug, section)
        for source in case.relevant_sources
        for section in (source.sections or ("",))
    }
    found: set[tuple[str, str]] = set()
    for chunk in chunks:
        source = _relevant_source(case, chunk)
        if source is None:
            continue
        if source.sections:
            found.add((source.slug, chunk.section))
        else:
            found.add((source.slug, ""))
    return len(found) / len(expected)


def _reciprocal_rank(case: GoldenCase, chunks: Sequence[RetrievedChunk]) -> float:
    for rank, chunk in enumerate(chunks, start=1):
        if _relevant_source(case, chunk) is not None:
            return 1 / rank
    return 0.0


def _ndcg(case: GoldenCase, chunks: Sequence[RetrievedChunk]) -> float:
    seen_relevance_units: set[tuple[str, str]] = set()
    gains: list[int] = []
    for chunk in chunks:
        source = _relevant_source(case, chunk)
        if source is None:
            gains.append(0)
            continue
        relevance_unit = (
            source.slug,
            chunk.section if source.sections else "",
        )
        if relevance_unit in seen_relevance_units:
            gains.append(0)
            continue
        seen_relevance_units.add(relevance_unit)
        gains.append(source.relevance)
    dcg = sum((2**gain - 1) / log2(rank + 1) for rank, gain in enumerate(gains, start=1))
    ideal_gains = sorted(
        (source.relevance for source in case.relevant_sources for _ in (source.sections or ("",))),
        reverse=True,
    )[: len(chunks)]
    ideal = sum((2**gain - 1) / log2(rank + 1) for rank, gain in enumerate(ideal_gains, start=1))
    return dcg / ideal if ideal else 0.0


def report_as_json(report: EvaluationReport) -> str:
    return json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True)


async def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate KB retrieval without invoking answer generation."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_GOLDEN_DATASET)
    parser.add_argument("--split", choices=("calibration", "holdout", "all"), default="all")
    parser.add_argument(
        "--generation",
        type=UUID,
        help="Evaluate a staged generation instead of the active generation.",
    )
    arguments = parser.parse_args()
    from ask_about_me.config import get_settings
    from ask_about_me.inspect_retrieval import build_retrieval_inspector

    cases = load_golden_dataset(arguments.dataset)
    if arguments.split != "all":
        cases = tuple(case for case in cases if case.split == arguments.split)
    searcher = await build_retrieval_inspector(get_settings())
    try:
        report = await evaluate_retrieval(
            searcher=searcher.knowledge_base,
            cases=cases,
            generation_id=arguments.generation,
        )
    finally:
        await searcher.close()
    print(report_as_json(report))


if __name__ == "__main__":
    asyncio.run(_main())
