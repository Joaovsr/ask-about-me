import asyncio

from ask_about_me.case_studies import CaseStudyProjector, PostgresCaseStudyCatalog
from ask_about_me.composition import build_openai_knowledge_base
from ask_about_me.config import Settings, get_settings
from ask_about_me.db import Database


async def reindex_published_case_studies(settings: Settings) -> int:
    if settings.openai_api_key is None:
        raise RuntimeError("AAM_OPENAI_API_KEY is required for OpenAI reindexing")

    database = Database(settings.database_url)
    knowledge_base = build_openai_knowledge_base(settings, database)
    catalog = PostgresCaseStudyCatalog(database=database)
    projector = CaseStudyProjector()

    try:
        # Read the guard first so any publication overlapping the snapshot makes staging stale.
        active_generation = await knowledge_base.get_active_generation_id()
        case_studies = await catalog.list_current()
        if not case_studies:
            raise RuntimeError("no published Case Studies are available to reindex")
        candidate = await knowledge_base.prepare_index(
            tuple(projector.project(case_study) for case_study in case_studies),
        )
        await knowledge_base.stage_prepared_sources(
            candidate,
            expected_active_generation=active_generation,
        )
        smoke_results = await knowledge_base.search_generation(
            case_studies[0].title_pt_br,
            (),
            generation_id=candidate.id,
        )
        if case_studies[0].id not in {result.source_id for result in smoke_results}:
            raise RuntimeError(
                "OpenAI reindexing smoke retrieval did not find the indexed source"
            )
        await knowledge_base.activate_staged_generation(
            candidate.id,
            expected_active_generation=active_generation,
        )
    finally:
        await database.close()

    return len(case_studies)


async def _main() -> None:
    settings = get_settings()
    indexed_count = await reindex_published_case_studies(settings)
    print(
        f"Reindexed {indexed_count} published Case Study source(s) with "
        f"{settings.embedding_model}/{settings.embedding_dimensions}. "
        "Smoke retrieval passed."
    )


if __name__ == "__main__":
    asyncio.run(_main())
