import asyncio
from pathlib import Path
from uuid import UUID

from ask_about_me.rag import (
    CalibratedEvidenceSupportEvaluator,
    ConversationMessage,
    DocumentType,
    RetrievalSignals,
    RetrievedChunk,
)
from ask_about_me.retrieval_evaluation import (
    GoldenCase,
    RelevantSource,
    _recall,
    evaluate_retrieval,
    load_golden_dataset,
)


def chunk(
    *,
    chunk_id: str,
    slug: str,
    section: str,
    vector_rank: int | None,
    text_rank: int | None,
    rrf_score: float,
) -> RetrievedChunk:
    return RetrievedChunk(
        id=UUID(chunk_id),
        document_id=UUID("72c78f20-52b8-4b0d-a29b-04b8adba2219"),
        source_id=UUID("7580bd75-32e6-49c7-854d-e70737823b43"),
        source_revision=1,
        source_slug=slug,
        document_type=DocumentType.PROFILE,
        title="Portal do Candidato",
        section=section,
        excerpt="Evidência publicada.",
        source_url=f"/projects/{slug}",
        signals=RetrievalSignals(
            vector_distance=0.2 if vector_rank is not None else None,
            vector_similarity=0.8 if vector_rank is not None else None,
            vector_rank=vector_rank,
            text_rank_cd=0.4 if text_rank is not None else None,
            text_rank=text_rank,
            title_match=text_rank == 1,
            section_match=False,
            rrf_score=rrf_score,
        ),
    )


class FixedSearcher:
    def __init__(
        self,
        *,
        vector_similarity: float = 0.8,
        title_match: bool = True,
    ) -> None:
        self.vector_similarity = vector_similarity
        self.title_match = title_match
        self.requested_candidate_limit: int | None = None

    async def search_for_evaluation(
        self,
        question: str,
        history: tuple[ConversationMessage, ...],
        *,
        generation_id: UUID | None,
        candidate_limit: int,
    ) -> tuple[RetrievedChunk, ...]:
        del question, history, generation_id
        self.requested_candidate_limit = candidate_limit
        chunks = (
            chunk(
                chunk_id="1b3d640f-9f4c-4894-aad2-9740f50a1647",
                slug="irrelevante",
                section="Resumo",
                vector_rank=1,
                text_rank=None,
                rrf_score=1 / 61,
            ),
            chunk(
                chunk_id="d8fa2461-da11-46f9-ab8c-ff54921c2d46",
                slug="candidate_portal",
                section="Resultado",
                vector_rank=2,
                text_rank=1,
                rrf_score=(1 / 62) + (1 / 61),
            ),
        )
        return tuple(
            RetrievedChunk(
                id=item.id,
                document_id=item.document_id,
                source_id=item.source_id,
                source_revision=item.source_revision,
                source_slug=item.source_slug,
                document_type=item.document_type,
                title=item.title,
                section=item.section,
                excerpt=item.excerpt,
                source_url=item.source_url,
                signals=RetrievalSignals(
                    vector_distance=1 - self.vector_similarity,
                    vector_similarity=self.vector_similarity,
                    vector_rank=item.signals.vector_rank,
                    text_rank_cd=item.signals.text_rank_cd,
                    text_rank=item.signals.text_rank,
                    title_match=item.signals.title_match and self.title_match,
                    section_match=item.signals.section_match,
                    rrf_score=item.signals.rrf_score,
                ),
            )
            for item in chunks
        )


class DuplicateRelevantSearcher:
    async def search_for_evaluation(
        self,
        question: str,
        history: tuple[ConversationMessage, ...],
        *,
        generation_id: UUID | None,
        candidate_limit: int,
    ) -> tuple[RetrievedChunk, ...]:
        del question, history, generation_id, candidate_limit
        return (
            chunk(
                chunk_id="d8fa2461-da11-46f9-ab8c-ff54921c2d46",
                slug="candidate_portal",
                section="Resultado",
                vector_rank=1,
                text_rank=1,
                rrf_score=2 / 61,
            ),
            chunk(
                chunk_id="445b13a2-2423-49a8-8378-b419943cf7ca",
                slug="candidate_portal",
                section="Resumo",
                vector_rank=2,
                text_rank=2,
                rrf_score=2 / 62,
            ),
        )


