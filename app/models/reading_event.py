"""ReadingEvent model.

Append-only record of "a user finished reading some lines of a
passage". METRIC-2 (#22) writes one row per beacon dispatched on
passage-close. METRIC-3 (#23) aggregates them for the "100,000 lines
processed in three months" PRD success metric.

Design choices:
  - Append-only: no `updated_at` column, no UPDATE path anywhere.
    Reading is observed, not edited.
  - `lines_processed` is `INT NOT NULL, CHECK >= 1` — every event
    must claim at least one line. Zero would just be noise.
  - `occurred_at` is server-defaulted to `now()` so the writer in
    METRIC-2 can rely on the database's clock (consistent across
    Cloud Run instances).
  - `owner_id` references `auth.users(id)` in Supabase — FK lives in
    the SQL migration, not on the SQLModel field (auth schema is
    cross-schema and not SQLModel-managed).
  - `passage_id` keeps its SQLModel FK to the local `passage` table.

Indexes:
  - `ix_reading_event_occurred_at` for the date-range aggregate in
    METRIC-3. No composite (owner_id, occurred_at) index yet — the
    aggregate is cross-user, and adding indexes ahead of an
    observed query is premature.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class ReadingEvent(SQLModel, table=True):
    __tablename__ = "reading_event"
    # Mirror the migration's CHECK constraint here too so
    # `SQLModel.metadata.create_all` (used by the test conftest) also
    # enforces the >=1 invariant. Without this, the tests would see a
    # 0-line row succeed even though Supabase-managed Postgres rejects it.
    __table_args__ = (
        sa.CheckConstraint(
            "lines_processed >= 1",
            name="reading_event_lines_processed_positive",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(nullable=False)
    passage_id: uuid.UUID = Field(foreign_key="passage.id", nullable=False)
    lines_processed: int = Field(nullable=False)
    # Python-side default mirrors the migration's `server_default=now()`.
    # Either layer alone would do the job; both means a stray
    # `ReadingEvent(...)` without `occurred_at` works whether or not the
    # writer relies on the DB's clock.
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)
    # ANALYTICS-1 (#166): the user's raw stored preference values at the moment
    # this event was recorded, so mode-correlation analysis reflects what the
    # reader actually had set during the session (the `preference` table only
    # holds their *current* settings). JSONB on Postgres, JSON on SQLite — same
    # column type as Preference.values. Nullable: null means the user had no
    # preference row (i.e. all defaults), which is not an error. Append-only,
    # like the rest of this row — never updated after insert.
    preferences_snapshot: dict[str, Any] | None = Field(
        default=None, sa_column=sa.Column(sa.JSON, nullable=True)
    )
