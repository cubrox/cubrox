"""Passage model.

A piece of text the user is reading. Originates from paste (INGEST-1)
or PDF upload (INGEST-2 #14). The `text_hash` column is the
content-addressable key into `comprehension_question_cache` (per
ADR-001 in docs/TECHNICAL-ARCHITECTURE.md), so the SAME passage pasted
by two different users hits the same cached questions.

`source_type` is constrained to `'paste' | 'pdf'`. `source_filename` is
populated only for PDF uploads (kept for display, never re-read from
disk — the parsed text is the source of truth post-ingestion).
"""

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class Passage(SQLModel, table=True):
    __tablename__ = "passage"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False)
    text: str
    text_hash: bytes
    source_type: str
    source_filename: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
