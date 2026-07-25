import asyncio
from uuid import UUID

import pytest
from sqlalchemy import create_engine, text

from ask_about_me.db import Database
from ask_about_me.knowledge_base import (
    ChunkDraft,
    EmbeddingProfile,
    PostgresKnowledgeBase,
    ProjectedKbDocument,
    ProjectedSection,
    SectionChunker,
    StaleIndexGenerationError,
    TokenSectionChunker,
)
from ask_about_me.rag import ConversationMessage, ConversationRole, DocumentType

EXPECTED_CHUNK_ID = UUID("98e30019-a72a-4b72-b21f-3ed73f44234f")
VECTOR_ONLY_CHUNK_ID = UUID("94a314f6-6c27-4a6f-a6eb-d330e140edbd")


def test_token_section_chunker_preserves_semantic_boundaries_and_limits_chunks() -> None:
    chunker = TokenSectionChunker(
        model="text-embedding-3-small",
        target_tokens=12,
        max_tokens=18,
        overlap_tokens=4,
    )
    document = ProjectedKbDocument(
        source_id=UUID("b5615981-9272-47fc-9064-81523c99796d"),
        source_revision=1,
        doc_type=DocumentType.CASE_STUDY,
        title="Plataforma de recrutamento",
        slug="plataforma-recrutamento",
        source_url="/case-studies/plataforma-recrutamento",
        sections=(
            ProjectedSection(
                name="Resultado",
                text=(
                    "O processo manual demorava várias horas. "
                    "A busca semântica reduziu esse tempo.\n\n"
                    "A equipe também passou a acompanhar o SLA automaticamente. "
                    "Os gestores receberam indicadores por etapa."
                ),
            ),
        ),
    )

    chunks = chunker.chunk(document)

    assert len(chunks) >= 2
    assert all(chunk.section == "Resultado" for chunk in chunks)
    assert all(chunker.count_tokens(chunk.content) <= 18 for chunk in chunks)
    assert chunks[0].content.endswith((".", "!", "?"))
    assert chunks[-1].content.endswith((".", "!", "?"))


def test_token_section_chunker_preserves_internal_paragraph_whitespace() -> None:
    chunker = TokenSectionChunker(
        model="text-embedding-3-small",
        target_tokens=100,
        max_tokens=120,
        overlap_tokens=10,
    )
    source_text = (
        "O processo manual demorava várias horas.\n\n"
        "A busca semântica reduziu esse tempo."
    )
    document = ProjectedKbDocument(
        source_id=UUID("ee40266e-dd1e-486e-a941-ed3a7b66386c"),
        source_revision=1,
        doc_type=DocumentType.CASE_STUDY,
        title="Plataforma de recrutamento",
        slug="plataforma-recrutamento",
        source_url="/case-studies/plataforma-recrutamento",
        sections=(ProjectedSection(name="Resultado", text=source_text),),
    )

    chunks = chunker.chunk(document)

    assert chunks == (
        ChunkDraft(
            position=0,
            section="Resultado",
            content=source_text,
        ),
    )


class FixedEmbeddingProvider:
    @property
    def profile(self) -> EmbeddingProfile:
        return EmbeddingProfile(provider="test", model="fixed", dimensions=3)

    async def embed_query(self, text: str) -> tuple[float, ...]:
        return (1.0, 0.0, 0.0)

    async def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return tuple((1.0, 0.0, 0.0) for _ in texts)


class KeywordEmbeddingProvider:
    def __init__(self) -> None:
        self.fail_document_embeddings = False

    @property
    def profile(self) -> EmbeddingProfile:
        return EmbeddingProfile(provider="test", model="keyword", dimensions=3)

    async def embed_query(self, text: str) -> tuple[float, ...]:
        return self._embedding_for(text)

    async def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if self.fail_document_embeddings:
            raise RuntimeError("embedding provider unavailable")
        return tuple(self._embedding_for(text) for text in texts)

    @staticmethod
    def _embedding_for(text: str) -> tuple[float, ...]:
        if "pagamentos" in text.casefold():
            return (0.0, 1.0, 0.0)
        return (1.0, 0.0, 0.0)


class RecordingEmbeddingProvider:
    def __init__(self) -> None:
        self.document_inputs: tuple[str, ...] = ()

    @property
    def profile(self) -> EmbeddingProfile:
        return EmbeddingProfile(provider="test", model="recording", dimensions=3)

    async def embed_query(self, text: str) -> tuple[float, ...]:
        return (1.0, 0.0, 0.0)

    async def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        self.document_inputs = texts
        return tuple((1.0, 0.0, 0.0) for _ in texts)


