import asyncio

from ask_about_me.case_studies import CaseStudyProjector, PostgresCaseStudyCatalog
from ask_about_me.composition import build_openai_knowledge_base
from ask_about_me.config import Settings, get_settings
from ask_about_me.db import Database
from ask_about_me.portfolio_content import (
    PortfolioContentNotFoundError,
    PortfolioContentProjector,
    PostgresPortfolioContentCatalog,
)


async def reindex_published_content(settings: Settings) -> int:
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
        documents = [
            case_study_projector.project(case_study) for case_study in case_studies
        ]
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
        smoke_results = await knowledge_base.search_generation(
            documents[0].title,
            (),
            generation_id=candidate.id,
        )
        if documents[0].source_id not in {result.source_id for result in smoke_results}:
            raise RuntimeError(
                "OpenAI reindexing smoke retrieval did not find the indexed source"
            )
        await knowledge_base.activate_staged_generation(
            candidate.id,
            expected_active_generation=active_generation,
        )
    finally:
        await database.close()

    return len(documents)


async def _main() -> None:
    settings = get_settings()
    indexed_count = await reindex_published_content(settings)
    print(
        f"Reindexed {indexed_count} published content source(s) with "
        f"{settings.embedding_model}/{settings.embedding_dimensions}. "
        "Smoke retrieval passed."
    )


if __name__ == "__main__":
    asyncio.run(_main())
