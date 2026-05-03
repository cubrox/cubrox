"""MagicLinkToken model.

Short-lived, single-use sign-in token. Stored as SHA-256 hash of the raw
token; the raw token is delivered via email and never persisted. Rules
per ADR-002 in docs/TECHNICAL-ARCHITECTURE.md:

  - 15-minute TTL
  - single-use (consumed_at is the lockout marker)
  - issuing a new token invalidates outstanding ones (handled in service)
"""

import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel


class MagicLinkToken(SQLModel, table=True):
    __tablename__ = "magic_link_token"

    token_hash: bytes = Field(primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False)
    expires_at: datetime
    consumed_at: datetime | None = Field(default=None)
