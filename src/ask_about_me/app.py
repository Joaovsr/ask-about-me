from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Literal, Self, cast

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ask_about_me.composition import build_portfolio_rag
from ask_about_me.config import Settings, get_settings
from ask_about_me.db import Database
from ask_about_me.providers import OpenAIProviderUnavailableError
from ask_about_me.rag import (
    AnswerStatus,
    Citation,
    ClaimAnswerItem,
    ClaimType,
    ConversationMessage,
    ConversationRole,
    DocumentType,
    LimitationAnswerItem,
    Locale,
    PortfolioAnswer,
    PortfolioRag,
)

MAX_CONVERSATION_CHARACTERS = 8000
MAX_ASK_BODY_BYTES = 16_384
RagFactory = Callable[[Settings, Database], PortfolioRag]


class AskBodyTooLargeError(Exception):
    pass


class AskBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] != "/ask":
            await self._app(scope, receive, send)
            return

        content_length = dict(scope["headers"]).get(b"content-length")
        if content_length is not None and int(content_length) > self._max_bytes:
            await self._send_too_large(scope, receive, send)
            return

        received_bytes = 0

        async def limited_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self._max_bytes:
                    raise AskBodyTooLargeError
            return message

        try:
            await self._app(scope, limited_receive, send)
        except AskBodyTooLargeError:
            await self._send_too_large(scope, receive, send)

    @staticmethod
    async def _send_too_large(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=413,
            content={"detail": "request body exceeds the byte limit"},
        )
        await response(scope, receive, send)


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class HttpModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class HistoryMessageRequest(HttpModel):
    role: ConversationRole
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class AskRequest(HttpModel):
    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
    ]
    locale: Locale
    history: list[HistoryMessageRequest] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def enforce_total_character_limit(self) -> Self:
        total_characters = len(self.question) + sum(
            len(message.content) for message in self.history
        )
        if total_characters > MAX_CONVERSATION_CHARACTERS:
            raise ValueError("conversation payload exceeds the character limit")
        return self


class ClaimAnswerItemResponse(HttpModel):
    kind: Literal["claim"] = "claim"
    claim_type: ClaimType
    text: str
    citation_ids: tuple[str, ...]


class LimitationAnswerItemResponse(HttpModel):
    kind: Literal["limitation"] = "limitation"
    text: str


class CitationResponse(HttpModel):
    id: str
    document_id: str
    source_id: str
    document_version: int
    document_type: DocumentType
    title: str
    section: str
    excerpt: str
    source_url: str


class AskResponse(HttpModel):
    status: AnswerStatus
    answer_items: list[ClaimAnswerItemResponse | LimitationAnswerItemResponse]
    citations: list[CitationResponse]


def create_app(
    settings: Settings | None = None,
    *,
    portfolio_rag: PortfolioRag | None = None,
    rag_factory: RagFactory | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.database = Database(resolved_settings.database_url)
        app.state.portfolio_rag = portfolio_rag
        if app.state.portfolio_rag is None and _has_openai_api_key(resolved_settings):
            factory = rag_factory or build_portfolio_rag
            app.state.portfolio_rag = factory(
                resolved_settings,
                cast(Database, app.state.database),
            )
        try:
            yield
        finally:
            await cast(Database, app.state.database).close()

    app = FastAPI(title="ask-about-me", lifespan=lifespan)
    app.add_middleware(AskBodyLimitMiddleware, max_bytes=MAX_ASK_BODY_BYTES)

    @app.get("/health/live")
    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def readiness(request: Request) -> dict[str, str]:
        database = cast(Database, request.app.state.database)
        try:
            await database.ping()
        except (TimeoutError, SQLAlchemyError) as error:
            raise HTTPException(
                status_code=503,
                detail={"status": "unavailable", "dependency": "database"},
            ) from error
        return {"status": "ok", "database": "available"}

    @app.post("/ask", response_model=AskResponse)
    async def ask(payload: AskRequest, request: Request) -> AskResponse:
        configured_rag = cast(PortfolioRag | None, request.app.state.portfolio_rag)
        if configured_rag is None:
            raise HTTPException(
                status_code=503,
                detail={"status": "unavailable", "dependency": "rag"},
            )

        try:
            answer = await configured_rag.answer(
                question=payload.question,
                locale=payload.locale,
                history=tuple(
                    ConversationMessage(role=message.role, content=message.content)
                    for message in payload.history
                ),
            )
        except OpenAIProviderUnavailableError as error:
            raise HTTPException(
                status_code=503,
                detail={"status": "unavailable", "dependency": "openai"},
            ) from error
        return _to_ask_response(answer)

    return app


def _has_openai_api_key(settings: Settings) -> bool:
    return (
        settings.openai_api_key is not None
        and bool(settings.openai_api_key.get_secret_value().strip())
    )


def _to_ask_response(answer: PortfolioAnswer) -> AskResponse:
    answer_items: list[ClaimAnswerItemResponse | LimitationAnswerItemResponse] = []
    for item in answer.answer_items:
        if isinstance(item, ClaimAnswerItem):
            answer_items.append(
                ClaimAnswerItemResponse(
                    claim_type=item.claim_type,
                    text=item.text,
                    citation_ids=tuple(str(citation_id) for citation_id in item.citation_ids),
                )
            )
        elif isinstance(item, LimitationAnswerItem):
            answer_items.append(LimitationAnswerItemResponse(text=item.text))

    return AskResponse(
        status=answer.status,
        answer_items=answer_items,
        citations=[_to_citation_response(citation) for citation in answer.citations],
    )


def _to_citation_response(citation: Citation) -> CitationResponse:
    return CitationResponse(
        id=str(citation.id),
        document_id=str(citation.document_id),
        source_id=str(citation.source_id),
        document_version=citation.source_revision,
        document_type=citation.document_type,
        title=citation.title,
        section=citation.section,
        excerpt=citation.excerpt,
        source_url=citation.source_url,
    )


app = create_app()
