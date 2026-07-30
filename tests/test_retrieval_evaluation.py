import asyncio
from pathlib import Path
from uuid import UUID

from ask_about_me.rag import DocumentType, RetrievalSignals, RetrievedChunk
from ask_about_me.retrieval_evaluation import (
    GoldenCase,
    RelevantSource,
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
    async def search_my_work(
        self, question: str, history: tuple[object, ...]
    ) -> tuple[RetrievedChunk, ...]:
        del question, history
        return (
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

    report = asyncio.run(evaluate_retrieval(searcher=FixedSearcher(), cases=cases))

    assert report.case_count == 1
    assert report.channels["hybrid"].recall_at[1] == 0.0
    assert report.channels["hybrid"].recall_at[3] == 1.0
    assert report.channels["hybrid"].mrr == 0.5
    assert report.channels["text"].recall_at[1] == 1.0
    assert report.gate.supported_precision == 1.0
    assert report.gate.supported_recall == 1.0
    assert report.generation_calls == 0


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
