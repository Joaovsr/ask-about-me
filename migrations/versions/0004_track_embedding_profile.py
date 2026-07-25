"""Track the embedding profile for each Knowledge Base generation.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE kb_index_generations
        ADD COLUMN embedding_provider TEXT NOT NULL DEFAULT 'legacy',
        ADD COLUMN embedding_model TEXT NOT NULL DEFAULT 'unknown',
        ADD COLUMN embedding_dimensions INTEGER NOT NULL DEFAULT 1
            CHECK (embedding_dimensions > 0),
        ADD COLUMN chunker_version TEXT NOT NULL DEFAULT 'section-char-v1',
        ADD COLUMN canonical_locale TEXT NOT NULL DEFAULT 'pt-BR'
            CHECK (canonical_locale = 'pt-BR')
        """
    )
    op.execute(
        """
        UPDATE kb_index_generations AS generation
        SET embedding_dimensions = COALESCE(
            (
                SELECT vector_dims(chunk.embedding)
                FROM kb_documents AS document
                JOIN kb_chunks AS chunk ON chunk.document_id = document.id
                WHERE document.index_generation = generation.id
                LIMIT 1
            ),
            1
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE kb_index_generations
        DROP COLUMN canonical_locale,
        DROP COLUMN chunker_version,
        DROP COLUMN embedding_dimensions,
        DROP COLUMN embedding_model,
        DROP COLUMN embedding_provider
        """
    )
