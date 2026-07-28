import json
from dataclasses import dataclass
from typing import Any, Protocol, cast
from uuid import UUID, uuid5

from sqlalchemy import text

from ask_about_me.db import Database
from ask_about_me.knowledge_base import (
    PostgresKnowledgeBase,
    ProjectedKbDocument,
    ProjectedSection,
)
from ask_about_me.rag import DocumentType, Locale

PORTFOLIO_SNAPSHOT_ID = UUID("b5a1ad00-8638-48b4-9a71-d9d0142f75cd")
_PORTFOLIO_NAMESPACE = UUID("4b3e35eb-ce60-4c21-b65c-7b6608f16180")
_PROFILE_FIELDS = frozenset(
    {
        "name",
        "nameShort",
        "email",
        "avatar",
        "brand",
        "careerStart",
        "github",
        "linkedin",
        "role",
        "roleSub",
        "location",
        "tagline",
        "aboutLead",
        "aboutBody",
        "differentials",
        "openTo",
        "languages",
    }
)
_EXPERIENCE_FIELDS = frozenset(
    {"slug", "company", "startDate", "finishDate", "skills", "role", "description"}
)
_PROJECT_FIELDS = frozenset(
    {
        "slug",
        "title",
        "description",
        "problem",
        "solution",
        "result",
        "technologies",
        "status",
        "images",
    }
)


@dataclass(frozen=True, slots=True)
class LocalizedPortfolioContent:
    profile: dict[str, Any]
    experiences: tuple[dict[str, Any], ...]
    projects: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class PublishedPortfolioSnapshot:
    id: UUID
    revision: int
    pt_br: LocalizedPortfolioContent
    en_us: LocalizedPortfolioContent


class PortfolioContentReader(Protocol):
    async def get_current(self) -> PublishedPortfolioSnapshot: ...

    async def get_revision(self, revision: int) -> PublishedPortfolioSnapshot: ...


class PortfolioContentNotFoundError(LookupError):
    pass


class StalePortfolioContentRevisionError(RuntimeError):
    pass


class PostgresPortfolioContentCatalog:
    def __init__(self, *, database: Database) -> None:
        self._database = database

    async def get_current(self) -> PublishedPortfolioSnapshot:
        return await self._get_snapshot(
            "WHERE id = :id AND is_current", {"id": PORTFOLIO_SNAPSHOT_ID}
        )

    async def get_revision(self, revision: int) -> PublishedPortfolioSnapshot:
        return await self._get_snapshot(
            "WHERE id = :id AND revision = :revision",
            {"id": PORTFOLIO_SNAPSHOT_ID, "revision": revision},
        )

    async def _get_snapshot(
        self,
        where_clause: str,
        parameters: dict[str, object],
    ) -> PublishedPortfolioSnapshot:
        async with self._database.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        f"""
                        SELECT id, revision, profile_pt_br, profile_en_us,
                               experiences_pt_br, experiences_en_us,
                               projects_pt_br, projects_en_us
                        FROM portfolio_content_snapshots
                        {where_clause}
                        """
                    ),
                    parameters,
                )
            ).one_or_none()
        if row is None:
            raise PortfolioContentNotFoundError
        return PublishedPortfolioSnapshot(
            id=row.id,
            revision=row.revision,
            pt_br=_localized_content(
                profile=row.profile_pt_br,
                experiences=row.experiences_pt_br,
                projects=row.projects_pt_br,
            ),
            en_us=_localized_content(
                profile=row.profile_en_us,
                experiences=row.experiences_en_us,
                projects=row.projects_en_us,
            ),
        )


