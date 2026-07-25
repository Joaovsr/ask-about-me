from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ask_about_me.db import Database
from ask_about_me.knowledge_base import (
    PostgresKnowledgeBase,
    ProjectedKbDocument,
    ProjectedSection,
)
from ask_about_me.rag import DocumentType


@dataclass(frozen=True, slots=True)
class CaseStudySection:
    position: int
    heading_pt_br: str
    heading_en_us: str
    body_pt_br: str
    body_en_us: str


@dataclass(frozen=True, slots=True)
class PublishedCaseStudy:
    id: UUID
    revision: int
    slug: str
    title_pt_br: str
    title_en_us: str
    sections: tuple[CaseStudySection, ...]


@dataclass(slots=True)
class _CaseStudyDraft:
    id: UUID
    revision: int
    slug: str
    title_pt_br: str
    title_en_us: str
    sections: list[CaseStudySection]


class CaseStudyNotFoundError(LookupError):
    pass


class CaseStudyReader(Protocol):
    async def get_current(self, slug: str) -> PublishedCaseStudy: ...


class StaleCaseStudyRevisionError(RuntimeError):
    def __init__(self, *, expected: int | None, actual: int | None) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"current Case Study revision changed: expected {expected}, found {actual}"
        )


class CaseStudyIdentityConflictError(RuntimeError):
    pass


class PostgresCaseStudyCatalog:
    def __init__(self, *, database: Database) -> None:
        self._database = database

    async def get_current(self, slug: str) -> PublishedCaseStudy:
        async with self._database.connect() as connection:
            result = await connection.execute(
                text(
                    """
                    SELECT
                        case_study.id,
                        case_study.slug,
                        revision.revision,
                        revision.title_pt_br,
                        revision.title_en_us,
                        section.position,
                        section.heading_pt_br,
                        section.heading_en_us,
                        section.body_pt_br,
                        section.body_en_us
                    FROM case_studies AS case_study
                    JOIN case_study_revisions AS revision
                        ON revision.case_study_id = case_study.id
                        AND revision.revision = case_study.current_revision
                    JOIN case_study_sections AS section
                        ON section.case_study_id = revision.case_study_id
                        AND section.revision = revision.revision
                    WHERE case_study.slug = :slug
                    ORDER BY section.position
                    """
                ),
                {"slug": slug},
            )
            rows = result.all()

        if not rows:
            raise CaseStudyNotFoundError(slug)
        first = rows[0]
        return PublishedCaseStudy(
            id=first.id,
            revision=first.revision,
            slug=first.slug,
            title_pt_br=first.title_pt_br,
            title_en_us=first.title_en_us,
            sections=tuple(
                CaseStudySection(
                    position=row.position,
                    heading_pt_br=row.heading_pt_br,
                    heading_en_us=row.heading_en_us,
                    body_pt_br=row.body_pt_br,
                    body_en_us=row.body_en_us,
                )
                for row in rows
            ),
        )

    async def list_current(self) -> tuple[PublishedCaseStudy, ...]:
        async with self._database.connect() as connection:
            result = await connection.execute(
                text(
                    """
                    SELECT
                        case_study.id,
                        case_study.slug,
                        revision.revision,
                        revision.title_pt_br,
                        revision.title_en_us,
                        section.position,
                        section.heading_pt_br,
                        section.heading_en_us,
                        section.body_pt_br,
                        section.body_en_us
                    FROM case_studies AS case_study
                    JOIN case_study_revisions AS revision
                        ON revision.case_study_id = case_study.id
                        AND revision.revision = case_study.current_revision
                    JOIN case_study_sections AS section
                        ON section.case_study_id = revision.case_study_id
                        AND section.revision = revision.revision
                    ORDER BY case_study.slug, section.position
                    """
                )
            )
            rows = result.all()

        drafts: dict[UUID, _CaseStudyDraft] = {}
        for row in rows:
            draft = drafts.setdefault(
                row.id,
                _CaseStudyDraft(
                    id=row.id,
                    revision=row.revision,
                    slug=row.slug,
                    title_pt_br=row.title_pt_br,
                    title_en_us=row.title_en_us,
                    sections=[],
                ),
            )
            draft.sections.append(
                CaseStudySection(
                    position=row.position,
                    heading_pt_br=row.heading_pt_br,
                    heading_en_us=row.heading_en_us,
                    body_pt_br=row.body_pt_br,
                    body_en_us=row.body_en_us,
                )
            )
        return tuple(
            PublishedCaseStudy(
                id=draft.id,
                revision=draft.revision,
                slug=draft.slug,
                title_pt_br=draft.title_pt_br,
                title_en_us=draft.title_en_us,
                sections=tuple(draft.sections),
            )
            for draft in drafts.values()
        )


class CaseStudyProjector:
    def project(self, case_study: PublishedCaseStudy) -> ProjectedKbDocument:
        return ProjectedKbDocument(
            source_id=case_study.id,
            source_revision=case_study.revision,
            doc_type=DocumentType.CASE_STUDY,
            title=case_study.title_pt_br,
            slug=case_study.slug,
            source_url=(
                f"/case-studies/{case_study.slug}?locale=pt-BR&version={case_study.revision}"
            ),
            sections=tuple(
                ProjectedSection(name=section.heading_pt_br, text=section.body_pt_br)
                for section in case_study.sections
            ),
        )


