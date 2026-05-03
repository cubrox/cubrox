"""add user and magic_link_token tables

Revision ID: 003
Revises: 002
Create Date: 2026-05-03

Schema for the passwordless magic-link sign-in flow per ADR-002.

  - user: account record. Email is the natural identifier; no password.
  - magic_link_token: short-lived, hashed sign-in token. Single-use,
    15-minute TTL. CASCADE on user delete because tokens are meaningless
    without their owner.

UUID and CITEXT are Postgres-native (citext requires the citext
extension). On SQLite (in-memory test DB) we fall back to TEXT for
both — the application normalises emails to lowercase before insert
either way, so the UNIQUE constraint suffices.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        op.execute("CREATE EXTENSION IF NOT EXISTS citext")
        op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    uuid_type: sa.types.TypeEngine = sa.Uuid() if is_pg else sa.String(length=36)
    email_type: sa.types.TypeEngine = (
        sa.dialects.postgresql.CITEXT() if is_pg else sa.String(length=320)
    )

    op.create_table(
        "user",
        sa.Column(
            "id",
            uuid_type,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()") if is_pg else None,
        ),
        sa.Column("email", email_type, nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "magic_link_token",
        sa.Column("token_hash", sa.LargeBinary(), primary_key=True),
        sa.Column(
            "user_id",
            uuid_type,
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_magic_link_token_user_id",
        "magic_link_token",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_magic_link_token_user_id", table_name="magic_link_token")
    op.drop_table("magic_link_token")
    op.drop_table("user")
