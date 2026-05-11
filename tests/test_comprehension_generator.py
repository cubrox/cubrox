"""Tests for the Anthropic-backed comprehension-question generator.

Covers the Definition of Done from issue #19 (COMP-2):
  - Cache hit returns immediately without invoking the Anthropic client
  - Cache miss calls Anthropic exactly once, persists to cache, returns parsed list
  - Second call with the same text after a miss is a cache hit
  - Passage exceeding 16,000 chars raises PassageTooLongError BEFORE the LLM call
  - The call to messages.create uses cache_control={'type': 'ephemeral'} on the system message
  - The call uses model=settings.anthropic_model
  - Malformed JSON response raises GeneratorError
  - Schema-mismatched response (e.g., wrong "type" value) raises GeneratorError
  - The passage text never appears in log output
  - Bumping PROMPT_VERSION produces a cache miss for previously-cached entries

The Anthropic client is ALWAYS a MagicMock. The real API is never hit
from this file. CI never makes outbound requests to Anthropic.
"""

import hashlib
import logging
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlmodel import Session

from app.services.comprehension import cache, generator
from app.services.comprehension.generator import (
    MAX_INPUT_CHARS,
    GeneratorError,
    PassageTooLongError,
    generate_questions,
)
from app.services.comprehension.prompts import PROMPT_VERSION

TEST_MODEL_ID = "claude-haiku-4-5"
TEST_PASSAGE = "O Son of Spirit! My first counsel is this: possess a pure, kindly heart."

VALID_LLM_OUTPUT = (
    '[{"type":"recall","text":"What is the first counsel?"},'
    '{"type":"recall","text":"What attribute should the heart have?"},'
    '{"type":"summary","text":"What virtue is the passage urging?"}]'
)


def _make_mock_client(*, response_text: str = VALID_LLM_OUTPUT) -> MagicMock:
    """Build a MagicMock client whose messages.create() returns one
    text content block carrying `response_text`."""
    response = MagicMock()
    text_block = MagicMock()
    text_block.text = response_text
    response.content = [text_block]

    client = MagicMock()
    client.messages.create.return_value = response
    return client


# ---------------------------------------------------------------------------
# Cache-first contract — the cost-containment promise
# ---------------------------------------------------------------------------


def test_cache_hit_returns_immediately_without_calling_anthropic(session: Session) -> None:
    """The ADR-001 cost story rests on this: any cache hit short-circuits
    before the Anthropic SDK is touched. Verify by pre-populating the
    cache and asserting the mock client's create() is never called."""
    text_hash = hashlib.sha256(TEST_PASSAGE.encode("utf-8")).digest()
    cached_questions = [{"type": "recall", "text": "cached question?"}]

    cache.put_cache(
        passage_hash=text_hash,
        question_type="recall",
        model_id=TEST_MODEL_ID,
        prompt_version=PROMPT_VERSION,
        questions=cached_questions,
        session=session,
    )
    session.commit()

    client = _make_mock_client()

    result = generate_questions(
        passage_text=TEST_PASSAGE,
        question_type="recall",
        client=client,
        model_id=TEST_MODEL_ID,
        session=session,
    )

    assert result == cached_questions
    assert client.messages.create.call_count == 0


def test_cache_miss_calls_anthropic_once_and_persists(session: Session) -> None:
    client = _make_mock_client()

    result = generate_questions(
        passage_text=TEST_PASSAGE,
        question_type="recall",
        client=client,
        model_id=TEST_MODEL_ID,
        session=session,
    )

    assert client.messages.create.call_count == 1
    assert len(result) == 3
    assert result[0] == {"type": "recall", "text": "What is the first counsel?"}

    # And the cache now has it.
    text_hash = hashlib.sha256(TEST_PASSAGE.encode("utf-8")).digest()
    cached = cache.get_cached(
        passage_hash=text_hash,
        question_type="recall",
        model_id=TEST_MODEL_ID,
        prompt_version=PROMPT_VERSION,
        session=session,
    )
    assert cached == result


def test_second_call_after_miss_is_a_cache_hit(session: Session) -> None:
    """Pins the round-trip: first call is a miss (LLM invoked once),
    second call with the same input is a hit (no further LLM calls)."""
    client = _make_mock_client()

    generate_questions(
        passage_text=TEST_PASSAGE,
        question_type="recall",
        client=client,
        model_id=TEST_MODEL_ID,
        session=session,
    )
    generate_questions(
        passage_text=TEST_PASSAGE,
        question_type="recall",
        client=client,
        model_id=TEST_MODEL_ID,
        session=session,
    )

    assert client.messages.create.call_count == 1  # only the first call


