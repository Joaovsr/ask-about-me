import argparse
import asyncio
from dataclasses import dataclass
from uuid import UUID

from ask_about_me.case_studies import CaseStudyProjector, PostgresCaseStudyCatalog
from ask_about_me.composition import build_openai_knowledge_base
from ask_about_me.config import Settings, get_settings
from ask_about_me.db import Database
from ask_about_me.portfolio_content import (
    PortfolioContentNotFoundError,
    PortfolioContentProjector,
    PostgresPortfolioContentCatalog,
)
from ask_about_me.retrieval_evaluation import (
    DEFAULT_GOLDEN_DATASET,
    evaluate_retrieval,
    load_golden_dataset,
)


@dataclass(frozen=True, slots=True)
class StagedReindex:
    generation_id: UUID
    expected_active_generation: UUID | None
    document_count: int


async def stage_published_content(settings: Settings) -> StagedReindex:
    if settings.openai_api_key is None:
        raise RuntimeError("AAM_OPENAI_API_KEY is required for OpenAI reindexing")

    database = Database(settings.database_url)
    knowledge_base = build_openai_knowledge_base(settings, database)
    catalog = PostgresCaseStudyCatalog(database=database)
    case_study_projector = CaseStudyProjector()
    portfolio_catalog = PostgresPortfolioContentCatalog(database=database)
    portfolio_projector = PortfolioContentProjector()

    try:
        # Read the guard first so any publication overlapping the snapshot makes staging stale.
        active_generation = await knowledge_base.get_active_generation_id()
        case_studies = await catalog.list_current()
        documents = [case_study_projector.project(case_study) for case_study in case_studies]
        try:
            portfolio_snapshot = await portfolio_catalog.get_current()
        except PortfolioContentNotFoundError:
            portfolio_snapshot = None
        if portfolio_snapshot is not None:
            documents.extend(portfolio_projector.project(portfolio_snapshot))
        if not documents:
            raise RuntimeError("no published content is available to reindex")
        candidate = await knowledge_base.prepare_index(tuple(documents))
        await knowledge_base.stage_prepared_sources(
            candidate,
            expected_active_generation=active_generation,
        )
        return StagedReindex(
            generation_id=candidate.id,
            expected_active_generation=active_generation,
            document_count=len(documents),
        )
    finally:
        await database.close()


async def validate_and_activate_generation(
    settings: Settings,
    *,
    generation_id: UUID,
    expected_active_generation: UUID | None,
) -> None:
    if settings.openai_api_key is None:
        raise RuntimeError("AAM_OPENAI_API_KEY is required for OpenAI reindexing")
    database = Database(settings.database_url)
    knowledge_base = build_openai_knowledge_base(settings, database)
    try:
        holdout = tuple(
            case for case in load_golden_dataset(DEFAULT_GOLDEN_DATASET) if case.split == "holdout"
        )
        report = await evaluate_retrieval(
            searcher=knowledge_base,
            cases=holdout,
            generation_id=generation_id,
        )
        if not report.passed:
            raise RuntimeError(
                "candidate KB generation failed the Golden Dataset gates: "
                f"Recall@5={report.channels['hybrid'].recall_at[5]:.3f}, "
                f"supported precision={report.gate.supported_precision:.3f}, "
                f"false acceptances={report.gate.false_acceptances}, "
                f"critical failures={','.join(report.critical_failures) or 'none'}"
            )
        await knowledge_base.activate_staged_generation(
            generation_id,
            expected_active_generation=expected_active_generation,
        )
    finally:
        await database.close()


async def reindex_published_content(settings: Settings) -> int:
    staged = await stage_published_content(settings)
    await validate_and_activate_generation(
        settings,
        generation_id=staged.generation_id,
        expected_active_generation=staged.expected_active_generation,
    )
    return staged.document_count


async def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage, evaluate, and atomically activate an OpenAI KB generation."
    )
    parser.add_argument(
        "--stage-only",
        action="store_true",
        help="Build a candidate but leave the active generation unchanged.",
    )
    parser.add_argument("--activate", type=UUID, metavar="GENERATION_ID")
    parser.add_argument("--expected-active", type=UUID, metavar="GENERATION_ID")
    arguments = parser.parse_args()
    settings = get_settings()
    if arguments.activate is not None:
        await validate_and_activate_generation(
            settings,
            generation_id=arguments.activate,
            expected_active_generation=arguments.expected_active,
        )
        print(f"Activated KB generation {arguments.activate} after Golden Dataset validation.")
        return
    if arguments.stage_only:
        staged = await stage_published_content(settings)
        print(
            f"Staged KB generation {staged.generation_id} with "
            f"{staged.document_count} source(s); expected active generation: "
            f"{staged.expected_active_generation or 'none'}."
        )
        return
    indexed_count = await reindex_published_content(settings)
    print(
        f"Reindexed {indexed_count} published content source(s) with "
        f"{settings.embedding_model}/{settings.embedding_dimensions}. "
        "Golden Dataset holdout passed."
    )


if __name__ == "__main__":
    asyncio.run(_main())
