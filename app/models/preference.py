"""Preference model.

Per-user reading-support settings (font, size, contrast, line-height,
etc.). One row per user, identified by `user_id`. The `values` column
is a JSONB blob (JSON on SQLite) so the support toolkit can evolve
without schema changes — new modes ship as new keys, validated against
an allow-list at the route layer (READ-2 #16).

Per the architecture doc, defaults are sourced from
app/services/reading/defaults.py. A user with no Preference row gets
the defaults rendered server-side; the row is only created when they
actually toggle something (READ-2).
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class Preference(SQLModel, table=True):
    __tablename__ = "preference"

    user_id: uuid.UUID = Field(foreign_key="user.id", primary_key=True)
    values: dict[str, Any] = Field(sa_column=sa.Column(sa.JSON, nullable=False, default=dict))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
