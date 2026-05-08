"""add passage table

Revision ID: 004
Revises: 003
Create Date: 2026-05-08

Stores user-submitted passages. Two ingestion paths per Epic #4:
paste-text (INGEST-1, this PR) and PDF upload (INGEST-2 #14). Both
land here with `source_type` distinguishing them. `text_hash` is the
content-addressable key the comprehension cache (#18) uses to find
LLM-generated questions for the same text across users.

UUID handling mirrors revision 003: native on Postgres, CHAR(36) on
SQLite for the in-memory test database. `source_type` carries a CHECK
constraint that both dialects accept.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    uuid_type: sa.types.TypeEngine = sa.Uuid() if is_pg else sa.String(length=36)

    op.create_table(
        "passage",
        sa.Column(
            "id",
            uuid_type,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()") if is_pg else None,
        ),
        sa.Column(
            "user_id",
            uuid_type,
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.LargeBinary(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_filename", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_type IN ('paste', 'pdf')",
            name="passage_source_type_check",
        ),
    )

    # The reading-history view will list passages newest-first per user.
    # A composite (user_id, created_at DESC) index serves that query
    # without a separate sort step.
    op.create_index(
        "ix_passage_user_id_created_at",
        "passage",
        ["user_id", sa.text("created_at DESC")],
    )
    # text_hash is the cache lookup key; index it for the cross-user
    # "have we seen this passage before" path.
    op.create_index("ix_passage_text_hash", "passage", ["text_hash"])


def downgrade() -> None:
    op.drop_index("ix_passage_text_hash", table_name="passage")
    op.drop_index("ix_passage_user_id_created_at", table_name="passage")
    op.drop_table("passage")
