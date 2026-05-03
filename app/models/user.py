"""User model.

Account record. Identified by email; passwordless per ADR-002 in
docs/TECHNICAL-ARCHITECTURE.md. Sign-in is via a one-time magic link
(see app/services/identity/magic_link.py).
"""

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "user"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str = Field(unique=True, max_length=320)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_login: datetime | None = Field(default=None)