def test_prepare_index_embeds_document_context_with_each_raw_chunk() -> None:
    database = Database(
        "postgresql+psycopg://ask_about_me:ask_about_me@127.0.0.1:1/not-used"
    )
    provider = RecordingEmbeddingProvider()
    knowledge_base = PostgresKnowledgeBase(
        database=database,
        embedding_provider=provider,
        chunker=TokenSectionChunker(
            target_tokens=350,
            max_tokens=500,
            overlap_tokens=50,
        ),
    )
    document = ProjectedKbDocument(
        source_id=UUID("b44b6f80-437a-4cc4-8acc-d8ac1ce5c9ad"),
        source_revision=1,
        doc_type=DocumentType.CASE_STUDY,
        title="Plataforma de recrutamento",
        slug="plataforma-recrutamento",
        source_url="/case-studies/plataforma-recrutamento",
        sections=(
            ProjectedSection(
                name="Resultado",
                text="O scoring passou de horas para milissegundos.",
            ),
        ),
    )

    try:
        asyncio.run(knowledge_base.prepare_index((document,)))
    finally:
        asyncio.run(database.close())

    assert provider.document_inputs == (
        "Tipo de documento: case_study\n"
        "Título: Plataforma de recrutamento\n"
        "Seção: Resultado\n"
        "Conteúdo: O scoring passou de horas para milissegundos.",
    )


def test_search_my_work_combines_vector_and_portuguese_full_text_search(
    test_database_url: str,
) -> None:
    engine = create_engine(test_database_url)
    database = Database(test_database_url)

    try:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM kb_documents"))
            connection.execute(text("DELETE FROM kb_index_generations"))
            connection.execute(
                text(
                    """
                    INSERT INTO kb_index_generations (
                        id,
                        is_active,
                        embedding_provider,
                        embedding_model,
                        embedding_dimensions,
                        chunker_version,
                        canonical_locale
                    )
                    VALUES (
                        'd737467e-7c27-46f8-9347-3c6265530475',
                        TRUE,
                        'test',
                        'fixed',
                        3,
                        'manual-test',
                        'pt-BR'
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO kb_documents (
                        id, source_id, source_revision, index_generation, doc_type,
                        title, slug, source_url, canonical_text
                    ) VALUES
                        (
                            '3ba42f3e-280b-4d40-885f-9cc04aa0e228',
                            'b3f5f421-3314-48d8-b9cc-02cb458890e5',
                            2,
                            'd737467e-7c27-46f8-9347-3c6265530475',
                            'case_study',
                            'Plataforma de recrutamento',
                            'plataforma-recrutamento',
                            '/case-studies/plataforma-recrutamento?locale=pt-BR&version=2',
                            'A plataforma automatizou o recrutamento com busca semântica.'
                        ),
                        (
                            '2631068d-3e0c-4a05-a947-928ba70fa600',
                            '4674e40d-255b-4720-a3a5-85284a84cf5b',
                            1,
                            'd737467e-7c27-46f8-9347-3c6265530475',
                            'profile',
                            'Perfil técnico',
                            'perfil-tecnico',
                            '/profile?locale=pt-BR&version=1',
                            'Experiência geral com desenvolvimento de software.'
                        )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO kb_chunks (
                        id, document_id, position, section, content, embedding
                    ) VALUES
                        (
                            :expected_chunk_id,
                            '3ba42f3e-280b-4d40-885f-9cc04aa0e228',
                            0,
                            'Implementação',
                            'A plataforma automatizou o recrutamento com busca semântica.',
                            '[0.9,0.1,0]'::vector
                        ),
                        (
                            :vector_only_chunk_id,
                            '2631068d-3e0c-4a05-a947-928ba70fa600',
                            0,
                            'Resumo',
                            'Experiência geral com desenvolvimento de software.',
                            '[1,0,0]'::vector
                        )
                    """
                ),
                {
                    "expected_chunk_id": EXPECTED_CHUNK_ID,
                    "vector_only_chunk_id": VECTOR_ONLY_CHUNK_ID,
                },
            )

        knowledge_base = PostgresKnowledgeBase(
            database=database,
            embedding_provider=FixedEmbeddingProvider(),
            result_limit=2,
        )
        results = asyncio.run(
            knowledge_base.search_my_work(
                "E qual foi o resultado?",
                (
                    ConversationMessage(
                        role=ConversationRole.USER,
                        content="Como a plataforma automatizou o recrutamento?",
                    ),
                ),
            )
        )
    finally:
        asyncio.run(database.close())
        engine.dispose()

    assert [result.id for result in results] == [
        EXPECTED_CHUNK_ID,
        VECTOR_ONLY_CHUNK_ID,
    ]
    assert results[0].title == "Plataforma de recrutamento"
    assert results[0].document_type == "case_study"
    assert results[0].excerpt == ("A plataforma automatizou o recrutamento com busca semântica.")
    assert results[0].score > results[1].score


