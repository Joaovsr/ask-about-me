import re
from dataclasses import dataclass
from math import isfinite
from typing import Protocol, cast
from uuid import UUID, uuid4

import tiktoken
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ask_about_me.db import Database
from ask_about_me.rag import (
    RETRIEVAL_PIPELINE_VERSION,
    ConversationMessage,
    DeterministicRetrievalQueryBuilder,
    DocumentType,
    RetrievalQuery,
    RetrievalSignals,
    RetrievedChunk,
)

LEGACY_LEXICAL_STRATEGY = "legacy-content-only-v1"
WEIGHTED_LEXICAL_STRATEGY = "weighted-portuguese-v1"


@dataclass(frozen=True, slots=True)
class EmbeddingProfile:
    provider: str
    model: str
    dimensions: int


@dataclass(frozen=True, slots=True)
class IndexProfile:
    embedding: EmbeddingProfile
    chunker_version: str
    canonical_locale: str = "pt-BR"
    lexical_strategy_version: str = WEIGHTED_LEXICAL_STRATEGY

    @property
    def identifier(self) -> str:
        embedding = self.embedding
        return (
            f"embedding={embedding.provider}/{embedding.model}/{embedding.dimensions};"
            f"chunker={self.chunker_version};locale={self.canonical_locale};"
            f"lexical={self.lexical_strategy_version}"
        )

    def retrieval_identifier(self, *, query_strategy_version: str) -> str:
        return (
            f"retrieval={RETRIEVAL_PIPELINE_VERSION};"
            f"query={query_strategy_version};{self.identifier}"
        )


class EmbeddingProvider(Protocol):
    @property
    def profile(self) -> EmbeddingProfile: ...

    async def embed_query(self, text: str) -> tuple[float, ...]: ...

    async def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...


@dataclass(frozen=True, slots=True)
class ProjectedSection:
    name: str
    text: str


@dataclass(frozen=True, slots=True)
class ProjectedKbDocument:
    source_id: UUID
    source_revision: int
    doc_type: DocumentType
    title: str
    slug: str
    source_url: str
    sections: tuple[ProjectedSection, ...]


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    position: int
    section: str
    content: str


@dataclass(frozen=True, slots=True)
class _PreparedDocument:
    document: ProjectedKbDocument
    document_id: UUID
    canonical_text: str
    chunks: tuple[ChunkDraft, ...]


@dataclass(frozen=True, slots=True)
class PreparedIndexGeneration:
    id: UUID
    documents: tuple[_PreparedDocument, ...]
    embeddings: tuple[tuple[float, ...], ...]
    profile: IndexProfile


class StaleIndexGenerationError(RuntimeError):
    def __init__(self, *, expected: UUID | None, actual: UUID | None) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"active KB index generation changed: expected {expected}, found {actual}")


class EmbeddingProfileMismatchError(RuntimeError):
    def __init__(self, *, indexed: EmbeddingProfile, configured: EmbeddingProfile) -> None:
        self.indexed = indexed
        self.configured = configured
        super().__init__(
            "active KB generation uses a different embedding profile; reindexing is required"
        )


class IndexProfileMismatchError(RuntimeError):
    def __init__(self, *, indexed: IndexProfile, prepared: IndexProfile) -> None:
        self.indexed = indexed
        self.prepared = prepared
        super().__init__(
            "active KB generation uses a different index profile; full reindexing is required"
        )


class UnsupportedLexicalStrategyError(RuntimeError):
    def __init__(self, strategy: str) -> None:
        self.strategy = strategy
        super().__init__(f"unsupported lexical strategy {strategy!r}; reindexing is required")


class DocumentChunker(Protocol):
    @property
    def version(self) -> str: ...

    def chunk(self, document: ProjectedKbDocument) -> tuple[ChunkDraft, ...]: ...