def test_evaluator_reports_retrieval_and_support_metrics_without_generation() -> None:
    cases = (
        GoldenCase(
            schema_version=1,
            id="supported-title",
            split="holdout",
            locale="pt-BR",
            question="Portal do Candidato",
            history=(),
            expected_support="supported",
            relevant_sources=(
                RelevantSource(
                    slug="candidate_portal",
                    sections=("Resultado",),
                    relevance=3,
                ),
            ),
            tags=("product-title",),
        ),
    )

    searcher = FixedSearcher()
    report = asyncio.run(evaluate_retrieval(searcher=searcher, cases=cases))

    assert report.case_count == 1
    assert searcher.requested_candidate_limit == 32
    assert report.channels["hybrid"].recall_at[1] == 0.0
    assert report.channels["hybrid"].recall_at[3] == 1.0
    assert report.channels["hybrid"].mrr == 0.5
    assert report.channels["text"].recall_at[1] == 1.0
    assert report.gate.supported_precision == 1.0
    assert report.gate.supported_recall == 1.0
    assert report.generation_calls == 0


def test_evaluator_does_not_count_duplicate_chunks_as_repeated_ndcg_gain() -> None:
    case = GoldenCase(
        schema_version=1,
        id="one-source",
        split="holdout",
        locale="pt-BR",
        question="Portal do Candidato",
        history=(),
        expected_support="supported",
        relevant_sources=(
            RelevantSource(
                slug="candidate_portal",
                sections=(),
                relevance=3,
            ),
        ),
        tags=(),
    )

    report = asyncio.run(evaluate_retrieval(searcher=DuplicateRelevantSearcher(), cases=(case,)))

    assert report.channels["hybrid"].ndcg_at_5 == 1.0


def test_recall_handles_document_and_section_qrels_without_exceeding_one() -> None:
    case = GoldenCase(
        schema_version=1,
        id="mixed-qrels",
        split="holdout",
        locale="pt-BR",
        question="Quais projetos usaram Power BI?",
        history=(),
        expected_support="supported",
        relevant_sources=(
            RelevantSource(
                slug="candidate_portal",
                sections=("Resultado",),
                relevance=3,
            ),
            RelevantSource(slug="atalaia", sections=(), relevance=2),
        ),
        tags=(),
    )
    chunks = (
        chunk(
            chunk_id="d8fa2461-da11-46f9-ab8c-ff54921c2d46",
            slug="candidate_portal",
            section="Resultado",
            vector_rank=1,
            text_rank=1,
            rrf_score=2 / 61,
        ),
        chunk(
            chunk_id="445b13a2-2423-49a8-8378-b419943cf7ca",
            slug="atalaia",
            section="Experiência",
            vector_rank=2,
            text_rank=2,
            rrf_score=2 / 62,
        ),
    )

    assert _recall(case, chunks) == 1.0


def test_evaluator_requires_supported_recall_to_pass() -> None:
    case = GoldenCase(
        schema_version=1,
        id="non-critical-false-rejection",
        split="holdout",
        locale="pt-BR",
        question="Portal do Candidato",
        history=(),
        expected_support="supported",
        relevant_sources=(
            RelevantSource(
                slug="candidate_portal",
                sections=("Resultado",),
                relevance=3,
            ),
        ),
        tags=(),
    )

    report = asyncio.run(
        evaluate_retrieval(
            searcher=FixedSearcher(vector_similarity=0.2, title_match=False),
            cases=(case,),
            support_evaluator=CalibratedEvidenceSupportEvaluator(
                minimum_vector_similarity=0.9,
                minimum_text_rank_cd=0.5,
            ),
        )
    )

    assert report.gate.supported_recall == 0.0
    assert report.passed is False


def test_versioned_golden_dataset_covers_calibration_holdout_and_critical_cases() -> None:
    cases = load_golden_dataset(Path("evals/retrieval/golden.jsonl"))

    assert len(cases) >= 20
    assert {case.split for case in cases} == {"calibration", "holdout"}
    assert {
        "pt-audit-president",
        "pt-audit-power-bi",
        "pt-audit-candidate-portal",
        "pt-audit-people-platform",
    } <= {case.id for case in cases}
    assert any(case.locale == "en-US" for case in cases)
    assert any("follow-up" in case.tags for case in cases)
    assert any("semantic-hard-negative" in case.tags for case in cases)