def test_replace_index_switches_the_searchable_generation_atomically(
    test_database_url: str,
) -> None:
    engine = create_engine(test_database_url)
    database = Database(test_database_url)
    embedding_provider = KeywordEmbeddingProvider()
    knowledge_base = PostgresKnowledgeBase(
        database=database,
        embedding_provider=embedding_provider,
        chunker=SectionChunker(max_characters=80),
        result_limit=8,
    )
    old_source_id = UUID("fc4d8722-f0cb-41bf-bb73-d647332323ad")
    new_source_id = UUID("8a498b39-bc53-48e0-ae30-4a1d4024f5eb")

    try:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM kb_index_generations"))

        first_generation = asyncio.run(
            knowledge_base.replace_index(
                (
                    ProjectedKbDocument(
                        source_id=old_source_id,
                        source_revision=1,
                        doc_type=DocumentType.CASE_STUDY,
                        title="Automação de recrutamento",
                        slug="automacao-recrutamento",
                        source_url="/case-studies/automacao-recrutamento?version=1",
                        sections=(
                            ProjectedSection(
                                name="Implementação",
                                text=(
                                    "Automatizei o recrutamento com busca semântica. "
                                    "A solução reduziu o trabalho manual da equipe."
                                ),
                            ),
                        ),
                    ),
                ),
                expected_active_generation=None,
            )
        )
        first_results = asyncio.run(knowledge_base.search_my_work("recrutamento", ()))

        second_generation = asyncio.run(
            knowledge_base.replace_index(
                (
                    ProjectedKbDocument(
                        source_id=new_source_id,
                        source_revision=3,
                        doc_type=DocumentType.PROFILE,
                        title="Sistemas de pagamentos",
                        slug="sistemas-pagamentos",
                        source_url="/profile/sistemas-pagamentos?version=3",
                        sections=(
                            ProjectedSection(
                                name="Experiência",
                                text=(
                                    "Construí sistemas de pagamentos resilientes.\n"
                                    "Mantive  observabilidade."
                                ),
                            ),
                        ),
                    ),
                ),
                expected_active_generation=first_generation,
            )
        )
        second_results = asyncio.run(knowledge_base.search_my_work("pagamentos", ()))
        active_profile = asyncio.run(knowledge_base.get_active_embedding_profile())

        with pytest.raises(StaleIndexGenerationError):
            asyncio.run(
                knowledge_base.replace_index(
                    (
                        ProjectedKbDocument(
                            source_id=UUID("38ca0e93-4822-4f13-bf53-c01f99d98383"),
                            source_revision=1,
                            doc_type=DocumentType.ESSAY,
                            title="Geração obsoleta",
                            slug="geracao-obsoleta",
                            source_url="/essays/geracao-obsoleta?version=1",
                            sections=(
                                ProjectedSection(
                                    name="Tese",
                                    text="Observabilidade deve orientar decisões técnicas.",
                                ),
                            ),
                        ),
                    ),
                    expected_active_generation=first_generation,
                )
            )
        results_after_stale_write = asyncio.run(knowledge_base.search_my_work("pagamentos", ()))
    finally:
        asyncio.run(database.close())
        engine.dispose()

    assert first_generation != second_generation
    assert active_profile == embedding_provider.profile
    assert {result.document_id for result in first_results}
    assert {result.title for result in first_results} == {"Automação de recrutamento"}
    assert {result.title for result in second_results} == {"Sistemas de pagamentos"}
    assert {result.source_id for result in second_results} == {new_source_id}
    assert {result.title for result in results_after_stale_write} == {"Sistemas de pagamentos"}
    assert {result.excerpt for result in second_results} == {
        "Construí sistemas de pagamentos resilientes.\nMantive  observabilidade."
    }
    assert len(first_results) == 2