class SectionChunker:
    """Split projected sections into bounded chunks while retaining their section name."""

    def __init__(self, *, max_characters: int = 1_200) -> None:
        if max_characters < 50:
            raise ValueError("max_characters must be at least 50")
        self._max_characters = max_characters

    @property
    def version(self) -> str:
        return f"section-char-v1:{self._max_characters}"

    def chunk(self, document: ProjectedKbDocument) -> tuple[ChunkDraft, ...]:
        chunks: list[ChunkDraft] = []
        for section in document.sections:
            section_name = section.name.strip()
            section_text = section.text.strip()
            if not section_name or not section_text:
                raise ValueError("projected sections require a name and text")

            section_chunks = self._split_preserving_text(section_text)
            chunks.extend(
                ChunkDraft(
                    position=len(chunks),
                    section=section_name,
                    content=content,
                )
                for content in section_chunks
            )
        return tuple(chunks)

    def _split_preserving_text(self, section_text: str) -> tuple[str, ...]:
        chunks: list[str] = []
        start = 0
        while start < len(section_text):
            maximum_end = min(start + self._max_characters, len(section_text))
            end = maximum_end
            if maximum_end < len(section_text):
                word_boundary = section_text.rfind(" ", start, maximum_end + 1)
                if word_boundary > start:
                    end = word_boundary

            chunk = section_text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start = end
            while start < len(section_text) and section_text[start].isspace():
                start += 1

        return tuple(chunks)


class TokenSectionChunker:
    """Split sections on semantic boundaries using the embedding model tokenizer."""

    _sentence_boundary = re.compile(r"(?<=[.!?])\s+")

    def __init__(
        self,
        *,
        model: str = "text-embedding-3-small",
        target_tokens: int = 350,
        max_tokens: int = 500,
        overlap_tokens: int = 50,
    ) -> None:
        if target_tokens < 8:
            raise ValueError("target_tokens must be at least 8")
        if max_tokens < target_tokens:
            raise ValueError("max_tokens must be greater than or equal to target_tokens")
        if overlap_tokens < 0 or overlap_tokens >= target_tokens:
            raise ValueError("overlap_tokens must be non-negative and smaller than target_tokens")

        try:
            self._encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            self._encoding = tiktoken.get_encoding("cl100k_base")
        self._target_tokens = target_tokens
        self._max_tokens = max_tokens
        self._overlap_tokens = overlap_tokens
        self._model = model

    @property
    def version(self) -> str:
        return (
            f"section-token-v1:{self._model}:"
            f"{self._target_tokens}:{self._max_tokens}:{self._overlap_tokens}"
        )

    def count_tokens(self, text: str) -> int:
        return len(self._encoding.encode(text))

    def chunk(self, document: ProjectedKbDocument) -> tuple[ChunkDraft, ...]:
        chunks: list[ChunkDraft] = []
        for section in document.sections:
            section_name = section.name.strip()
            section_text = section.text.strip()
            if not section_name or not section_text:
                raise ValueError("projected sections require a name and text")

            for content in self._chunk_section(section_text):
                chunks.append(
                    ChunkDraft(
                        position=len(chunks),
                        section=section_name,
                        content=content,
                    )
                )
        return tuple(chunks)

    def _chunk_section(self, text: str) -> tuple[str, ...]:
        units = self._semantic_units(text)
        chunks: list[str] = []
        current: list[str] = []

        for unit in units:
            candidate = self._join_units((*current, unit))
            if current and self.count_tokens(candidate) > self._target_tokens:
                chunks.append(self._join_units(tuple(current)))
                current = self._overlap_units(current)
                candidate = self._join_units((*current, unit))
                while current and self.count_tokens(candidate) > self._max_tokens:
                    current.pop(0)
                    candidate = self._join_units((*current, unit))

            current.append(unit)

        if current:
            final_chunk = self._join_units(tuple(current))
            if not chunks or final_chunk != chunks[-1]:
                chunks.append(final_chunk)
        return tuple(chunks)

    def _semantic_units(self, text: str) -> tuple[str, ...]:
        units: list[str] = []
        paragraph_parts = re.split(r"(\n\s*\n+)", text)
        paragraphs: list[str] = []
        for index in range(0, len(paragraph_parts), 2):
            paragraph = paragraph_parts[index]
            if not paragraph:
                continue
            separator = paragraph_parts[index + 1] if index + 1 < len(paragraph_parts) else ""
            paragraphs.append(paragraph + separator)

        for paragraph in paragraphs:
            if self.count_tokens(paragraph.strip()) <= self._target_tokens:
                units.append(paragraph)
                continue

            sentences = self._sentences_preserving_whitespace(paragraph)
            for sentence in sentences:
                if self.count_tokens(sentence) <= self._max_tokens:
                    units.append(sentence)
                else:
                    units.extend(self._split_oversized_sentence(sentence))
        return tuple(units)

    def _sentences_preserving_whitespace(self, paragraph: str) -> tuple[str, ...]:
        sentences: list[str] = []
        start = 0
        for boundary in self._sentence_boundary.finditer(paragraph):
            sentences.append(paragraph[start : boundary.end()])
            start = boundary.end()
        if start < len(paragraph):
            sentences.append(paragraph[start:])
        return tuple(sentence for sentence in sentences if sentence.strip())

    def _split_oversized_sentence(self, sentence: str) -> tuple[str, ...]:
        tokens = self._encoding.encode(sentence)
        return tuple(
            self._encoding.decode(tokens[start : start + self._max_tokens])
            for start in range(0, len(tokens), self._max_tokens)
        )

    def _overlap_units(self, units: list[str]) -> list[str]:
        if self._overlap_tokens == 0:
            return []
        overlap: list[str] = []
        for unit in reversed(units):
            candidate = self._join_units((unit, *overlap))
            if self.count_tokens(candidate) > self._overlap_tokens:
                break
            overlap.insert(0, unit)
        return overlap

    @staticmethod
    def _join_units(units: tuple[str, ...]) -> str:
        return "".join(units).strip()


