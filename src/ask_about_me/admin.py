from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from ask_about_me.case_studies import (
    CaseStudyNotFoundError,
    CaseStudyPublisher,
    CaseStudySection,
    PostgresCaseStudyCatalog,
    PublishedCaseStudy,
)
from ask_about_me.composition import build_openai_knowledge_base
from ask_about_me.config import Settings
from ask_about_me.db import Database


@dataclass(frozen=True, slots=True)
class AdminCaseStudyDraft:
    slug: str
    title_pt_br: str
    title_en_us: str
    sections: tuple[CaseStudySection, ...]
    expected_current_revision: int | None


class AdminCaseStudyService(Protocol):
    async def list_case_studies(self) -> tuple[PublishedCaseStudy, ...]: ...

    async def get_case_study(self, slug: str) -> PublishedCaseStudy: ...

    async def publish_case_study(self, draft: AdminCaseStudyDraft) -> PublishedCaseStudy: ...


class PostgresAdminCaseStudyService:
    def __init__(
        self,
        *,
        catalog: PostgresCaseStudyCatalog,
        publisher: CaseStudyPublisher,
        knowledge_base_generation_id: Callable[[], Awaitable[UUID | None]],
    ) -> None:
        self._catalog = catalog
        self._publisher = publisher
        self._knowledge_base_generation_id = knowledge_base_generation_id

    async def list_case_studies(self) -> tuple[PublishedCaseStudy, ...]:
        return await self._catalog.list_current()

    async def get_case_study(self, slug: str) -> PublishedCaseStudy:
        return await self._catalog.get_current(slug)

    async def publish_case_study(self, draft: AdminCaseStudyDraft) -> PublishedCaseStudy:
        try:
            current = await self._catalog.get_current(draft.slug)
        except CaseStudyNotFoundError:
            current = None

        revision = (
            1 if draft.expected_current_revision is None else draft.expected_current_revision + 1
        )
        case_study = PublishedCaseStudy(
            id=current.id if current is not None else uuid4(),
            revision=revision,
            slug=draft.slug,
            title_pt_br=draft.title_pt_br,
            title_en_us=draft.title_en_us,
            sections=draft.sections,
        )
        await self._publisher.publish(
            case_study,
            expected_current_revision=draft.expected_current_revision,
            expected_active_generation=await self._knowledge_base_generation_id(),
        )
        return case_study


def build_admin_case_study_service(
    settings: Settings,
    database: Database,
) -> AdminCaseStudyService:
    knowledge_base = build_openai_knowledge_base(settings, database)
    return PostgresAdminCaseStudyService(
        catalog=PostgresCaseStudyCatalog(database=database),
        publisher=CaseStudyPublisher(database=database, knowledge_base=knowledge_base),
        knowledge_base_generation_id=knowledge_base.get_active_generation_id,
    )
