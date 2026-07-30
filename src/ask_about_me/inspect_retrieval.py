import argparse
import asyncio
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any, cast
from uuid import UUID

from ask_about_me.composition import build_openai_knowledge_base
from ask_about_me.config import Settings, get_settings
from ask_about_me.db import Database
from ask_about_me.knowledge_base import IndexProfile, PostgresKnowledgeBase
from ask_about_me.providers import LocalHashEmbeddingProvider
from ask_about_me.rag import (
    CalibratedEvidenceSupportEvaluator,
    ConversationMessage,
    ConversationRole,
    RetrievalQuery,
    RetrievedChunk,
    SupportDecision,
)


@dataclass(frozen=True, slots=True)
class RetrievalInspection:
    query: RetrievalQuery
    chunks: tuple[RetrievedChunk, ...]
    support: SupportDecision
    index_generation: UUID | None
    index_profile: str | None
    retrieval_profile: str


class RetrievalInspector:
    def __init__(
        self,
        *,
        database: Database,
        knowledge_base: PostgresKnowledgeBase,
    ) -> None:
        self.database = database
        self.knowledge_base = knowledge_base

    async def inspect(
        self,
        *,
        question: str,
        history: Sequence[ConversationMessage],
        generation_id: UUID | None = None,
    ) -> RetrievalInspection:
        normalized_history = tuple(history)
        query = self.knowledge_base.build_retrieval_query(question, normalized_history)
        chunks = (
            await self.knowledge_base.search_my_work(question, normalized_history)
            if generation_id is None
            else await self.knowledge_base.search_generation(
                question,
                normalized_history,
                generation_id=generation_id,
            )
        )
        retrieval_profile = (
            chunks[0].signals.retrieval_profile if chunks else "hybrid-v2:weighted-lexical-v1"
        )
        support = CalibratedEvidenceSupportEvaluator().evaluate(
            question=question,
            retrieval_query=query,
            chunks=chunks,
            retrieval_profile=retrieval_profile,
        )
        profile = await self.knowledge_base.get_index_profile(generation_id=generation_id)
        resolved_generation = (
            generation_id
            if generation_id is not None
            else await self.knowledge_base.get_active_generation_id()
        )
        return RetrievalInspection(
            query=query,
            chunks=chunks,
            support=support,
            index_generation=resolved_generation,
            index_profile=None if profile is None else profile.identifier,
            retrieval_profile=retrieval_profile,
        )

    async def close(self) -> None:
        await self.database.close()


def _parse_history_entry(value: str) -> ConversationMessage:
    try:
        role_value, content = value.split(":", maxsplit=1)
        role = ConversationRole(role_value.strip())
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "history entries must use 'user: message' or 'assistant: message'"
        ) from error
    if not content.strip():
        raise argparse.ArgumentTypeError("history messages must not be empty")
    return ConversationMessage(role=role, content=content.strip())


async def build_retrieval_inspector(settings: Settings) -> RetrievalInspector:
    database = Database(settings.database_url)
    local_knowledge_base = PostgresKnowledgeBase(
        database=database,
        embedding_provider=LocalHashEmbeddingProvider(),
    )
    try:
        active_profile = await local_knowledge_base.get_active_index_profile()
        knowledge_base = _knowledge_base_for_active_profile(
            settings=settings,
            database=database,
            active_profile=active_profile,
            local_knowledge_base=local_knowledge_base,
        )
    except BaseException:
        await database.close()
        raise
    return RetrievalInspector(database=database, knowledge_base=knowledge_base)


def _knowledge_base_for_active_profile(
    *,
    settings: Settings,
    database: Database,
    active_profile: IndexProfile | None,
    local_knowledge_base: PostgresKnowledgeBase,
) -> PostgresKnowledgeBase:
    if active_profile is None:
        return local_knowledge_base
    if active_profile.embedding == LocalHashEmbeddingProvider().profile:
        return local_knowledge_base
    if active_profile.embedding.provider == "openai":
        if settings.openai_api_key is None:
            raise RuntimeError("AAM_OPENAI_API_KEY is required to inspect this OpenAI-indexed KB")
        return build_openai_knowledge_base(settings, database)
    raise RuntimeError(
        "The active KB uses an embedding provider unsupported by the retrieval inspector: "
        f"{active_profile.embedding.provider}/{active_profile.embedding.model}."
    )


def inspection_as_dict(inspection: RetrievalInspection) -> dict[str, Any]:
    payload = asdict(inspection)
    return cast(dict[str, Any], _json_ready(payload))


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_ready(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    return value


def _print_human(inspection: RetrievalInspection) -> None:
    query = inspection.query
    print(f"Original question: {query.original_question}")
    print(f"Embedding query: {query.embedding_text}")
    print(f"Lexical query: {query.lexical_text}")
    print(f"Query strategy: {query.strategy_version}")
    print(f"History used: {query.history_reason or 'none'}")
    print(f"Index generation: {inspection.index_generation or 'none'}")
    print(f"Index profile: {inspection.index_profile or 'none'}")
    print(f"Retrieval profile: {inspection.retrieval_profile}")
    print(
        "Support decision: "
        f"{'supported' if inspection.support.supported else 'unsupported'} "
        f"({inspection.support.rule_version}; "
        f"{', '.join(inspection.support.reasons)})"
    )
    if not inspection.chunks:
        print("No chunks returned.")
        return
    for position, chunk in enumerate(inspection.chunks, start=1):
        signals = chunk.signals
        print(f"{position}. rrf={signals.rrf_score:.6f} id={chunk.id}")
        print(
            "   "
            f"vector_distance={signals.vector_distance} "
            f"vector_similarity={signals.vector_similarity} "
            f"vector_rank={signals.vector_rank}"
        )
        print(
            "   "
            f"text_rank_cd={signals.text_rank_cd} text_rank={signals.text_rank} "
            f"title_match={signals.title_match} section_match={signals.section_match}"
        )
        print(f"   {chunk.document_type.value} | {chunk.title} | {chunk.section}")
        print(f"   {chunk.excerpt}")


async def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect KB retrieval without calling OpenAI answer generation."
    )
    parser.add_argument("question", help="Visitor question to search for")
    parser.add_argument(
        "--history",
        action="append",
        default=[],
        type=_parse_history_entry,
        metavar="ROLE:MESSAGE",
        help="Optional prior message; may be repeated and preserves the provided order",
    )
    parser.add_argument("--generation", type=UUID)
    parser.add_argument("--json", action="store_true", dest="as_json")
    arguments = parser.parse_args()
    inspector = await build_retrieval_inspector(get_settings())
    try:
        inspection = await inspector.inspect(
            question=arguments.question,
            history=arguments.history,
            generation_id=arguments.generation,
        )
    finally:
        await inspector.close()
    if arguments.as_json:
        print(json.dumps(inspection_as_dict(inspection), ensure_ascii=False, indent=2))
    else:
        _print_human(inspection)


if __name__ == "__main__":
    asyncio.run(_main())