class PortfolioContentProjector:
    def project(self, snapshot: PublishedPortfolioSnapshot) -> tuple[ProjectedKbDocument, ...]:
        documents = [self._profile_document(snapshot)]
        documents.extend(self._experience_documents(snapshot))
        documents.extend(self._project_documents(snapshot))
        return tuple(documents)

    def _profile_document(self, snapshot: PublishedPortfolioSnapshot) -> ProjectedKbDocument:
        profile = snapshot.pt_br.profile
        return ProjectedKbDocument(
            source_id=_source_id("profile"),
            source_revision=snapshot.revision,
            doc_type=DocumentType.PROFILE,
            title=str(profile["name"]),
            slug="perfil",
            source_url=f"/portfolio?locale=pt-BR&version={snapshot.revision}",
            sections=(
                ProjectedSection(name="Resumo", text=str(profile["aboutLead"])),
                ProjectedSection(name="Atuação", text=str(profile["aboutBody"])),
            ),
        )

    def _experience_documents(
        self, snapshot: PublishedPortfolioSnapshot
    ) -> tuple[ProjectedKbDocument, ...]:
        return tuple(
            ProjectedKbDocument(
                source_id=_source_id(f"experience:{experience['slug']}"),
                source_revision=snapshot.revision,
                doc_type=DocumentType.PROFILE,
                title=f"{experience['role']} — {experience['company']}",
                slug=str(experience["slug"]),
                source_url=(
                    f"/portfolio?locale=pt-BR&experience={experience['slug']}"
                    f"&version={snapshot.revision}"
                ),
                sections=(
                    ProjectedSection(name="Experiência", text=str(experience["description"])),
                ),
            )
            for experience in snapshot.pt_br.experiences
        )

    def _project_documents(
        self, snapshot: PublishedPortfolioSnapshot
    ) -> tuple[ProjectedKbDocument, ...]:
        return tuple(
            ProjectedKbDocument(
                source_id=_source_id(f"project:{project['slug']}"),
                source_revision=snapshot.revision,
                doc_type=DocumentType.PROFILE,
                title=str(project["title"]),
                slug=str(project["slug"]),
                source_url=(
                    f"/portfolio?locale=pt-BR&project={project['slug']}&version={snapshot.revision}"
                ),
                sections=(
                    ProjectedSection(name="Resumo", text=str(project["description"])),
                    ProjectedSection(name="Problema", text=str(project["problem"])),
                    ProjectedSection(name="Solução", text=str(project["solution"])),
                    ProjectedSection(name="Resultado", text=str(project["result"])),
                ),
            )
            for project in snapshot.pt_br.projects
        )


class PortfolioContentPublisher:
    def __init__(self, *, database: Database, knowledge_base: PostgresKnowledgeBase) -> None:
        self._database = database
        self._knowledge_base = knowledge_base
        self._projector = PortfolioContentProjector()

    async def publish(
        self,
        snapshot: PublishedPortfolioSnapshot,
        *,
        expected_current_revision: int | None,
        expected_active_generation: UUID | None,
    ) -> UUID:
        _validate_snapshot(snapshot, expected_current_revision=expected_current_revision)
        prepared_index = await self._knowledge_base.prepare_index(self._projector.project(snapshot))
        async with self._database.transaction() as connection:
            current_revision = await self._current_revision(connection)
            if current_revision != expected_current_revision:
                raise StalePortfolioContentRevisionError
            if current_revision is not None:
                await connection.execute(
                    text(
                        """
                        UPDATE portfolio_content_snapshots
                        SET is_current = FALSE
                        WHERE id = :id AND is_current
                        """
                    ),
                    {"id": PORTFOLIO_SNAPSHOT_ID},
                )
            await connection.execute(
                text(
                    """
                    INSERT INTO portfolio_content_snapshots (
                        id, revision, profile_pt_br, profile_en_us,
                        experiences_pt_br, experiences_en_us, projects_pt_br, projects_en_us,
                        is_current
                    ) VALUES (
                        :id, :revision,
                        CAST(:profile_pt_br AS jsonb), CAST(:profile_en_us AS jsonb),
                        CAST(:experiences_pt_br AS jsonb), CAST(:experiences_en_us AS jsonb),
                        CAST(:projects_pt_br AS jsonb), CAST(:projects_en_us AS jsonb), TRUE
                    )
                    """
                ),
                _snapshot_parameters(snapshot),
            )
            await self._knowledge_base.activate_prepared_sources(
                connection,
                prepared_index,
                expected_active_generation=expected_active_generation,
            )
        return prepared_index.id

    async def _current_revision(self, connection: Any) -> int | None:
        result = await connection.execute(
            text(
                """
                SELECT revision
                FROM portfolio_content_snapshots
                WHERE id = :id AND is_current
                FOR UPDATE
                """
            ),
            {"id": PORTFOLIO_SNAPSHOT_ID},
        )
        return cast(int | None, result.scalar_one_or_none())


