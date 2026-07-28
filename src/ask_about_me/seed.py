import asyncio

from ask_about_me.case_studies import (
    CaseStudyIdentityConflictError,
    CaseStudyNotFoundError,
    CaseStudyPublisher,
    PostgresCaseStudyCatalog,
)
from ask_about_me.composition import build_openai_knowledge_base
from ask_about_me.config import get_settings
from ask_about_me.db import Database
from ask_about_me.initial_content import INITIAL_CASE_STUDY
from ask_about_me.initial_portfolio_content import INITIAL_PORTFOLIO_CONTENT
from ask_about_me.knowledge_base import PostgresKnowledgeBase
from ask_about_me.portfolio_content import (
    PortfolioContentNotFoundError,
    PortfolioContentPublisher,
    PostgresPortfolioContentCatalog,
)
from ask_about_me.providers import LocalHashEmbeddingProvider


async def seed_initial_content(
    *,
    database: Database,
    knowledge_base: PostgresKnowledgeBase,
) -> bool:
    catalog = PostgresCaseStudyCatalog(database=database)
    active_generation = await knowledge_base.get_active_generation_id()
    try:
        current = await catalog.get_current(INITIAL_CASE_STUDY.slug)
    except CaseStudyNotFoundError:
        current = None

    if current is not None:
        if current.id != INITIAL_CASE_STUDY.id:
            raise CaseStudyIdentityConflictError(INITIAL_CASE_STUDY.slug)
        if active_generation is None:
            raise RuntimeError("published seed exists without an active KB generation")
        return False

    publisher = CaseStudyPublisher(database=database, knowledge_base=knowledge_base)
    await publisher.publish(
        INITIAL_CASE_STUDY,
        expected_current_revision=None,
        expected_active_generation=active_generation,
    )
    return True


async def seed_initial_portfolio_content(
    *,
    database: Database,
    knowledge_base: PostgresKnowledgeBase,
) -> bool:
    catalog = PostgresPortfolioContentCatalog(database=database)
    try:
        await catalog.get_current()
    except PortfolioContentNotFoundError:
        current = None
    else:
        current = True

    if current is not None:
        return False

    publisher = PortfolioContentPublisher(database=database, knowledge_base=knowledge_base)
    await publisher.publish(
        INITIAL_PORTFOLIO_CONTENT,
        expected_current_revision=None,
        expected_active_generation=await knowledge_base.get_active_generation_id(),
    )
    return True


async def _main() -> None:
    settings = get_settings()
    database = Database(settings.database_url)
    knowledge_base = PostgresKnowledgeBase(
        database=database,
        embedding_provider=LocalHashEmbeddingProvider(),
    )
    active_profile = await knowledge_base.get_active_index_profile()
    if active_profile is not None and active_profile.embedding.provider != "local-hash":
        if settings.openai_api_key is None:
            raise RuntimeError(
                "the active Knowledge Base uses OpenAI embeddings; "
                "AAM_OPENAI_API_KEY is required to seed new content"
            )
        knowledge_base = build_openai_knowledge_base(settings, database)
    try:
        case_study_created = await seed_initial_content(
            database=database,
            knowledge_base=knowledge_base,
        )
        portfolio_created = await seed_initial_portfolio_content(
            database=database,
            knowledge_base=knowledge_base,
        )
    finally:
        await database.close()

    case_study_status = "published" if case_study_created else "already published"
    portfolio_status = "published" if portfolio_created else "already published"
    print(
        "Development seed with local hash embeddings: "
        f"Case Study {case_study_status}; portfolio content {portfolio_status}."
    )


if __name__ == "__main__":
    asyncio.run(_main())
