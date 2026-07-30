from ask_about_me.config import Settings
from ask_about_me.db import Database
from ask_about_me.knowledge_base import PostgresKnowledgeBase, TokenSectionChunker
from ask_about_me.openai_generation import OpenAIAnswerGenerator
from ask_about_me.providers import OpenAIEmbeddingProvider
from ask_about_me.rag import DeterministicRetrievalQueryBuilder, PortfolioRag


def build_openai_knowledge_base(
    settings: Settings,
    database: Database,
    *,
    retrieval_query_builder: DeterministicRetrievalQueryBuilder | None = None,
) -> PostgresKnowledgeBase:
    if settings.openai_api_key is None:
        raise ValueError("AAM_OPENAI_API_KEY is required to build the Knowledge Base")

    embedding_provider = OpenAIEmbeddingProvider(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        batch_size=settings.embedding_batch_size,
        timeout_seconds=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )
    return PostgresKnowledgeBase(
        database=database,
        embedding_provider=embedding_provider,
        chunker=TokenSectionChunker(
            model=settings.embedding_model,
            target_tokens=settings.chunk_target_tokens,
            max_tokens=settings.chunk_max_tokens,
            overlap_tokens=settings.chunk_overlap_tokens,
        ),
        retrieval_query_builder=retrieval_query_builder,
    )


def build_portfolio_rag(settings: Settings, database: Database) -> PortfolioRag:
    if settings.openai_api_key is None:
        raise ValueError("AAM_OPENAI_API_KEY is required to build the RAG pipeline")

    api_key = settings.openai_api_key.get_secret_value()
    retrieval_query_builder = DeterministicRetrievalQueryBuilder()
    return PortfolioRag(
        knowledge_base=build_openai_knowledge_base(
            settings,
            database,
            retrieval_query_builder=retrieval_query_builder,
        ),
        answer_generator=OpenAIAnswerGenerator(
            api_key=api_key,
            model=settings.generation_model,
            max_output_tokens=settings.generation_max_output_tokens,
            timeout_seconds=settings.openai_timeout_seconds,
            max_retries=settings.openai_max_retries,
        ),
        retrieval_query_builder=retrieval_query_builder,
    )
