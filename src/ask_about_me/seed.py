import asyncio

from ask_about_me.case_studies import (
    CaseStudyIdentityConflictError,
    CaseStudyNotFoundError,
    CaseStudyPublisher,
    PostgresCaseStudyCatalog,
)
from ask_about_me.config import get_settings
from ask_about_me.db import Database
from ask_about_me.initial_content import INITIAL_CASE_STUDY
from ask_about_me.knowledge_base import PostgresKnowledgeBase
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


async def _main() -> None:
    settings = get_settings()
    database = Database(settings.database_url)
    knowledge_base = PostgresKnowledgeBase(
        database=database,
        embedding_provider=LocalHashEmbeddingProvider(),
    )
    try:
        created = await seed_initial_content(
            database=database,
            knowledge_base=knowledge_base,
        )
    finally:
        await database.close()

    status = "published" if created else "already published"
    print(f"Development seed {status} with local hash embeddings.")


if __name__ == "__main__":
    asyncio.run(_main())
