import hashlib
import re
from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Protocol

from openai import AsyncOpenAI, OpenAIError

from ask_about_me.knowledge_base import EmbeddingProfile


class OpenAIProviderUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class IndexedEmbedding:
    index: int
    values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class EmbeddingBatch:
    embeddings: tuple[IndexedEmbedding, ...]


class OpenAIEmbeddingGateway(Protocol):
    async def create_embeddings(
        self,
        *,
        inputs: tuple[str, ...],
        model: str,
        dimensions: int,
    ) -> EmbeddingBatch: ...


class OpenAISdkEmbeddingGateway:
    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float = 30,
        max_retries: int = 2,
    ) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )

    async def create_embeddings(
        self,
        *,
        inputs: tuple[str, ...],
        model: str,
        dimensions: int,
    ) -> EmbeddingBatch:
        try:
            response = await self._client.embeddings.create(
                input=list(inputs),
                model=model,
                dimensions=dimensions,
                encoding_format="float",
            )
        except OpenAIError as error:
            raise OpenAIProviderUnavailableError("OpenAI could not generate embeddings") from error
        return EmbeddingBatch(
            embeddings=tuple(
                IndexedEmbedding(
                    index=item.index,
                    values=tuple(item.embedding),
                )
                for item in response.data
            )
        )


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimensions: int,
        batch_size: int = 64,
        timeout_seconds: float = 30,
        max_retries: int = 2,
        gateway: OpenAIEmbeddingGateway | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OpenAI API key must not be empty")
        if not model.strip():
            raise ValueError("embedding model must not be empty")
        if dimensions < 1:
            raise ValueError("embedding dimensions must be positive")
        if batch_size < 1 or batch_size > 2048:
            raise ValueError("embedding batch_size must be between 1 and 2048")
        if timeout_seconds <= 0:
            raise ValueError("OpenAI timeout must be positive")
        if max_retries < 0:
            raise ValueError("OpenAI max_retries must not be negative")

        self._profile = EmbeddingProfile(
            provider="openai",
            model=model.strip(),
            dimensions=dimensions,
        )
        self._batch_size = batch_size
        self._gateway = gateway or OpenAISdkEmbeddingGateway(
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

    @property
    def profile(self) -> EmbeddingProfile:
        return self._profile

    async def embed_query(self, text: str) -> tuple[float, ...]:
        embeddings = await self.embed_documents((text,))
        return embeddings[0]

    async def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if any(not text.strip() for text in texts):
            raise ValueError("embedding inputs must not be empty")

        embeddings: list[tuple[float, ...]] = []
        for start in range(0, len(texts), self._batch_size):
            batch_inputs = texts[start : start + self._batch_size]
            batch = await self._gateway.create_embeddings(
                inputs=batch_inputs,
                model=self._profile.model,
                dimensions=self._profile.dimensions,
            )
            ordered = sorted(batch.embeddings, key=lambda embedding: embedding.index)
            has_expected_indexes = [embedding.index for embedding in ordered] == list(
                range(len(batch_inputs))
            )
            has_expected_dimensions = all(
                len(embedding.values) == self._profile.dimensions for embedding in ordered
            )
            has_only_finite_values = all(
                all(isfinite(value) for value in embedding.values) for embedding in ordered
            )
            if (
                not has_expected_indexes
                or not has_expected_dimensions
                or not has_only_finite_values
            ):
                raise OpenAIProviderUnavailableError(
                    "OpenAI returned an invalid embedding response"
                )
            embeddings.extend(embedding.values for embedding in ordered)
        return tuple(embeddings)


class LocalHashEmbeddingProvider:
    """Deterministic local embeddings for development and tests, never production."""

    _token_pattern = re.compile(r"\w+", re.UNICODE)

    def __init__(self, *, dimensions: int = 64) -> None:
        if dimensions < 8:
            raise ValueError("dimensions must be at least 8")
        self._dimensions = dimensions

    @property
    def profile(self) -> EmbeddingProfile:
        return EmbeddingProfile(
            provider="local",
            model="hash-blake2b-v1",
            dimensions=self._dimensions,
        )

    async def embed_query(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self._dimensions
        for token in self._token_pattern.findall(text.casefold()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest, byteorder="big") % self._dimensions
            sign = 1.0 if digest[0] & 1 else -1.0
            vector[bucket] += sign

        norm = sqrt(sum(value * value for value in vector))
        if norm == 0:
            vector[0] = 1.0
            return tuple(vector)
        return tuple(value / norm for value in vector)

    async def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return tuple([await self.embed_query(text) for text in texts])