class PostgresKnowledgeBase:
    def __init__(
        self,
        *,
        database: Database,
        embedding_provider: EmbeddingProvider,
        chunker: DocumentChunker | None = None,
        result_limit: int = 8,
        retrieval_query_builder: DeterministicRetrievalQueryBuilder | None = None,
    ) -> None:
        if result_limit < 1:
            raise ValueError("result_limit must be positive")
        self._database = database
        self._embedding_provider = embedding_provider
        self._chunker = chunker or TokenSectionChunker()
        self._result_limit = result_limit
        self._retrieval_query_builder = (
            retrieval_query_builder or DeterministicRetrievalQueryBuilder()
        )

    async def get_active_generation_id(self) -> UUID | None:
        async with self._database.connect() as connection:
            result = await connection.execute(
                text(
                    """
                    SELECT id
                    FROM kb_index_generations
                    WHERE is_active
                    """
                )
            )
        return cast(UUID | None, result.scalar_one_or_none())

    async def get_active_embedding_profile(self) -> EmbeddingProfile | None:
        profile = await self.get_active_index_profile()
        return None if profile is None else profile.embedding

    async def get_active_index_profile(self) -> IndexProfile | None:
        async with self._database.connect() as connection:
            return await self._read_index_profile(connection)

    async def get_index_profile(
        self,
        *,
        generation_id: UUID | None = None,
    ) -> IndexProfile | None:
        async with self._database.connect() as connection:
            return await self._read_index_profile(
                connection,
                generation_id=generation_id,
            )

    @staticmethod
    async def _read_index_profile(
        connection: AsyncConnection,
        *,
        generation_id: UUID | None = None,
    ) -> IndexProfile | None:
        result = await connection.execute(
            text(
                """
                SELECT
                    embedding_provider,
                    embedding_model,
                    embedding_dimensions,
                    chunker_version,
                    canonical_locale,
                    lexical_strategy_version
                FROM kb_index_generations
                WHERE (
                    CAST(:generation_id AS uuid) IS NULL
                    AND is_active
                ) OR id = CAST(:generation_id AS uuid)
                """
            ),
            {"generation_id": generation_id},
        )
        row = result.one_or_none()
        if row is None:
            return None
        return IndexProfile(
            embedding=EmbeddingProfile(
                provider=row.embedding_provider,
                model=row.embedding_model,
                dimensions=row.embedding_dimensions,
            ),
            chunker_version=row.chunker_version,
            canonical_locale=row.canonical_locale,
            lexical_strategy_version=row.lexical_strategy_version,
        )

    async def replace_index(
        self,
        documents: tuple[ProjectedKbDocument, ...],
        *,
        expected_active_generation: UUID | None,
    ) -> UUID:
        prepared = await self.prepare_index(documents)
        async with self._database.transaction() as connection:
            await self.activate_prepared_index(
                connection,
                prepared,
                expected_active_generation=expected_active_generation,
            )
        return prepared.id

    async def replace_sources(
        self,
        documents: tuple[ProjectedKbDocument, ...],
        *,
        expected_active_generation: UUID | None,
    ) -> UUID:
        prepared = await self.prepare_index(documents)
        async with self._database.transaction() as connection:
            await self.activate_prepared_sources(
                connection,
                prepared,
                expected_active_generation=expected_active_generation,
            )
        return prepared.id

    async def prepare_index(
        self, documents: tuple[ProjectedKbDocument, ...]
    ) -> PreparedIndexGeneration:
        prepared_documents = self._prepare_documents(documents)
        chunk_contents = tuple(
            self._embedding_input(prepared.document, chunk)
            for prepared in prepared_documents
            for chunk in prepared.chunks
        )
        embeddings = await self._embedding_provider.embed_documents(chunk_contents)
        self._validate_embeddings(
            embeddings,
            expected_count=len(chunk_contents),
            expected_dimensions=self._embedding_provider.profile.dimensions,
        )
        return PreparedIndexGeneration(
            id=uuid4(),
            documents=prepared_documents,
            embeddings=embeddings,
            profile=IndexProfile(
                embedding=self._embedding_provider.profile,
                chunker_version=self._chunker.version,
            ),
        )

    async def activate_prepared_index(
        self,
        connection: AsyncConnection,
        prepared: PreparedIndexGeneration,
        *,
        expected_active_generation: UUID | None,
    ) -> None:
        await self._activate_prepared_index(
            connection,
            prepared,
            expected_active_generation=expected_active_generation,
            preserve_active_documents=False,
        )

    async def activate_prepared_sources(
        self,
        connection: AsyncConnection,
        prepared: PreparedIndexGeneration,
        *,
        expected_active_generation: UUID | None,
    ) -> None:
        await self._activate_prepared_index(
            connection,
            prepared,
            expected_active_generation=expected_active_generation,
            preserve_active_documents=True,
        )

    async def stage_prepared_sources(
        self,
        prepared: PreparedIndexGeneration,
        *,
        expected_active_generation: UUID | None,
    ) -> None:
        async with self._database.transaction() as connection:
            await self._stage_prepared_index(
                connection,
                prepared,
                expected_active_generation=expected_active_generation,
                preserve_active_documents=True,
            )

    async def activate_staged_generation(
        self,
        generation_id: UUID,
        *,
        expected_active_generation: UUID | None,
    ) -> None:
        async with self._database.transaction() as connection:
            active_generation = await self._lock_and_get_active_generation(connection)
            if active_generation != expected_active_generation:
                raise StaleIndexGenerationError(
                    expected=expected_active_generation,
                    actual=active_generation,
                )

            staged_result = await connection.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM kb_index_generations
                        WHERE id = :generation_id
                        AND NOT is_active
                    )
                    """
                ),
                {"generation_id": generation_id},
            )
            if not staged_result.scalar_one():
                raise ValueError("staged KB generation does not exist")
            await self._switch_active_generation(connection, generation_id)

    async def _activate_prepared_index(
        self,
        connection: AsyncConnection,
        prepared: PreparedIndexGeneration,
        *,
        expected_active_generation: UUID | None,
        preserve_active_documents: bool,
    ) -> None:
        await self._stage_prepared_index(
            connection,
            prepared,
            expected_active_generation=expected_active_generation,
            preserve_active_documents=preserve_active_documents,
        )
        await self._switch_active_generation(connection, prepared.id)

    async def _stage_prepared_index(
        self,
        connection: AsyncConnection,
        prepared: PreparedIndexGeneration,
        *,
        expected_active_generation: UUID | None,
        preserve_active_documents: bool,
    ) -> None:
        active_generation = await self._lock_and_get_active_generation(connection)
        if active_generation != expected_active_generation:
            raise StaleIndexGenerationError(
                expected=expected_active_generation,
                actual=active_generation,
            )

        if (
            preserve_active_documents
            and active_generation is not None
            and await self._has_unaffected_active_documents(
                connection,
                replaced_source_ids=tuple(
                    document.document.source_id for document in prepared.documents
                ),
            )
        ):
            active_profile = await self._read_index_profile(
                connection,
                generation_id=active_generation,
            )
            if active_profile is None:
                raise RuntimeError("active KB generation has no index profile")
            if active_profile != prepared.profile:
                raise IndexProfileMismatchError(
                    indexed=active_profile,
                    prepared=prepared.profile,
                )

        await self._write_generation(
            connection,
            generation_id=prepared.id,
            prepared_documents=prepared.documents,
            embeddings=prepared.embeddings,
            index_profile=prepared.profile,
        )
        if preserve_active_documents:
            await self._copy_active_documents(
                connection,
                target_generation=prepared.id,
                replaced_source_ids=tuple(
                    document.document.source_id for document in prepared.documents
                ),
            )

    @staticmethod
    async def _lock_and_get_active_generation(
        connection: AsyncConnection,
    ) -> UUID | None:
        await connection.execute(text("LOCK TABLE kb_index_generations IN EXCLUSIVE MODE"))
        active_result = await connection.execute(
            text(
                """
                SELECT id
                FROM kb_index_generations
                WHERE is_active
                """
            )
        )
        return cast(UUID | None, active_result.scalar_one_or_none())

    @staticmethod
    async def _switch_active_generation(
        connection: AsyncConnection,
        generation_id: UUID,
    ) -> None:
        await connection.execute(
            text(
                """
                UPDATE kb_index_generations
                SET is_active = (id = :generation_id)
                WHERE is_active OR id = :generation_id
                """
            ),
            {"generation_id": generation_id},
        )

    @staticmethod
    async def _copy_active_documents(
        connection: AsyncConnection,
        *,
        target_generation: UUID,
        replaced_source_ids: tuple[UUID, ...],
    ) -> None:
        parameters = {
            "target_generation": target_generation,
            "replaced_source_ids": list(replaced_source_ids),
        }
        await connection.execute(
            text(
                """
                INSERT INTO kb_documents (
                    id, source_id, source_revision, index_generation, doc_type,
                    title, slug, source_url, canonical_text
                )
                SELECT
                    md5(document.id::text || CAST(:target_generation AS text))::uuid,
                    document.source_id,
                    document.source_revision,
                    :target_generation,
                    document.doc_type,
                    document.title,
                    document.slug,
                    document.source_url,
                    document.canonical_text
                FROM kb_documents AS document
                JOIN kb_index_generations AS generation
                    ON generation.id = document.index_generation
                    AND generation.is_active
                WHERE NOT (
                    document.source_id = ANY(CAST(:replaced_source_ids AS uuid[]))
                )
                """
            ),
            parameters,
        )
        await connection.execute(
            text(
                """
                INSERT INTO kb_chunks (
                    id, document_id, position, section, content, embedding,
                    lexical_search_vector
                )
                SELECT
                    md5(chunk.id::text || CAST(:target_generation AS text))::uuid,
                    md5(document.id::text || CAST(:target_generation AS text))::uuid,
                    chunk.position,
                    chunk.section,
                    chunk.content,
                    chunk.embedding,
                    chunk.lexical_search_vector
                FROM kb_chunks AS chunk
                JOIN kb_documents AS document ON document.id = chunk.document_id
                JOIN kb_index_generations AS generation
                    ON generation.id = document.index_generation
                    AND generation.is_active
                WHERE NOT (
                    document.source_id = ANY(CAST(:replaced_source_ids AS uuid[]))
                )
                """
            ),
            parameters,
        )

    @staticmethod
    async def _has_unaffected_active_documents(
        connection: AsyncConnection,
        *,
        replaced_source_ids: tuple[UUID, ...],
    ) -> bool:
        result = await connection.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM kb_documents AS document
                    JOIN kb_index_generations AS generation
                        ON generation.id = document.index_generation
                        AND generation.is_active
                    WHERE NOT (
                        document.source_id = ANY(CAST(:replaced_source_ids AS uuid[]))
                    )
                )
                """
            ),
            {"replaced_source_ids": list(replaced_source_ids)},
        )
        return bool(result.scalar_one())

    async def search_my_work(
        self, question: str, history: tuple[ConversationMessage, ...]
    ) -> tuple[RetrievedChunk, ...]:
        return await self._search(
            question,
            history,
            generation_id=None,
            result_limit=self._result_limit,
            candidate_limit=self._result_limit * 4,
        )

    async def search_generation(
        self,
        question: str,
        history: tuple[ConversationMessage, ...],
        *,
        generation_id: UUID,
    ) -> tuple[RetrievedChunk, ...]:
        return await self._search(
            question,
            history,
            generation_id=generation_id,
            result_limit=self._result_limit,
            candidate_limit=self._result_limit * 4,
        )

    async def search_for_evaluation(
        self,
        question: str,
        history: tuple[ConversationMessage, ...],
        *,
        generation_id: UUID | None,
        candidate_limit: int,
    ) -> tuple[RetrievedChunk, ...]:
        if candidate_limit < 1:
            raise ValueError("candidate_limit must be positive")
        return await self._search(
            question,
            history,
            generation_id=generation_id,
            result_limit=candidate_limit * 2,
            candidate_limit=candidate_limit,
        )

    async def _search(
        self,
        question: str,
        history: tuple[ConversationMessage, ...],
        *,
        generation_id: UUID | None,
        result_limit: int,
        candidate_limit: int,
    ) -> tuple[RetrievedChunk, ...]:
        if generation_id is None:
            index_profile = await self.get_active_index_profile()
        else:
            async with self._database.connect() as connection:
                index_profile = await self._read_index_profile(
                    connection,
                    generation_id=generation_id,
                )
        if index_profile is None:
            return ()
        if index_profile.embedding != self._embedding_provider.profile:
            raise EmbeddingProfileMismatchError(
                indexed=index_profile.embedding,
                configured=self._embedding_provider.profile,
            )
        lexical_strategy = index_profile.lexical_strategy_version
        if lexical_strategy == WEIGHTED_LEXICAL_STRATEGY:
            lexical_vector = "chunk.lexical_search_vector"
            title_match = (
                ":title_question <> '' AND "
                "to_tsvector('portuguese', document.title) "
                "@@ websearch_to_tsquery('portuguese', :title_question)"
            )
            section_match = (
                "to_tsvector('portuguese', chunk.section) "
                "@@ websearch_to_tsquery('portuguese', :question)"
            )
        elif lexical_strategy == LEGACY_LEXICAL_STRATEGY:
            lexical_vector = "chunk.search_vector"
            title_match = "FALSE"
            section_match = "FALSE"
        else:
            raise UnsupportedLexicalStrategyError(lexical_strategy)

        retrieval_query = self.build_retrieval_query(question, history)
        embedding = await self._embedding_provider.embed_query(retrieval_query.embedding_text)
        self._validate_embeddings(
            (embedding,),
            expected_count=1,
            expected_dimensions=self._embedding_provider.profile.dimensions,
        )
        embedding_literal = self._to_vector_literal(embedding)

        async with self._database.connect() as connection:
            result = await connection.execute(
                text(
                    f"""
                    WITH vector_ranked AS (
                        SELECT
                            chunk.id,
                            chunk.embedding <=> CAST(:embedding AS vector) AS distance,
                            ROW_NUMBER() OVER (
                                ORDER BY chunk.embedding <=> CAST(:embedding AS vector), chunk.id
                            ) AS rank
                        FROM kb_chunks AS chunk
                        JOIN kb_documents AS document ON document.id = chunk.document_id
                        JOIN kb_index_generations AS generation
                            ON generation.id = document.index_generation
                            AND (
                                (
                                    CAST(:generation_id AS uuid) IS NULL
                                    AND generation.is_active
                                )
                                OR generation.id = CAST(:generation_id AS uuid)
                            )
                        ORDER BY chunk.embedding <=> CAST(:embedding AS vector), chunk.id
                        LIMIT :candidate_limit
                    ),
                    text_ranked AS (
                        SELECT
                            chunk.id,
                            ts_rank_cd(
                                {lexical_vector},
                                websearch_to_tsquery('portuguese', :question)
                            ) AS rank_cd,
                            ROW_NUMBER() OVER (
                                ORDER BY
                                    ts_rank_cd(
                                        {lexical_vector},
                                        websearch_to_tsquery('portuguese', :question)
                                    ) DESC,
                                    chunk.id
                            ) AS rank
                        FROM kb_chunks AS chunk
                        JOIN kb_documents AS document ON document.id = chunk.document_id
                        JOIN kb_index_generations AS generation
                            ON generation.id = document.index_generation
                            AND (
                                (
                                    CAST(:generation_id AS uuid) IS NULL
                                    AND generation.is_active
                                )
                                OR generation.id = CAST(:generation_id AS uuid)
                            )
                        WHERE {lexical_vector}
                            @@ websearch_to_tsquery('portuguese', :question)
                        ORDER BY
                            ts_rank_cd(
                                {lexical_vector},
                                websearch_to_tsquery('portuguese', :question)
                            ) DESC,
                            chunk.id
                        LIMIT :candidate_limit
                    ),
                    candidate_ids AS (
                        SELECT id FROM vector_ranked
                        UNION
                        SELECT id FROM text_ranked
                    ),
                    ranked AS (
                        SELECT
                            candidate.id,
                            COALESCE(1.0 / (60 + vector_ranked.rank), 0.0)
                                + COALESCE(1.0 / (60 + text_ranked.rank), 0.0)
                                AS rrf_score,
                            vector_ranked.distance AS vector_distance,
                            vector_ranked.rank AS vector_rank,
                            text_ranked.rank_cd AS text_rank_cd,
                            text_ranked.rank AS text_rank
                        FROM candidate_ids AS candidate
                        LEFT JOIN vector_ranked ON vector_ranked.id = candidate.id
                        LEFT JOIN text_ranked ON text_ranked.id = candidate.id
                    )
                    SELECT
                        chunk.id,
                        document.id AS document_id,
                        document.source_id,
                        document.source_revision,
                        document.doc_type AS document_type,
                        document.title,
                        document.slug AS source_slug,
                        chunk.section,
                        chunk.content AS excerpt,
                        document.source_url,
                        ranked.rrf_score,
                        ranked.vector_distance,
                        ranked.vector_rank,
                        ranked.text_rank_cd,
                        ranked.text_rank,
                        {title_match} AS title_match,
                        {section_match} AS section_match,
                        document.index_generation
                    FROM ranked
                    JOIN kb_chunks AS chunk ON chunk.id = ranked.id
                    JOIN kb_documents AS document ON document.id = chunk.document_id
                    ORDER BY ranked.rrf_score DESC, chunk.id
                    LIMIT :result_limit
                    """
                ),
                {
                    "embedding": embedding_literal,
                    "question": retrieval_query.lexical_text,
                    "title_question": retrieval_query.title_text,
                    "generation_id": generation_id,
                    "candidate_limit": candidate_limit,
                    "result_limit": result_limit,
                },
            )

        return tuple(
            RetrievedChunk(
                id=row.id,
                document_id=row.document_id,
                source_id=row.source_id,
                source_revision=row.source_revision,
                source_slug=row.source_slug,
                document_type=DocumentType(row.document_type),
                title=row.title,
                section=row.section,
                excerpt=row.excerpt,
                source_url=row.source_url,
                signals=RetrievalSignals(
                    vector_distance=(
                        None if row.vector_distance is None else float(row.vector_distance)
                    ),
                    vector_similarity=(
                        None if row.vector_distance is None else 1.0 - float(row.vector_distance)
                    ),
                    vector_rank=(None if row.vector_rank is None else int(row.vector_rank)),
                    text_rank_cd=(None if row.text_rank_cd is None else float(row.text_rank_cd)),
                    text_rank=None if row.text_rank is None else int(row.text_rank),
                    title_match=bool(row.title_match),
                    section_match=bool(row.section_match),
                    rrf_score=float(row.rrf_score),
                    retrieval_profile=index_profile.retrieval_identifier(
                        query_strategy_version=retrieval_query.strategy_version
                    ),
                    index_generation=row.index_generation,
                    index_profile=index_profile.identifier,
                ),
            )
            for row in result
        )

    def build_retrieval_query(
        self,
        question: str,
        history: tuple[ConversationMessage, ...],
    ) -> RetrievalQuery:
        return self._retrieval_query_builder.build(question, history)

    @staticmethod
    def _to_vector_literal(embedding: tuple[float, ...]) -> str:
        if not embedding or not all(isfinite(value) for value in embedding):
            raise ValueError("embedding must contain finite values")
        return "[" + ",".join(str(value) for value in embedding) + "]"

    def _prepare_documents(
        self, documents: tuple[ProjectedKbDocument, ...]
    ) -> tuple[_PreparedDocument, ...]:
        if not documents:
            raise ValueError("at least one projected KB Doc is required")

        source_revisions: set[tuple[UUID, int]] = set()
        prepared: list[_PreparedDocument] = []
        for document in documents:
            if document.source_revision < 1:
                raise ValueError("source_revision must be positive")
            if (
                not document.title.strip()
                or not document.slug.strip()
                or not document.source_url.strip()
            ):
                raise ValueError("projected KB Docs require title, slug, and source_url")
            source_revision = (document.source_id, document.source_revision)
            if source_revision in source_revisions:
                raise ValueError("projected KB Docs must have unique source revisions")
            source_revisions.add(source_revision)

            chunks = self._chunker.chunk(document)
            if not chunks:
                raise ValueError("projected KB Docs require at least one chunk")
            prepared.append(
                _PreparedDocument(
                    document=document,
                    document_id=uuid4(),
                    canonical_text="\n\n".join(
                        section.text.strip() for section in document.sections
                    ),
                    chunks=chunks,
                )
            )

        return tuple(prepared)

    @staticmethod
    def _embedding_input(document: ProjectedKbDocument, chunk: ChunkDraft) -> str:
        return "\n".join(
            (
                f"Tipo de documento: {document.doc_type.value}",
                f"Título: {document.title.strip()}",
                f"Seção: {chunk.section}",
                f"Conteúdo: {chunk.content}",
            )
        )

    @staticmethod
    def _validate_embeddings(
        embeddings: tuple[tuple[float, ...], ...],
        *,
        expected_count: int,
        expected_dimensions: int,
    ) -> None:
        if len(embeddings) != expected_count:
            raise ValueError("embedding provider returned an unexpected number of embeddings")
        dimensions = {len(embedding) for embedding in embeddings}
        if dimensions == {0} or len(dimensions) != 1:
            raise ValueError("document embeddings must have one non-empty dimension")
        if dimensions != {expected_dimensions}:
            raise ValueError("embedding provider returned an unexpected dimension")
        if not all(all(isfinite(value) for value in embedding) for embedding in embeddings):
            raise ValueError("document embeddings must contain finite values")

    async def _write_generation(
        self,
        connection: AsyncConnection,
        *,
        generation_id: UUID,
        prepared_documents: tuple[_PreparedDocument, ...],
        embeddings: tuple[tuple[float, ...], ...],
        index_profile: IndexProfile,
    ) -> None:
        await connection.execute(
            text(
                """
                INSERT INTO kb_index_generations (
                    id,
                    is_active,
                    embedding_provider,
                    embedding_model,
                    embedding_dimensions,
                    chunker_version,
                    canonical_locale,
                    lexical_strategy_version
                )
                VALUES (
                    :generation_id,
                    FALSE,
                    :embedding_provider,
                    :embedding_model,
                    :embedding_dimensions,
                    :chunker_version,
                    'pt-BR',
                    :lexical_strategy_version
                )
                """
            ),
            {
                "generation_id": generation_id,
                "embedding_provider": index_profile.embedding.provider,
                "embedding_model": index_profile.embedding.model,
                "embedding_dimensions": index_profile.embedding.dimensions,
                "chunker_version": index_profile.chunker_version,
                "lexical_strategy_version": index_profile.lexical_strategy_version,
            },
        )
        await connection.execute(
            text(
                """
                INSERT INTO kb_documents (
                    id, source_id, source_revision, index_generation, doc_type,
                    title, slug, source_url, canonical_text
                ) VALUES (
                    :id, :source_id, :source_revision, :index_generation, :doc_type,
                    :title, :slug, :source_url, :canonical_text
                )
                """
            ),
            [
                {
                    "id": prepared.document_id,
                    "source_id": prepared.document.source_id,
                    "source_revision": prepared.document.source_revision,
                    "index_generation": generation_id,
                    "doc_type": prepared.document.doc_type.value,
                    "title": prepared.document.title.strip(),
                    "slug": prepared.document.slug.strip(),
                    "source_url": prepared.document.source_url.strip(),
                    "canonical_text": prepared.canonical_text,
                }
                for prepared in prepared_documents
            ],
        )

        embedding_index = 0
        chunk_rows: list[dict[str, object]] = []
        for prepared in prepared_documents:
            for chunk in prepared.chunks:
                chunk_rows.append(
                    {
                        "id": uuid4(),
                        "document_id": prepared.document_id,
                        "position": chunk.position,
                        "section": chunk.section,
                        "content": chunk.content,
                        "title": prepared.document.title.strip(),
                        "embedding": self._to_vector_literal(embeddings[embedding_index]),
                    }
                )
                embedding_index += 1

        await connection.execute(
            text(
                """
                INSERT INTO kb_chunks (
                    id, document_id, position, section, content, embedding,
                    lexical_search_vector
                ) VALUES (
                    :id, :document_id, :position, :section, :content,
                    CAST(:embedding AS vector),
                    setweight(to_tsvector('portuguese', :title), 'A')
                        || setweight(to_tsvector('portuguese', :section), 'B')
                        || setweight(to_tsvector('portuguese', :content), 'D')
                )
                """
            ),
            chunk_rows,
        )
