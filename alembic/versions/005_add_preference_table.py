"""add preference table

Revision ID: 005
Revises: 004
Create Date: 2026-05-08

Per-user reading preferences. One row per user (PK = user_id). The
`values` column is a JSON-shaped blob so the support toolkit can grow
without schema changes — JSONB on Postgres for index-able queries,
plain JSON on SQLite for the test database.

CASCADE on user delete because preferences are meaningless without
their owner.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    uuid_type: sa.types.TypeEngine = sa.Uuid() if is_pg else sa.String(length=36)
    json_type: sa.types.TypeEngine = postgresql.JSONB() if is_pg else sa.JSON()

    op.create_table(
        "preference",
        sa.Column(
            "user_id",
            uuid_type,
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("values", json_type, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("preference")
