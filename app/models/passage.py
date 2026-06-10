"""Passage model.

A piece of text the user is reading. Originates from paste (INGEST-1)
or PDF upload (INGEST-2 #14). The `text_hash` column is the
content-addressable key into `comprehension_question_cache` (per
ADR-001 in docs/TECHNICAL-ARCHITECTURE.md), so the SAME passage pasted
by two different users hits the same cached questions.

`source_type` is constrained to `'paste' | 'pdf'`. `source_filename` is
populated only for PDF uploads (kept for display, never re-read from
disk — the parsed text is the source of truth post-ingestion).

`owner_id` references `auth.users(id)` in Supabase. The FK constraint
lives in the SQL migration (supabase/migrations/*.sql), not on the
SQLModel field — `auth.users` is in a different schema and isn't a
SQLModel-managed table.
"""

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class Passage(SQLModel, table=True):
    __tablename__ = "passage"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(nullable=False)
    text: str
    text_hash: bytes
    source_type: str
    source_filename: str | None = Field(default=None)
    # COMP-5 (#128): per-passage comprehension toggle. Default on; a reader
    # can disable questions for a passage where the auto-generated ones are
    # unhelpful (PRD Risk #2 mitigation for sacred/poetic text).
    comprehension_enabled: bool = Field(default=True, nullable=False)
    # INGEST-3 (#145): documents larger than MAX_TEXT_LEN are auto-split into
    # ordered parts that share a `document_id`, so a big PDF reads as a
    # navigable sequence instead of being truncated or rejected. A standalone
    # passage has document_id=None, part_index=0, part_count=1.
    document_id: uuid.UUID | None = Field(default=None, index=True)
    part_index: int = Field(default=0, nullable=False)
    part_count: int = Field(default=1, nullable=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