# ---------------------------------------------------------------------------
# Input-cap contract — the runaway-cost prevention
# ---------------------------------------------------------------------------


def test_passage_at_input_cap_succeeds(session: Session) -> None:
    """Exactly MAX_INPUT_CHARS passes — boundary case."""
    client = _make_mock_client()
    passage = "a" * MAX_INPUT_CHARS

    result = generate_questions(
        passage_text=passage,
        question_type="recall",
        client=client,
        model_id=TEST_MODEL_ID,
        session=session,
    )
    assert client.messages.create.call_count == 1
    assert len(result) == 3


def test_passage_over_input_cap_raises_and_does_not_call_anthropic(
    session: Session,
) -> None:
    """The cost-prevention property: a too-long passage raises BEFORE the
    LLM is invoked, AND BEFORE writing anything to the cache. Pinned by
    asserting both side effects didn't happen."""
    client = _make_mock_client()
    passage = "a" * (MAX_INPUT_CHARS + 1)

    with pytest.raises(PassageTooLongError) as exc_info:
        generate_questions(
            passage_text=passage,
            question_type="recall",
            client=client,
            model_id=TEST_MODEL_ID,
            session=session,
        )

    assert client.messages.create.call_count == 0
    assert exc_info.value.char_count == MAX_INPUT_CHARS + 1

    # No cache row was written.
    text_hash = hashlib.sha256(passage.encode("utf-8")).digest()
    assert (
        cache.get_cached(
            passage_hash=text_hash,
            question_type="recall",
            model_id=TEST_MODEL_ID,
            prompt_version=PROMPT_VERSION,
            session=session,
        )
        is None
    )


# ---------------------------------------------------------------------------
# Anthropic call shape — pinning the prompt-caching invariant
# ---------------------------------------------------------------------------


def test_anthropic_call_uses_ephemeral_cache_control_on_system(session: Session) -> None:
    """The system message must carry cache_control={'type': 'ephemeral'}.
    Without this, Anthropic's prompt cache never warms up and we re-pay
    the system-prompt tokens on every call."""
    client = _make_mock_client()

    generate_questions(
        passage_text=TEST_PASSAGE,
        question_type="recall",
        client=client,
        model_id=TEST_MODEL_ID,
        session=session,
    )

    _, kwargs = client.messages.create.call_args
    system = kwargs["system"]
    assert isinstance(system, list)
    assert system[0]["cache_control"] == {"type": "ephemeral"}


def test_anthropic_call_uses_supplied_model_id(session: Session) -> None:
    client = _make_mock_client()

    generate_questions(
        passage_text=TEST_PASSAGE,
        question_type="recall",
        client=client,
        model_id="claude-haiku-4-5",
        session=session,
    )

    _, kwargs = client.messages.create.call_args
    assert kwargs["model"] == "claude-haiku-4-5"


def test_anthropic_call_carries_passage_as_user_message(session: Session) -> None:
    client = _make_mock_client()

    generate_questions(
        passage_text=TEST_PASSAGE,
        question_type="recall",
        client=client,
        model_id=TEST_MODEL_ID,
        session=session,
    )

    _, kwargs = client.messages.create.call_args
    messages = kwargs["messages"]
    assert messages == [{"role": "user", "content": TEST_PASSAGE}]


# ---------------------------------------------------------------------------
# Malformed responses — the bad-LLM-day case
# ---------------------------------------------------------------------------


def test_malformed_json_response_raises_generator_error(session: Session) -> None:
    """The LLM occasionally emits prose preamble even when told not to.
    Catch it, raise GeneratorError, surface a friendly UX message at
    the route layer."""
    client = _make_mock_client(response_text="Here are your questions: ...")

    with pytest.raises(GeneratorError):
        generate_questions(
            passage_text=TEST_PASSAGE,
            question_type="recall",
            client=client,
            model_id=TEST_MODEL_ID,
            session=session,
        )


def test_schema_mismatched_response_raises_generator_error(session: Session) -> None:
    """The LLM emits valid JSON but with the wrong 'type' enum or missing
    'text' field. Pydantic catches it; we re-raise as GeneratorError."""
    bad_payload = '[{"type":"opinion","text":"What did you think?"}]'
    client = _make_mock_client(response_text=bad_payload)

    with pytest.raises(GeneratorError):
        generate_questions(
            passage_text=TEST_PASSAGE,
            question_type="recall",
            client=client,
            model_id=TEST_MODEL_ID,
            session=session,
        )


