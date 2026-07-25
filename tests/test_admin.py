from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import SecretStr

from ask_about_me.admin import AdminCaseStudyDraft
from ask_about_me.app import create_app
from ask_about_me.case_studies import CaseStudySection, PublishedCaseStudy
from ask_about_me.config import Settings


class RecordingAdminCaseStudies:
    def __init__(self, case_study: PublishedCaseStudy | None = None) -> None:
        self.published: list[AdminCaseStudyDraft] = []
        self.case_study = case_study

    async def list_case_studies(self) -> tuple[PublishedCaseStudy, ...]:
        return ()

    async def get_case_study(self, slug: str) -> PublishedCaseStudy:
        if self.case_study is None or self.case_study.slug != slug:
            raise LookupError(slug)
        return self.case_study

    async def get_current(self, slug: str) -> PublishedCaseStudy:
        return await self.get_case_study(slug)

    async def publish_case_study(self, draft: AdminCaseStudyDraft) -> PublishedCaseStudy:
        self.published.append(draft)
        return PublishedCaseStudy(
            id=uuid4(),
            revision=1,
            slug=draft.slug,
            title_pt_br=draft.title_pt_br,
            title_en_us=draft.title_en_us,
            sections=draft.sections,
        )


def admin_settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://unused:unused@localhost/unused",
        openai_api_key=None,
        admin_password=SecretStr("admin-password"),
        admin_session_secret=SecretStr("test-session-secret"),
        admin_cookie_secure=False,
    )


def publish_payload() -> dict[str, object]:
    return {
        "slug": "produto-de-exemplo",
        "titlePtBr": "Produto de exemplo",
        "titleEnUs": "Example product",
        "expectedCurrentRevision": None,
        "sections": [
            {
                "position": 0,
                "headingPtBr": "Contexto",
                "headingEnUs": "Context",
                "bodyPtBr": "Contexto público e verificável.",
                "bodyEnUs": "Public and verifiable context.",
            }
        ],
    }


def test_admin_requires_an_authenticated_session() -> None:
    app = create_app(admin_settings(), admin_case_studies=RecordingAdminCaseStudies())
    with TestClient(app) as client:
        response = client.get("/admin/case-studies")

    assert response.status_code == 401
    assert response.json() == {"detail": "admin authentication required"}


def test_admin_is_unavailable_without_owner_credentials() -> None:
    settings = Settings(database_url="postgresql+psycopg://unused:unused@localhost/unused")
    with TestClient(create_app(settings)) as client:
        response = client.post("/admin/session", json={"password": "any-password"})

    assert response.status_code == 503
    assert response.json() == {"detail": "admin is not configured"}


def test_admin_can_authenticate_before_openai_is_configured() -> None:
    with TestClient(create_app(admin_settings())) as client:
        login = client.post("/admin/session", json={"password": "admin-password"})
        listing = client.get("/admin/case-studies")

    assert login.status_code == 204
    assert listing.status_code == 503
    assert listing.json() == {"detail": "admin publishing is unavailable"}


def test_admin_logs_in_and_publishes_a_bilingual_case_study() -> None:
    service = RecordingAdminCaseStudies()
    with TestClient(create_app(admin_settings(), admin_case_studies=service)) as client:
        login = client.post("/admin/session", json={"password": "admin-password"})
        csrf = client.get("/admin/csrf")
        publish = client.post(
            "/admin/case-studies",
            json=publish_payload(),
            headers={"X-CSRF-Token": csrf.json()["token"]},
        )

    assert login.status_code == 204
    assert csrf.status_code == 200
    assert publish.status_code == 201
    published = publish.json()
    assert isinstance(published["id"], str)
    assert published == {
        "id": published["id"],
        "revision": 1,
        "slug": "produto-de-exemplo",
        "titlePtBr": "Produto de exemplo",
        "titleEnUs": "Example product",
        "sections": [
            {
                "position": 0,
                "headingPtBr": "Contexto",
                "headingEnUs": "Context",
                "bodyPtBr": "Contexto público e verificável.",
                "bodyEnUs": "Public and verifiable context.",
            }
        ],
    }
    assert service.published[0].sections == (
        CaseStudySection(
            position=0,
            heading_pt_br="Contexto",
            heading_en_us="Context",
            body_pt_br="Contexto público e verificável.",
            body_en_us="Public and verifiable context.",
        ),
    )


def test_admin_rejects_a_mutation_without_a_valid_csrf_token() -> None:
    app = create_app(admin_settings(), admin_case_studies=RecordingAdminCaseStudies())
    with TestClient(app) as client:
        client.post("/admin/session", json={"password": "admin-password"})
        response = client.post("/admin/case-studies", json=publish_payload())

    assert response.status_code == 403
    assert response.json() == {"detail": "invalid CSRF token"}


def test_admin_rejects_non_contiguous_section_positions() -> None:
    payload = publish_payload()
    payload["sections"] = [
        {
            "position": 1,
            "headingPtBr": "Contexto",
            "headingEnUs": "Context",
            "bodyPtBr": "Contexto público e verificável.",
            "bodyEnUs": "Public and verifiable context.",
        }
    ]
    with TestClient(
        create_app(admin_settings(), admin_case_studies=RecordingAdminCaseStudies())
    ) as client:
        client.post("/admin/session", json={"password": "admin-password"})
        csrf = client.get("/admin/csrf")
        response = client.post(
            "/admin/case-studies",
            json=payload,
            headers={"X-CSRF-Token": csrf.json()["token"]},
        )

    assert response.status_code == 422


def test_public_case_study_returns_the_requested_locale() -> None:
    case_study = PublishedCaseStudy(
        id=uuid4(),
        revision=3,
        slug="produto-de-exemplo",
        title_pt_br="Produto de exemplo",
        title_en_us="Example product",
        sections=(
            CaseStudySection(
                position=0,
                heading_pt_br="Contexto",
                heading_en_us="Context",
                body_pt_br="Contexto público e verificável.",
                body_en_us="Public and verifiable context.",
            ),
        ),
    )
    reader = RecordingAdminCaseStudies(case_study)
    with TestClient(create_app(admin_settings(), case_study_reader=reader)) as client:
        response = client.get("/case-studies/produto-de-exemplo?locale=en-US")

    assert response.status_code == 200
    assert response.json() == {
        "slug": "produto-de-exemplo",
        "revision": 3,
        "locale": "en-US",
        "title": "Example product",
        "sections": [
            {
                "position": 0,
                "heading": "Context",
                "body": "Public and verifiable context.",
            }
        ],
    }
