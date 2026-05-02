"""add comprehension question cache

Revision ID: 002
Revises: 001
Create Date: 2026-05-02

Cost-containment foundation for the Anthropic Claude path. Per ADR-001,
every comprehension-question request must check this cache first; the
composite primary key makes re-reads free at the LLM layer.

JSONB on Postgres (production) for indexability; falls back to JSON on
SQLite for the in-memory test database.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    json_type: sa.types.TypeEngine = (
        postgresql.JSONB() if bind.dialect.name == "postgresql" else sa.JSON()
    )

    op.create_table(
        "comprehension_question_cache",
        sa.Column("passage_hash", sa.LargeBinary(), nullable=False),
        sa.Column("question_type", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Integer(), nullable=False),
        sa.Column("questions", json_type, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "passage_hash",
            "question_type",
            "model_id",
            "prompt_version",
            name="comprehension_question_cache_pkey",
        ),
    )


def downgrade() -> None:
    op.drop_table("comprehension_question_cache")
