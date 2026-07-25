"""Create the Knowledge Base schema.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE kb_index_generations (
            id UUID PRIMARY KEY,
            is_active BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_kb_index_generations_active
        ON kb_index_generations ((is_active))
        WHERE is_active
        """
    )
    op.execute(
        """
        CREATE TABLE kb_documents (
            id UUID PRIMARY KEY,
            source_id UUID NOT NULL,
            source_revision INTEGER NOT NULL CHECK (source_revision > 0),
            index_generation UUID NOT NULL REFERENCES kb_index_generations(id) ON DELETE CASCADE,
            doc_type TEXT NOT NULL CHECK (doc_type IN ('case_study', 'profile', 'essay')),
            title TEXT NOT NULL CHECK (title <> ''),
            slug TEXT NOT NULL CHECK (slug <> ''),
            source_url TEXT NOT NULL CHECK (source_url <> ''),
            canonical_text TEXT NOT NULL CHECK (canonical_text <> ''),
            UNIQUE (source_id, source_revision, index_generation)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_kb_documents_index_generation
        ON kb_documents (index_generation)
        """
    )
    op.execute(
        """
        CREATE TABLE kb_chunks (
            id UUID PRIMARY KEY,
            document_id UUID NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
            position INTEGER NOT NULL CHECK (position >= 0),
            section TEXT NOT NULL CHECK (section <> ''),
            content TEXT NOT NULL CHECK (content <> ''),
            embedding VECTOR NOT NULL,
            search_vector TSVECTOR GENERATED ALWAYS AS (
                to_tsvector('portuguese'::regconfig, content)
            ) STORED,
            UNIQUE (document_id, position)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_kb_chunks_search_vector
        ON kb_chunks USING GIN (search_vector)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE kb_chunks")
    op.execute("DROP TABLE kb_documents")
    op.execute("DROP TABLE kb_index_generations")
