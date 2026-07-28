"""Create versioned public portfolio content snapshots.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE portfolio_content_snapshots (
            id UUID PRIMARY KEY,
            revision INTEGER NOT NULL CHECK (revision > 0),
            profile_pt_br JSONB NOT NULL,
            profile_en_us JSONB NOT NULL,
            experiences_pt_br JSONB NOT NULL,
            experiences_en_us JSONB NOT NULL,
            projects_pt_br JSONB NOT NULL,
            projects_en_us JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE portfolio_content_snapshots")
