"""Tests for the comprehension-question cache.

Covers:
  - put → get round-trip
  - cache miss returns None
  - each of the 4 key parts (hash, type, model, prompt_version) is
    independently part of the cache key
  - duplicate put doesn't raise (ON CONFLICT DO NOTHING)
  - 32-byte SHA-256 digests round-trip through BYTEA/BLOB cleanly
  - the model exposes the composite primary key on its table

Migration up/down/up cycle is covered separately by
tests/test_comprehension_cache_migration.py.
"""

import hashlib

from sqlmodel import Session

from app.models.comprehension_question_cache import ComprehensionQuestionCache
from app.services.comprehension import cache

PASSAGE = b"O Son of Spirit! My first counsel is this..."
HASH = hashlib.sha256(PASSAGE).digest()
QUESTIONS = [
    {"type": "recall", "text": "What is the first counsel?"},
    {"type": "summary", "text": "Summarize the passage in one sentence."},
]


def _put(session: Session, **overrides: object) -> None:
    kwargs: dict[str, object] = {
        "passage_hash": HASH,
        "question_type": "recall",
        "model_id": "claude-haiku-4-5",
        "prompt_version": 1,
        "questions": QUESTIONS,
        "session": session,
    }
    kwargs.update(overrides)
    cache.put_cache(**kwargs)  # type: ignore[arg-type]


def _get(session: Session, **overrides: object) -> list[dict] | None:
    kwargs: dict[str, object] = {
        "passage_hash": HASH,
        "question_type": "recall",
        "model_id": "claude-haiku-4-5",
        "prompt_version": 1,
        "session": session,
    }
    kwargs.update(overrides)
    return cache.get_cached(**kwargs)  # type: ignore[arg-type]


def test_put_then_get_returns_stored_questions(session: Session) -> None:
    _put(session)
    assert _get(session) == QUESTIONS


def test_get_with_unknown_hash_returns_none(session: Session) -> None:
    _put(session)
    other_hash = hashlib.sha256(b"different passage").digest()
    assert _get(session, passage_hash=other_hash) is None


def test_get_on_empty_cache_returns_none(session: Session) -> None:
    assert _get(session) is None


def test_changing_question_type_misses(session: Session) -> None:
    _put(session)
    assert _get(session, question_type="summary") is None


def test_changing_model_id_misses(session: Session) -> None:
    _put(session)
    assert _get(session, model_id="claude-sonnet-4-6") is None


def test_changing_prompt_version_misses(session: Session) -> None:
    _put(session)
    assert _get(session, prompt_version=2) is None


def test_duplicate_put_does_not_raise(session: Session) -> None:
    _put(session)
    _put(session)  # second call uses ON CONFLICT DO NOTHING
    assert _get(session) == QUESTIONS


def test_duplicate_put_keeps_first_writers_values(session: Session) -> None:
    """ON CONFLICT DO NOTHING means the first cached value wins.

    Same (hash, type, model, prompt_version) → same generated questions
    is the cache invariant; this test pins the no-clobber behavior so a
    future change to ON CONFLICT DO UPDATE has to be deliberate.
    """
    _put(session, questions=[{"type": "recall", "text": "first"}])
    _put(session, questions=[{"type": "recall", "text": "second"}])
    assert _get(session) == [{"type": "recall", "text": "first"}]


def test_thirty_two_byte_hash_round_trips(session: Session) -> None:
    assert len(HASH) == 32
    _put(session)
    cached = _get(session)
    assert cached is not None
    assert cached == QUESTIONS


def test_model_has_composite_primary_key() -> None:
    pk_cols = {c.name for c in ComprehensionQuestionCache.__table__.primary_key.columns}
    assert pk_cols == {"passage_hash", "question_type", "model_id", "prompt_version"}


def test_questions_column_is_not_nullable() -> None:
    questions_col = ComprehensionQuestionCache.__table__.c["questions"]
    assert questions_col.nullable is False


def test_two_distinct_passages_coexist(session: Session) -> None:
    other_hash = hashlib.sha256(b"second passage").digest()
    other_questions = [{"type": "recall", "text": "What is the second passage about?"}]
    _put(session)
    _put(session, passage_hash=other_hash, questions=other_questions)
    assert _get(session) == QUESTIONS
    assert _get(session, passage_hash=other_hash) == other_questions
