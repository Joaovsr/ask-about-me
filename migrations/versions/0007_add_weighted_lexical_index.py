"""Add generation-versioned weighted lexical search.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE kb_index_generations
        ADD COLUMN lexical_strategy_version TEXT NOT NULL
            DEFAULT 'legacy-content-only-v1'
        """
    )
    op.execute(
        """
        ALTER TABLE kb_chunks
        ADD COLUMN lexical_search_vector TSVECTOR
        """
    )
    op.execute(
        """
        UPDATE kb_chunks AS chunk
        SET lexical_search_vector =
            setweight(to_tsvector('portuguese', document.title), 'A')
            || setweight(to_tsvector('portuguese', chunk.section), 'B')
            || setweight(to_tsvector('portuguese', chunk.content), 'D')
        FROM kb_documents AS document
        WHERE document.id = chunk.document_id
        """
    )
    op.execute(
        """
        ALTER TABLE kb_chunks
        ALTER COLUMN lexical_search_vector SET NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX ix_kb_chunks_lexical_search_vector
        ON kb_chunks USING GIN (lexical_search_vector)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_kb_chunks_lexical_search_vector")
    op.execute("ALTER TABLE kb_chunks DROP COLUMN lexical_search_vector")
    op.execute(
        """
        ALTER TABLE kb_index_generations
        DROP COLUMN lexical_strategy_version
        """
    )