class CaseStudyPublisher:
    def __init__(
        self,
        *,
        database: Database,
        knowledge_base: PostgresKnowledgeBase,
    ) -> None:
        self._database = database
        self._knowledge_base = knowledge_base
        self._projector = CaseStudyProjector()

    async def publish(
        self,
        case_study: PublishedCaseStudy,
        *,
        expected_current_revision: int | None,
        expected_active_generation: UUID | None,
    ) -> UUID:
        self._validate(case_study, expected_current_revision=expected_current_revision)
        prepared_index = await self._knowledge_base.prepare_index(
            (self._projector.project(case_study),)
        )

        async with self._database.transaction() as connection:
            await connection.execute(text("LOCK TABLE case_studies IN EXCLUSIVE MODE"))
            current_revision = await self._find_current_revision(connection, case_study)
            if current_revision != expected_current_revision:
                raise StaleCaseStudyRevisionError(
                    expected=expected_current_revision,
                    actual=current_revision,
                )

            await self._write_revision(
                connection,
                case_study,
                is_new=current_revision is None,
            )
            await self._knowledge_base.activate_prepared_sources(
                connection,
                prepared_index,
                expected_active_generation=expected_active_generation,
            )

        return prepared_index.id

    @staticmethod
    def _validate(
        case_study: PublishedCaseStudy,
        *,
        expected_current_revision: int | None,
    ) -> None:
        if case_study.revision < 1:
            raise ValueError("Case Study revision must be positive")
        expected_revision = (
            1 if expected_current_revision is None else expected_current_revision + 1
        )
        if case_study.revision != expected_revision:
            raise ValueError("Case Study revision must advance by exactly one")
        if (
            not case_study.slug.strip()
            or not case_study.title_pt_br.strip()
            or not case_study.title_en_us.strip()
        ):
            raise ValueError("Case Study requires slug and both localized titles")
        if not case_study.sections:
            raise ValueError("Case Study requires at least one localized section")
        if [section.position for section in case_study.sections] != list(
            range(len(case_study.sections))
        ):
            raise ValueError("Case Study section positions must be contiguous")
        if any(
            not value.strip()
            for section in case_study.sections
            for value in (
                section.heading_pt_br,
                section.heading_en_us,
                section.body_pt_br,
                section.body_en_us,
            )
        ):
            raise ValueError("Case Study sections require both locales")

    @staticmethod
    async def _find_current_revision(
        connection: AsyncConnection,
        case_study: PublishedCaseStudy,
    ) -> int | None:
        result = await connection.execute(
            text(
                """
                SELECT id, slug, current_revision
                FROM case_studies
                WHERE id = :id OR slug = :slug
                """
            ),
            {"id": case_study.id, "slug": case_study.slug},
        )
        row = result.one_or_none()
        if row is None:
            return None
        if row.id != case_study.id or row.slug != case_study.slug:
            raise CaseStudyIdentityConflictError(case_study.slug)
        return int(row.current_revision)

    async def _write_revision(
        self,
        connection: AsyncConnection,
        case_study: PublishedCaseStudy,
        *,
        is_new: bool,
    ) -> None:
        if is_new:
            await connection.execute(
                text(
                    """
                    INSERT INTO case_studies (id, slug, current_revision)
                    VALUES (:id, :slug, :revision)
                    """
                ),
                {
                    "id": case_study.id,
                    "slug": case_study.slug,
                    "revision": case_study.revision,
                },
            )

        await connection.execute(
            text(
                """
                INSERT INTO case_study_revisions (
                    case_study_id, revision, title_pt_br, title_en_us
                ) VALUES (
                    :case_study_id, :revision, :title_pt_br, :title_en_us
                )
                """
            ),
            {
                "case_study_id": case_study.id,
                "revision": case_study.revision,
                "title_pt_br": case_study.title_pt_br.strip(),
                "title_en_us": case_study.title_en_us.strip(),
            },
        )
        await connection.execute(
            text(
                """
                INSERT INTO case_study_sections (
                    case_study_id, revision, position,
                    heading_pt_br, heading_en_us, body_pt_br, body_en_us
                ) VALUES (
                    :case_study_id, :revision, :position,
                    :heading_pt_br, :heading_en_us, :body_pt_br, :body_en_us
                )
                """
            ),
            [
                {
                    "case_study_id": case_study.id,
                    "revision": case_study.revision,
                    "position": section.position,
                    "heading_pt_br": section.heading_pt_br.strip(),
                    "heading_en_us": section.heading_en_us.strip(),
                    "body_pt_br": section.body_pt_br.strip(),
                    "body_en_us": section.body_en_us.strip(),
                }
                for section in case_study.sections
            ],
        )

        if not is_new:
            await connection.execute(
                text(
                    """
                    UPDATE case_studies
                    SET current_revision = :revision, updated_at = NOW()
                    WHERE id = :id
                    """
                ),
                {"id": case_study.id, "revision": case_study.revision},
            )
