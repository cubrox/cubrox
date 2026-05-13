"""add rate_bucket table

Revision ID: 006
Revises: 005
Create Date: 2026-05-12

Per-key token bucket for AUTH-4 rate limiting on /login and
/auth/verify. One row per (route, dimension, value) tuple, e.g.:

  - "login:ip:203.0.113.7"
  - "login:email:reader@example.com"
  - "verify:ip:203.0.113.7"
  - "verify:token-prefix:abc12345"

The key is opaque to the schema; the service derives it. Tokens are
stored as float so the linear refill math works without integer
truncation. See app/services/rate_limit.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rate_bucket",
        sa.Column("key", sa.String(length=255), primary_key=True),
        sa.Column("tokens", sa.Float(), nullable=False),
        sa.Column(
            "refilled_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("rate_bucket")