def test_malformed_response_does_not_poison_cache(session: Session) -> None:
    """A failed call must NOT write the bad output to the cache. Otherwise
    every retry would serve the broken result without re-calling the LLM."""
    client = _make_mock_client(response_text="not json")

    with pytest.raises(GeneratorError):
        generate_questions(
            passage_text=TEST_PASSAGE,
            question_type="recall",
            client=client,
            model_id=TEST_MODEL_ID,
            session=session,
        )

    text_hash = hashlib.sha256(TEST_PASSAGE.encode("utf-8")).digest()
    assert (
        cache.get_cached(
            passage_hash=text_hash,
            question_type="recall",
            model_id=TEST_MODEL_ID,
            prompt_version=PROMPT_VERSION,
            session=session,
        )
        is None
    )


def test_empty_content_blocks_raises_generator_error(session: Session) -> None:
    """Defensive: if the SDK returns a response with no content blocks
    (rare but possible on some error paths), surface GeneratorError
    rather than 500ing."""
    client = MagicMock()
    response = MagicMock()
    response.content = []  # no blocks at all
    client.messages.create.return_value = response

    with pytest.raises(GeneratorError):
        generate_questions(
            passage_text=TEST_PASSAGE,
            question_type="recall",
            client=client,
            model_id=TEST_MODEL_ID,
            session=session,
        )


# ---------------------------------------------------------------------------
# PII-in-logs — never leak passage text
# ---------------------------------------------------------------------------


def test_passage_text_never_appears_in_logs(
    session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    """Passages may contain personal or sacred text. Never log them
    verbatim. The text_hash hex is the loggable identifier; passage
    contents are not."""
    client = _make_mock_client()
    sensitive_phrase = "O Son of Spirit"
    passage_with_sensitive_phrase = f"{sensitive_phrase}! My first counsel..."

    with caplog.at_level(logging.DEBUG):
        generate_questions(
            passage_text=passage_with_sensitive_phrase,
            question_type="recall",
            client=client,
            model_id=TEST_MODEL_ID,
            session=session,
        )

    assert sensitive_phrase not in caplog.text


def test_passage_too_long_log_does_not_include_passage(
    session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    """The 'too long' log line records char count but never the text."""
    client = _make_mock_client()
    sensitive_marker = "THIS_IS_THE_SECRET_MARKER"
    passage = sensitive_marker + ("a" * (MAX_INPUT_CHARS + 1))

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(PassageTooLongError):
            generate_questions(
                passage_text=passage,
                question_type="recall",
                client=client,
                model_id=TEST_MODEL_ID,
                session=session,
            )

    assert sensitive_marker not in caplog.text


# ---------------------------------------------------------------------------
# Cache invalidation via PROMPT_VERSION
# ---------------------------------------------------------------------------


def test_bumping_prompt_version_produces_cache_miss(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A prompt-text change is communicated via PROMPT_VERSION bump.
    Cached questions tagged with the OLD version are no longer found
    on lookup — the next call refetches from the LLM."""
    client = _make_mock_client()

    # Prime the cache at the current PROMPT_VERSION.
    generate_questions(
        passage_text=TEST_PASSAGE,
        question_type="recall",
        client=client,
        model_id=TEST_MODEL_ID,
        session=session,
    )
    assert client.messages.create.call_count == 1

    # Bump the version that generator.py references.
    monkeypatch.setattr(generator, "PROMPT_VERSION", PROMPT_VERSION + 1)

    # The next call should be a miss (different cache key now).
    generate_questions(
        passage_text=TEST_PASSAGE,
        question_type="recall",
        client=client,
        model_id=TEST_MODEL_ID,
        session=session,
    )
    assert client.messages.create.call_count == 2  # second LLM call


# ---------------------------------------------------------------------------
# Return shape
# ---------------------------------------------------------------------------


def test_return_shape_is_list_of_plain_dicts(session: Session) -> None:
    """Caller (COMP-3 route) and cache storage both expect plain dicts.
    Pydantic models go through .model_dump() before they leave this
    module so callers never see Pydantic types."""
    client = _make_mock_client()

    result: list[dict[str, Any]] = generate_questions(
        passage_text=TEST_PASSAGE,
        question_type="recall",
        client=client,
        model_id=TEST_MODEL_ID,
        session=session,
    )

    assert isinstance(result, list)
    for q in result:
        assert isinstance(q, dict)
        assert set(q.keys()) == {"type", "text"}
        assert isinstance(q["text"], str)
        assert q["type"] in ("recall", "summary")
