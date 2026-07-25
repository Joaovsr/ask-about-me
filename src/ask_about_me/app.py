import secrets
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Literal, Self, cast

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ask_about_me.admin import (
    AdminCaseStudyDraft,
    AdminCaseStudyService,
    build_admin_case_study_service,
)
from ask_about_me.case_studies import (
    CaseStudyIdentityConflictError,
    CaseStudyNotFoundError,
    CaseStudyReader,
    CaseStudySection,
    PostgresCaseStudyCatalog,
    PublishedCaseStudy,
    StaleCaseStudyRevisionError,
)
from ask_about_me.composition import build_portfolio_rag
from ask_about_me.config import Settings, get_settings
from ask_about_me.db import Database
from ask_about_me.knowledge_base import StaleIndexGenerationError
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
AdminCaseStudyServiceFactory = Callable[[Settings, Database], AdminCaseStudyService]


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


class AdminLoginRequest(HttpModel):
    password: Annotated[str, StringConstraints(min_length=1, max_length=256)]


class AdminCsrfResponse(HttpModel):
    token: str


class AdminCaseStudySectionRequest(HttpModel):
    position: int = Field(ge=0)
    heading_pt_br: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    heading_en_us: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    body_pt_br: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    body_en_us: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class AdminCaseStudyPublishRequest(HttpModel):
    slug: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=120,
            pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        ),
    ]
    title_pt_br: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    title_en_us: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    expected_current_revision: int | None = Field(default=None, ge=1)
    sections: list[AdminCaseStudySectionRequest] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def enforce_contiguous_section_positions(self) -> Self:
        positions = [section.position for section in self.sections]
        if sorted(positions) != list(range(len(positions))):
            raise ValueError("section positions must be unique and contiguous from zero")
        return self


class AdminCaseStudySectionResponse(HttpModel):
    position: int
    heading_pt_br: str
    heading_en_us: str
    body_pt_br: str
    body_en_us: str


class AdminCaseStudyResponse(HttpModel):
    id: str
    revision: int
    slug: str
    title_pt_br: str
    title_en_us: str
    sections: list[AdminCaseStudySectionResponse]


class PublicCaseStudySectionResponse(HttpModel):
    position: int
    heading: str
    body: str


class PublicCaseStudyResponse(HttpModel):
    slug: str
    revision: int
    locale: Locale
    title: str
    sections: list[PublicCaseStudySectionResponse]