def test_replace_index_keeps_previous_generation_when_embedding_fails(
    test_database_url: str,
) -> None:
    engine = create_engine(test_database_url)
    database = Database(test_database_url)
    embedding_provider = KeywordEmbeddingProvider()
    knowledge_base = PostgresKnowledgeBase(
        database=database,
        embedding_provider=embedding_provider,
    )

    try:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM kb_index_generations"))

        active_generation = asyncio.run(
            knowledge_base.replace_index(
                (
                    ProjectedKbDocument(
                        source_id=UUID("de80b73e-7dc0-459d-9744-e106befa5fc6"),
                        source_revision=1,
                        doc_type=DocumentType.CASE_STUDY,
                        title="Plataforma anterior",
                        slug="plataforma-anterior",
                        source_url="/case-studies/plataforma-anterior?version=1",
                        sections=(
                            ProjectedSection(
                                name="Resultado",
                                text="Automatizei o recrutamento técnico.",
                            ),
                        ),
                    ),
                ),
                expected_active_generation=None,
            )
        )
        embedding_provider.fail_document_embeddings = True

        with pytest.raises(RuntimeError, match="embedding provider unavailable"):
            asyncio.run(
                knowledge_base.replace_index(
                    (
                        ProjectedKbDocument(
                            source_id=UUID("f89aa47c-09c0-4c54-a045-296d7ed2559e"),
                            source_revision=1,
                            doc_type=DocumentType.PROFILE,
                            title="Nova plataforma",
                            slug="nova-plataforma",
                            source_url="/profile/nova-plataforma?version=1",
                            sections=(
                                ProjectedSection(
                                    name="Experiência",
                                    text="Trabalhei em sistemas de pagamentos.",
                                ),
                            ),
                        ),
                    ),
                    expected_active_generation=active_generation,
                )
            )

        results = asyncio.run(knowledge_base.search_my_work("recrutamento", ()))
    finally:
        asyncio.run(database.close())
        engine.dispose()

    assert {result.title for result in results} == {"Plataforma anterior"}


def test_staged_generation_is_searchable_before_atomic_activation(
    test_database_url: str,
) -> None:
    engine = create_engine(test_database_url)
    database = Database(test_database_url)
    knowledge_base = PostgresKnowledgeBase(
        database=database,
        embedding_provider=FixedEmbeddingProvider(),
        chunker=SectionChunker(max_characters=80),
    )

    def document(source_id: UUID, title: str) -> ProjectedKbDocument:
        slug = title.casefold().replace(" ", "-")
        return ProjectedKbDocument(
            source_id=source_id,
            source_revision=1,
            doc_type=DocumentType.CASE_STUDY,
            title=title,
            slug=slug,
            source_url=f"/case-studies/{slug}",
            sections=(
                ProjectedSection(
                    name="Implementação",
                    text=f"{title} contém evidência publicada para o teste.",
                ),
            ),
        )

    try:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM kb_index_generations"))

        previous_generation = asyncio.run(
            knowledge_base.replace_index(
                (
                    document(
                        UUID("9a78db5a-0247-40bd-a7e4-75e95817508a"),
                        "Índice anterior",
                    ),
                ),
                expected_active_generation=None,
            )
        )
        candidate = asyncio.run(
            knowledge_base.prepare_index(
                (
                    document(
                        UUID("fe10a5e5-728e-4c5b-bd37-2f498702771d"),
                        "Índice candidato",
                    ),
                ),
            )
        )
        asyncio.run(
            knowledge_base.stage_prepared_sources(
                candidate,
                expected_active_generation=previous_generation,
            )
        )
        active_before_smoke = asyncio.run(knowledge_base.get_active_generation_id())
        smoke_results = asyncio.run(
            knowledge_base.search_generation(
                "candidato",
                (),
                generation_id=candidate.id,
            )
        )
        asyncio.run(
            knowledge_base.activate_staged_generation(
                candidate.id,
                expected_active_generation=previous_generation,
            )
        )
        active_after_smoke = asyncio.run(knowledge_base.get_active_generation_id())
        active_results = asyncio.run(knowledge_base.search_my_work("candidato", ()))
    finally:
        asyncio.run(database.close())
        engine.dispose()

    assert active_before_smoke == previous_generation
    assert "Índice candidato" in {result.title for result in smoke_results}
    assert active_after_smoke == candidate.id
    assert "Índice candidato" in {result.title for result in active_results}
