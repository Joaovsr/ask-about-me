"""Create versioned Case Studies.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE case_studies (
            id UUID PRIMARY KEY,
            slug TEXT NOT NULL UNIQUE CHECK (slug <> ''),
            current_revision INTEGER NOT NULL CHECK (current_revision > 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE case_study_revisions (
            case_study_id UUID NOT NULL REFERENCES case_studies(id) ON DELETE CASCADE,
            revision INTEGER NOT NULL CHECK (revision > 0),
            title_pt_br TEXT NOT NULL CHECK (title_pt_br <> ''),
            title_en_us TEXT NOT NULL CHECK (title_en_us <> ''),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (case_study_id, revision)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE case_study_sections (
            case_study_id UUID NOT NULL,
            revision INTEGER NOT NULL,
            position INTEGER NOT NULL CHECK (position >= 0),
            heading_pt_br TEXT NOT NULL CHECK (heading_pt_br <> ''),
            heading_en_us TEXT NOT NULL CHECK (heading_en_us <> ''),
            body_pt_br TEXT NOT NULL CHECK (body_pt_br <> ''),
            body_en_us TEXT NOT NULL CHECK (body_en_us <> ''),
            PRIMARY KEY (case_study_id, revision, position),
            FOREIGN KEY (case_study_id, revision)
                REFERENCES case_study_revisions(case_study_id, revision)
                ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        ALTER TABLE case_studies
        ADD CONSTRAINT fk_case_studies_current_revision
        FOREIGN KEY (id, current_revision)
        REFERENCES case_study_revisions(case_study_id, revision)
        DEFERRABLE INITIALLY DEFERRED
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE case_study_sections")
    op.execute("ALTER TABLE case_studies DROP CONSTRAINT fk_case_studies_current_revision")
    op.execute("DROP TABLE case_study_revisions")
    op.execute("DROP TABLE case_studies")
