import asyncio
from dataclasses import dataclass

import pytest

from ask_about_me.providers import (
    EmbeddingBatch,
    IndexedEmbedding,
    OpenAIEmbeddingProvider,
    OpenAIProviderUnavailableError,
)


@dataclass(frozen=True)
class RecordedEmbeddingRequest:
    inputs: tuple[str, ...]
    model: str
    dimensions: int


class RecordingEmbeddingGateway:
    def __init__(self) -> None:
        self.requests: list[RecordedEmbeddingRequest] = []

    async def create_embeddings(
        self,
        *,
        inputs: tuple[str, ...],
        model: str,
        dimensions: int,
    ) -> EmbeddingBatch:
        self.requests.append(
            RecordedEmbeddingRequest(
                inputs=inputs,
                model=model,
                dimensions=dimensions,
            )
        )
        return EmbeddingBatch(
            embeddings=tuple(
                reversed(
                    tuple(
                        IndexedEmbedding(
                            index=index,
                            values=(float(len(text)), float(index)),
                        )
                        for index, text in enumerate(inputs)
                    )
                )
            )
        )


class InvalidEmbeddingGateway:
    async def create_embeddings(
        self,
        *,
        inputs: tuple[str, ...],
        model: str,
        dimensions: int,
    ) -> EmbeddingBatch:
        return EmbeddingBatch(
            embeddings=(
                IndexedEmbedding(index=1, values=(1.0, 0.0)),
                IndexedEmbedding(index=1, values=(0.0, 1.0)),
            )
        )


class NonFiniteEmbeddingGateway:
    async def create_embeddings(
        self,
        *,
        inputs: tuple[str, ...],
        model: str,
        dimensions: int,
    ) -> EmbeddingBatch:
        return EmbeddingBatch(
            embeddings=(
                IndexedEmbedding(index=0, values=(float("nan"), 0.0)),
            )
        )


def test_openai_embedding_provider_batches_documents_and_preserves_input_order() -> None:
    gateway = RecordingEmbeddingGateway()
    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        model="text-embedding-3-small",
        dimensions=2,
        batch_size=2,
        gateway=gateway,
    )

    embeddings = asyncio.run(provider.embed_documents(("um", "dois", "três")))

    assert embeddings == ((2.0, 0.0), (4.0, 1.0), (4.0, 0.0))
    assert gateway.requests == [
        RecordedEmbeddingRequest(
            inputs=("um", "dois"),
            model="text-embedding-3-small",
            dimensions=2,
        ),
        RecordedEmbeddingRequest(
            inputs=("três",),
            model="text-embedding-3-small",
            dimensions=2,
        ),
    ]


def test_openai_embedding_provider_exposes_the_index_profile() -> None:
    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        model="text-embedding-3-small",
        dimensions=1536,
        gateway=RecordingEmbeddingGateway(),
    )

    assert provider.profile.provider == "openai"
    assert provider.profile.model == "text-embedding-3-small"
    assert provider.profile.dimensions == 1536


def test_openai_embedding_provider_normalizes_an_invalid_provider_batch() -> None:
    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        model="text-embedding-3-small",
        dimensions=2,
        gateway=InvalidEmbeddingGateway(),
    )

    with pytest.raises(
        OpenAIProviderUnavailableError,
        match="invalid embedding response",
    ):
        asyncio.run(provider.embed_documents(("um", "dois")))


def test_openai_embedding_provider_rejects_non_finite_values() -> None:
    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        model="text-embedding-3-small",
        dimensions=2,
        gateway=NonFiniteEmbeddingGateway(),
    )

    with pytest.raises(
        OpenAIProviderUnavailableError,
        match="invalid embedding response",
    ):
        asyncio.run(provider.embed_documents(("um",)))
