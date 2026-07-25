import asyncio
from uuid import UUID

import pytest
from sqlalchemy import create_engine, text

from ask_about_me.case_studies import CaseStudyPublisher, PostgresCaseStudyCatalog
from ask_about_me.db import Database
from ask_about_me.initial_content import INITIAL_CASE_STUDY
from ask_about_me.knowledge_base import (
    IndexProfileMismatchError,
    PostgresKnowledgeBase,
    ProjectedKbDocument,
    ProjectedSection,
    SectionChunker,
)
from ask_about_me.providers import LocalHashEmbeddingProvider
from ask_about_me.rag import DocumentType
from ask_about_me.seed import seed_initial_content

CASE_STUDY_ID = UUID("28e81ec7-57e5-4d4d-ad79-064cb9aab3e2")


def test_seeded_case_study_projects_from_portuguese_and_is_searchable(
    test_database_url: str,
) -> None:
    engine = create_engine(test_database_url)
    database = Database(test_database_url)
    catalog = PostgresCaseStudyCatalog(database=database)
    knowledge_base = PostgresKnowledgeBase(
        database=database,
        embedding_provider=LocalHashEmbeddingProvider(),
        result_limit=1,
    )
    try:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM kb_index_generations"))
            connection.execute(text("DELETE FROM case_studies"))

        created = asyncio.run(
            seed_initial_content(database=database, knowledge_base=knowledge_base)
        )
        created_again = asyncio.run(
            seed_initial_content(database=database, knowledge_base=knowledge_base)
        )
        case_study = asyncio.run(catalog.get_current("plataforma-gestao-pessoas-ia"))
        listed_case_studies = asyncio.run(catalog.list_current())
        results = asyncio.run(
            knowledge_base.search_my_work(
                "Como funciona o scoring semântico de currículos?",
                (),
            )
        )
    finally:
        asyncio.run(database.close())
        engine.dispose()

    assert case_study.id == CASE_STUDY_ID
    assert listed_case_studies == (case_study,)
    assert created is True
    assert created_again is False
    assert case_study.revision == 1
    assert case_study.title_pt_br == "Plataforma de Gestão de Pessoas com IA"
    assert case_study.title_en_us == "AI-Powered People Management Platform"
    assert [section.heading_pt_br for section in case_study.sections] == [
        "Contexto",
        "Problema",
        "Solução",
        "Resultado",
    ]
    assert all(section.heading_en_us and section.body_en_us for section in case_study.sections)

    assert results
    assert {result.source_id for result in results} == {CASE_STUDY_ID}
    assert {result.source_revision for result in results} == {1}
    assert {result.document_type for result in results} == {DocumentType.CASE_STUDY}
    assert {result.source_url for result in results} == {
        "/case-studies/plataforma-gestao-pessoas-ia?locale=pt-BR&version=1"
    }
    assert results[0].section == "Contexto"
    assert results[0].excerpt == (
        "Sistema corporativo de recrutamento com pipeline Kanban, SLA automático e scoring "
        "semântico de currículos usando Azure OpenAI + pgvector."
    )


def test_publishing_a_case_study_preserves_other_kb_doc_types(
    test_database_url: str,
) -> None:
    engine = create_engine(test_database_url)
    database = Database(test_database_url)
    knowledge_base = PostgresKnowledgeBase(
        database=database,
        embedding_provider=LocalHashEmbeddingProvider(),
    )
    publisher = CaseStudyPublisher(database=database, knowledge_base=knowledge_base)
    profile = ProjectedKbDocument(
        source_id=UUID("e00c8822-95ab-46f1-83a0-bb407212837a"),
        source_revision=1,
        doc_type=DocumentType.PROFILE,
        title="Perfil técnico",
        slug="perfil-tecnico",
        source_url="/profile?locale=pt-BR&version=1",
        sections=(
            ProjectedSection(
                name="Resumo",
                text="Experiência com scoring semântico e engenharia de software.",
            ),
        ),
    )

    try:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM kb_index_generations"))
            connection.execute(text("DELETE FROM case_studies"))

        first_generation = asyncio.run(
            knowledge_base.replace_index(
                (profile,),
                expected_active_generation=None,
            )
        )
        asyncio.run(
            publisher.publish(
                INITIAL_CASE_STUDY,
                expected_current_revision=None,
                expected_active_generation=first_generation,
            )
        )
        results = asyncio.run(knowledge_base.search_my_work("scoring semântico", ()))
    finally:
        asyncio.run(database.close())
        engine.dispose()

    assert {result.title for result in results} == {
        "Plataforma de Gestão de Pessoas com IA",
        "Perfil técnico",
    }


def test_publishing_rejects_copying_sources_from_an_incompatible_index(
    test_database_url: str,
) -> None:
    engine = create_engine(test_database_url)
    database = Database(test_database_url)
    embedding_provider = LocalHashEmbeddingProvider()
    original_knowledge_base = PostgresKnowledgeBase(
        database=database,
        embedding_provider=embedding_provider,
        chunker=SectionChunker(max_characters=80),
    )
    publishing_knowledge_base = PostgresKnowledgeBase(
        database=database,
        embedding_provider=embedding_provider,
    )
    publisher = CaseStudyPublisher(
        database=database,
        knowledge_base=publishing_knowledge_base,
    )
    profile = ProjectedKbDocument(
        source_id=UUID("6b303558-c532-476d-823a-a7eaadce2b5c"),
        source_revision=1,
        doc_type=DocumentType.PROFILE,
        title="Perfil técnico",
        slug="perfil-tecnico",
        source_url="/profile?locale=pt-BR&version=1",
        sections=(
            ProjectedSection(
                name="Resumo",
                text="Experiência com sistemas de recrutamento.",
            ),
        ),
    )

    try:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM kb_index_generations"))
            connection.execute(text("DELETE FROM case_studies"))

        active_generation = asyncio.run(
            original_knowledge_base.replace_index(
                (profile,),
                expected_active_generation=None,
            )
        )
        with pytest.raises(IndexProfileMismatchError):
            asyncio.run(
                publisher.publish(
                    INITIAL_CASE_STUDY,
                    expected_current_revision=None,
                    expected_active_generation=active_generation,
                )
            )
        results = asyncio.run(
            original_knowledge_base.search_my_work("recrutamento", ())
        )
    finally:
        asyncio.run(database.close())
        engine.dispose()

    assert {result.title for result in results} == {"Perfil técnico"}