def select_locale(
    snapshot: PublishedPortfolioSnapshot, locale: Locale
) -> LocalizedPortfolioContent:
    return snapshot.pt_br if locale is Locale.PT_BR else snapshot.en_us


def _localized_content(
    *, profile: dict[str, Any], experiences: list[dict[str, Any]], projects: list[dict[str, Any]]
) -> LocalizedPortfolioContent:
    return LocalizedPortfolioContent(
        profile=profile,
        experiences=tuple(experiences),
        projects=tuple(projects),
    )


def _source_id(kind: str) -> UUID:
    return uuid5(_PORTFOLIO_NAMESPACE, kind)


def _validate_snapshot(
    snapshot: PublishedPortfolioSnapshot, *, expected_current_revision: int | None
) -> None:
    if snapshot.id != PORTFOLIO_SNAPSHOT_ID:
        raise ValueError("portfolio snapshot has an unexpected identity")
    expected_revision = 1 if expected_current_revision is None else expected_current_revision + 1
    if snapshot.revision != expected_revision:
        raise ValueError("portfolio snapshot revision must advance by exactly one")
    for localized in (snapshot.pt_br, snapshot.en_us):
        _validate_localized_content(localized)
    if _slugs(snapshot.pt_br.experiences) != _slugs(snapshot.en_us.experiences):
        raise ValueError("portfolio snapshot locales require the same experience slugs")
    if _slugs(snapshot.pt_br.projects) != _slugs(snapshot.en_us.projects):
        raise ValueError("portfolio snapshot locales require the same project slugs")


def _validate_localized_content(content: LocalizedPortfolioContent) -> None:
    _validate_record(content.profile, _PROFILE_FIELDS, "profile")
    if not content.experiences or not content.projects:
        raise ValueError("portfolio snapshot requires experiences and projects in both locales")
    for experience in content.experiences:
        _validate_record(experience, _EXPERIENCE_FIELDS, "experience")
    for project in content.projects:
        _validate_record(project, _PROJECT_FIELDS, "project")


def _validate_record(record: dict[str, Any], required_fields: frozenset[str], kind: str) -> None:
    missing = required_fields - record.keys()
    if missing:
        raise ValueError(f"{kind} is missing required fields: {', '.join(sorted(missing))}")
    if any(
        isinstance(value, str) and not value.strip()
        for field, value in record.items()
        if field in required_fields and field != "finishDate"
    ):
        raise ValueError(f"{kind} requires complete localized text")


def _slugs(records: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    slugs = tuple(str(record["slug"]) for record in records)
    if len(set(slugs)) != len(slugs):
        raise ValueError("portfolio snapshot requires unique slugs")
    return slugs


def _snapshot_parameters(snapshot: PublishedPortfolioSnapshot) -> dict[str, Any]:
    return {
        "id": snapshot.id,
        "revision": snapshot.revision,
        "profile_pt_br": json.dumps(snapshot.pt_br.profile),
        "profile_en_us": json.dumps(snapshot.en_us.profile),
        "experiences_pt_br": json.dumps(snapshot.pt_br.experiences),
        "experiences_en_us": json.dumps(snapshot.en_us.experiences),
        "projects_pt_br": json.dumps(snapshot.pt_br.projects),
        "projects_en_us": json.dumps(snapshot.en_us.projects),
    }
