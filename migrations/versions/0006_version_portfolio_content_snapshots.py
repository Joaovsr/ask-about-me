"""Keep immutable portfolio content snapshot revisions.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE portfolio_content_snapshots DROP CONSTRAINT portfolio_content_snapshots_pkey"
    )
    op.execute(
        "ALTER TABLE portfolio_content_snapshots "
        "ADD COLUMN is_current BOOLEAN NOT NULL DEFAULT TRUE"
    )
    op.execute("ALTER TABLE portfolio_content_snapshots ADD PRIMARY KEY (id, revision)")
    op.execute(
        "CREATE UNIQUE INDEX portfolio_content_snapshots_one_current "
        "ON portfolio_content_snapshots (id) WHERE is_current"
    )


def downgrade() -> None:
    op.execute("DROP INDEX portfolio_content_snapshots_one_current")
    op.execute(
        "ALTER TABLE portfolio_content_snapshots DROP CONSTRAINT portfolio_content_snapshots_pkey"
    )
    op.execute("ALTER TABLE portfolio_content_snapshots DROP COLUMN is_current")
    op.execute("ALTER TABLE portfolio_content_snapshots ADD PRIMARY KEY (id)")
