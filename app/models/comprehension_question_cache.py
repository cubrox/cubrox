"""ComprehensionQuestionCache model.

Content-addressable cache for LLM-generated comprehension questions.
Per ADR-001 in docs/TECHNICAL-ARCHITECTURE.md, every Anthropic API call
must check this cache first; the composite key
(passage_hash, question_type, model_id, prompt_version) ensures re-reads
of the same passage cost zero LLM calls.

The cache is intentionally global (no user_id). Two users pasting the
same Baha'i passage hit the same cached entry.
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class ComprehensionQuestionCache(SQLModel, table=True):
    __tablename__ = "comprehension_question_cache"

    passage_hash: bytes = Field(primary_key=True)
    question_type: str = Field(primary_key=True)
    model_id: str = Field(primary_key=True)
    prompt_version: int = Field(primary_key=True)
    questions: list[dict] = Field(sa_column=sa.Column(sa.JSON, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
