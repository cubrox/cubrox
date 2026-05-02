"""Cache helpers for comprehension questions.

Per ADR-001 in docs/TECHNICAL-ARCHITECTURE.md, every comprehension-question
request goes through this cache before hitting the Anthropic API. The
helpers are deliberately session-naive: callers manage transactions so
the cache writes commit alongside whatever business logic invoked them.
"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session

from app.models.comprehension_question_cache import ComprehensionQuestionCache

_TABLE = ComprehensionQuestionCache.metadata.tables["comprehension_question_cache"]


def get_cached(
    *,
    passage_hash: bytes,
    question_type: str,
    model_id: str,
    prompt_version: int,
    session: Session,
) -> list[dict] | None:
    """Look up cached questions by content-addressable key.

    Returns the stored questions list, or None on cache miss.
    """
    stmt = select(_TABLE.c.questions).where(
        _TABLE.c.passage_hash == passage_hash,
        _TABLE.c.question_type == question_type,
        _TABLE.c.model_id == model_id,
        _TABLE.c.prompt_version == prompt_version,
    )
    return session.execute(stmt).scalar_one_or_none()


def put_cache(
    *,
    passage_hash: bytes,
    question_type: str,
    model_id: str,
    prompt_version: int,
    questions: list[dict],
    session: Session,
) -> None:
    """Store generated questions in the cache.

    Uses INSERT ... ON CONFLICT DO NOTHING. Same input → same output is
    the cache's invariant, so a duplicate write is a no-op rather than
    an error. The caller commits.
    """
    insert = pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    stmt = insert(_TABLE).values(
        passage_hash=passage_hash,
        question_type=question_type,
        model_id=model_id,
        prompt_version=prompt_version,
        questions=questions,
    )
    session.execute(stmt.on_conflict_do_nothing())
