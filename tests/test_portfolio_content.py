import asyncio
from dataclasses import replace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from ask_about_me.app import create_app
from ask_about_me.config import Settings
from ask_about_me.db import Database
from ask_about_me.initial_portfolio_content import INITIAL_PORTFOLIO_CONTENT
from ask_about_me.knowledge_base import PostgresKnowledgeBase
from ask_about_me.portfolio_content import (
    LocalizedPortfolioContent,
    PostgresPortfolioContentCatalog,
    PublishedPortfolioSnapshot,
    _validate_snapshot,
)
from ask_about_me.providers import LocalHashEmbeddingProvider
from ask_about_me.seed import seed_initial_portfolio_content


class RecordingPortfolioContent:
    async def get_current(self) -> PublishedPortfolioSnapshot:
        return INITIAL_PORTFOLIO_CONTENT

    async def get_revision(self, revision: int) -> PublishedPortfolioSnapshot:
        assert revision == 1
        return INITIAL_PORTFOLIO_CONTENT


def test_public_portfolio_content_returns_the_requested_locale() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://unused:unused@localhost/unused",
        openai_api_key=None,
    )
    with TestClient(
        create_app(settings, portfolio_content_reader=RecordingPortfolioContent())
    ) as client:
        response = client.get("/portfolio?locale=en-US")

    assert response.status_code == 200
    payload = response.json()
    assert payload["revision"] == 1
    assert payload["locale"] == "en-US"
    assert payload["profile"]["location"] == "Barbacena, MG — Brazil"
    assert payload["experiences"][0]["role"] == "Full Stack Developer | AI Engineer"
    assert payload["projects"][2]["title"] == "AI-Powered People Management Platform"
    assert response.headers["etag"] == '"portfolio-1-en-US"'


def test_public_portfolio_content_reads_a_specific_revision() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://unused:unused@localhost/unused",
        openai_api_key=None,
    )
    with TestClient(
        create_app(settings, portfolio_content_reader=RecordingPortfolioContent())
    ) as client:
        response = client.get("/portfolio?locale=pt-BR&version=1")

    assert response.status_code == 200
    assert response.json()["revision"] == 1


def test_portfolio_snapshot_rejects_an_incomplete_locale() -> None:
    profile_without_tagline = dict(INITIAL_PORTFOLIO_CONTENT.en_us.profile)
    profile_without_tagline.pop("tagline")
    incomplete = replace(
        INITIAL_PORTFOLIO_CONTENT,
        en_us=LocalizedPortfolioContent(
            profile=profile_without_tagline,
            experiences=INITIAL_PORTFOLIO_CONTENT.en_us.experiences,
            projects=INITIAL_PORTFOLIO_CONTENT.en_us.projects,
        ),
    )

    try:
        _validate_snapshot(incomplete, expected_current_revision=None)
    except ValueError as error:
        assert "tagline" in str(error)
    else:
        raise AssertionError("expected incomplete localized content to be rejected")


def test_portfolio_seed_is_idempotent_and_indexes_profile_docs(test_database_url: str) -> None:
    engine = create_engine(test_database_url)
    database = Database(test_database_url)
    knowledge_base = PostgresKnowledgeBase(
        database=database,
        embedding_provider=LocalHashEmbeddingProvider(),
    )
    catalog = PostgresPortfolioContentCatalog(database=database)
    try:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM kb_index_generations"))
            connection.execute(text("DELETE FROM portfolio_content_snapshots"))

        created = asyncio.run(
            seed_initial_portfolio_content(database=database, knowledge_base=knowledge_base)
        )
        created_again = asyncio.run(
            seed_initial_portfolio_content(database=database, knowledge_base=knowledge_base)
        )
        snapshot = asyncio.run(catalog.get_current())
        results = asyncio.run(knowledge_base.search_my_work("Power BI", ()))
    finally:
        asyncio.run(database.close())
        engine.dispose()

    assert created is True
    assert created_again is False
    assert snapshot == INITIAL_PORTFOLIO_CONTENT
    assert {result.document_type.value for result in results} == {"profile"}
    assert any(result.title == "Fictor360 — Power BI Embedded" for result in results)