def create_app(
    settings: Settings | None = None,
    *,
    portfolio_rag: PortfolioRag | None = None,
    rag_factory: RagFactory | None = None,
    admin_case_studies: AdminCaseStudyService | None = None,
    admin_case_study_service_factory: AdminCaseStudyServiceFactory | None = None,
    case_study_reader: CaseStudyReader | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    admin_enabled = _has_admin_credentials(resolved_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.database = Database(resolved_settings.database_url)
        app.state.portfolio_rag = portfolio_rag
        app.state.admin_case_studies = admin_case_studies
        app.state.case_study_reader = case_study_reader or PostgresCaseStudyCatalog(
            database=cast(Database, app.state.database)
        )
        if app.state.portfolio_rag is None and _has_openai_api_key(resolved_settings):
            factory = rag_factory or build_portfolio_rag
            app.state.portfolio_rag = factory(
                resolved_settings,
                cast(Database, app.state.database),
            )
        if (
            app.state.admin_case_studies is None
            and admin_enabled
            and _has_openai_api_key(resolved_settings)
        ):
            admin_factory = admin_case_study_service_factory or build_admin_case_study_service
            app.state.admin_case_studies = admin_factory(
                resolved_settings,
                cast(Database, app.state.database),
            )
        try:
            yield
        finally:
            await cast(Database, app.state.database).close()

    app = FastAPI(title="ask-about-me", lifespan=lifespan)
    app.add_middleware(
        SessionMiddleware,
        secret_key=_session_secret_for(resolved_settings),
        max_age=28_800,
        same_site="strict",
        https_only=resolved_settings.admin_cookie_secure,
    )
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

    @app.get("/case-studies/{slug}", response_model=PublicCaseStudyResponse)
    async def get_public_case_study(
        slug: str,
        request: Request,
        locale: Locale = Locale.PT_BR,
    ) -> PublicCaseStudyResponse:
        reader = cast(CaseStudyReader, request.app.state.case_study_reader)
        try:
            case_study = await reader.get_current(slug)
        except CaseStudyNotFoundError as error:
            raise HTTPException(status_code=404, detail="case study not found") from error
        return _to_public_case_study_response(case_study, locale)

    @app.post("/admin/session", status_code=204)
    async def create_admin_session(payload: AdminLoginRequest, request: Request) -> Response:
        _require_admin_configuration(admin_enabled)
        password = resolved_settings.admin_password
        if password is None or not secrets.compare_digest(
            payload.password,
            password.get_secret_value(),
        ):
            raise HTTPException(status_code=401, detail="invalid admin credentials")
        request.session.clear()
        request.session["admin_authenticated"] = True
        request.session["csrf_token"] = secrets.token_urlsafe(32)
        return Response(status_code=204)

    @app.post("/admin/session/logout", status_code=204)
    async def delete_admin_session(request: Request) -> Response:
        _require_admin_session(request, admin_enabled)
        _require_csrf_token(request)
        request.session.clear()
        return Response(status_code=204)

    @app.get("/admin/csrf", response_model=AdminCsrfResponse)
    async def get_admin_csrf_token(request: Request) -> AdminCsrfResponse:
        _require_admin_session(request, admin_enabled)
        token = request.session.get("csrf_token")
        if not isinstance(token, str):
            token = secrets.token_urlsafe(32)
            request.session["csrf_token"] = token
        return AdminCsrfResponse(token=token)

    @app.get("/admin/case-studies", response_model=list[AdminCaseStudyResponse])
    async def list_admin_case_studies(request: Request) -> list[AdminCaseStudyResponse]:
        service = _admin_case_study_service(request, admin_enabled)
        return [
            _to_admin_case_study_response(case_study)
            for case_study in await service.list_case_studies()
        ]

    @app.get("/admin/case-studies/{slug}", response_model=AdminCaseStudyResponse)
    async def get_admin_case_study(slug: str, request: Request) -> AdminCaseStudyResponse:
        service = _admin_case_study_service(request, admin_enabled)
        try:
            case_study = await service.get_case_study(slug)
        except CaseStudyNotFoundError as error:
            raise HTTPException(status_code=404, detail="case study not found") from error
        return _to_admin_case_study_response(case_study)

    @app.post("/admin/case-studies", response_model=AdminCaseStudyResponse, status_code=201)
    async def publish_admin_case_study(
        payload: AdminCaseStudyPublishRequest,
        request: Request,
    ) -> AdminCaseStudyResponse:
        service = _admin_case_study_service(request, admin_enabled)
        _require_csrf_token(request)
        draft = AdminCaseStudyDraft(
            slug=payload.slug,
            title_pt_br=payload.title_pt_br,
            title_en_us=payload.title_en_us,
            expected_current_revision=payload.expected_current_revision,
            sections=tuple(
                CaseStudySection(
                    position=section.position,
                    heading_pt_br=section.heading_pt_br,
                    heading_en_us=section.heading_en_us,
                    body_pt_br=section.body_pt_br,
                    body_en_us=section.body_en_us,
                )
                for section in payload.sections
            ),
        )
        try:
            case_study = await service.publish_case_study(draft)
        except (
            CaseStudyIdentityConflictError,
            StaleCaseStudyRevisionError,
            StaleIndexGenerationError,
        ) as error:
            raise HTTPException(
                status_code=409, detail="content changed; reload before saving"
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except OpenAIProviderUnavailableError as error:
            raise HTTPException(
                status_code=503,
                detail="indexing is temporarily unavailable; the published version was preserved",
            ) from error
        return _to_admin_case_study_response(case_study)

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
    return settings.openai_api_key is not None and bool(
        settings.openai_api_key.get_secret_value().strip()
    )


def _has_admin_credentials(settings: Settings) -> bool:
    return all(
        secret is not None and bool(secret.get_secret_value().strip())
        for secret in (settings.admin_password, settings.admin_session_secret)
    )


def _session_secret_for(settings: Settings) -> str:
    if settings.admin_session_secret is not None:
        value = settings.admin_session_secret.get_secret_value().strip()
        if value:
            return value
    return secrets.token_urlsafe(32)


def _require_admin_configuration(admin_enabled: bool) -> None:
    if not admin_enabled:
        raise HTTPException(status_code=503, detail="admin is not configured")


def _require_admin_session(request: Request, admin_enabled: bool) -> None:
    _require_admin_configuration(admin_enabled)
    if request.session.get("admin_authenticated") is not True:
        raise HTTPException(status_code=401, detail="admin authentication required")


def _require_csrf_token(request: Request) -> None:
    expected = request.session.get("csrf_token")
    supplied = request.headers.get("X-CSRF-Token")
    if not isinstance(expected, str) or not isinstance(supplied, str):
        raise HTTPException(status_code=403, detail="invalid CSRF token")
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=403, detail="invalid CSRF token")


def _admin_case_study_service(
    request: Request,
    admin_enabled: bool,
) -> AdminCaseStudyService:
    _require_admin_session(request, admin_enabled)
    service = cast(AdminCaseStudyService | None, request.app.state.admin_case_studies)
    if service is None:
        raise HTTPException(status_code=503, detail="admin publishing is unavailable")
    return service


def _to_admin_case_study_response(case_study: PublishedCaseStudy) -> AdminCaseStudyResponse:
    return AdminCaseStudyResponse(
        id=str(case_study.id),
        revision=case_study.revision,
        slug=case_study.slug,
        title_pt_br=case_study.title_pt_br,
        title_en_us=case_study.title_en_us,
        sections=[
            AdminCaseStudySectionResponse(
                position=section.position,
                heading_pt_br=section.heading_pt_br,
                heading_en_us=section.heading_en_us,
                body_pt_br=section.body_pt_br,
                body_en_us=section.body_en_us,
            )
            for section in case_study.sections
        ],
    )


def _to_public_case_study_response(
    case_study: PublishedCaseStudy,
    locale: Locale,
) -> PublicCaseStudyResponse:
    is_portuguese = locale is Locale.PT_BR
    return PublicCaseStudyResponse(
        slug=case_study.slug,
        revision=case_study.revision,
        locale=locale,
        title=case_study.title_pt_br if is_portuguese else case_study.title_en_us,
        sections=[
            PublicCaseStudySectionResponse(
                position=section.position,
                heading=section.heading_pt_br if is_portuguese else section.heading_en_us,
                body=section.body_pt_br if is_portuguese else section.body_en_us,
            )
            for section in case_study.sections
        ],
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
