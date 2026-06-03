"""Anthropic-backed comprehension-question generator with caching.

Per ADR-001 in docs/TECHNICAL-ARCHITECTURE.md, this is the ONLY place
that should call the Anthropic API directly. Every other module goes
through `generate_questions()`. That gives one place to enforce:
  - cache-first lookup (so re-reads cost zero LLM calls)
  - input-token cap (so a huge passage can't accidentally cost much)
  - prompt caching (so the system prompt is reused across requests)
  - structured-output validation (so a malformed LLM response can't
    poison the cache)
  - no-PII-in-logs (passage text is hashed, never logged verbatim)

The wrapper takes an `anthropic.Anthropic` client as an argument so
tests can inject a MagicMock. The real client is built by the caller
(route layer in COMP-3) from `settings.anthropic_api_key`.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from sqlmodel import Session

from app.services.comprehension import cache
from app.services.comprehension.prompts import PROMPT_VERSION, SYSTEM_PROMPT

if TYPE_CHECKING:
    import anthropic

logger = logging.getLogger(__name__)

# Max chars sent to the LLM. ~4 chars per token is a conservative estimate
# for Claude on English text, so 16_000 chars ≈ 4_000 input tokens. The
# passage-ingestion route already caps at 100_000 chars per the INGEST-1
# guardrails, so passages between these two limits are the over-budget
# ones we reject here.
MAX_INPUT_CHARS = 16_000

DEFAULT_MAX_TOKENS = 1024


class PassageTooLongError(Exception):
    """The passage exceeds the LLM input-cap. Caller surfaces a UX hint.

    Distinct from GeneratorError because this is a recoverable, user-
    actionable condition (split the passage), not a system failure.
    """

    def __init__(self, char_count: int, max_chars: int = MAX_INPUT_CHARS) -> None:
        super().__init__(
            f"Passage is {char_count:,} chars; max for comprehension questions "
            f"is {max_chars:,}. Try splitting it."
        )
        self.char_count = char_count
        self.max_chars = max_chars


class GeneratorError(Exception):
    """The LLM response was malformed (not JSON, wrong schema, etc.).

    Should be rare. The route layer surfaces a generic 'temporarily
    unavailable' message to the user and logs the raw response.
    """


class _Question(BaseModel):
    """Pydantic shape for a single LLM-generated question.

    The Literal on `type` is the structural enforcement of the prompt's
    'recall' or 'summary' allow-list. If the LLM emits any other type,
    Pydantic raises ValidationError and we surface GeneratorError.

    `answer` (COMP-4 / #123) is the source-grounded model answer the
    reader self-assesses against — required and non-empty, so a v2
    response missing it is rejected as a malformed (poison-cache)
    response rather than cached without an answer.
    """

    type: Annotated[Literal["recall", "summary"], Field()]
    text: Annotated[str, Field(min_length=1, max_length=500)]
    answer: Annotated[str, Field(min_length=1, max_length=500)]


_QUESTIONS_ADAPTER: TypeAdapter[list[_Question]] = TypeAdapter(list[_Question])


def generate_questions(
    *,
    passage_text: str,
    question_type: str,
    client: anthropic.Anthropic,
    model_id: str,
    session: Session,
) -> list[dict[str, Any]]:
    """Return cached or freshly-generated comprehension questions.

    Order of operations (the cost-containment contract):
      1. SHA-256 the passage text.
      2. Look up the cache. On hit, return immediately. No LLM call.
      3. On miss, length-check. Over MAX_INPUT_CHARS → PassageTooLongError.
      4. Call Anthropic with the system prompt under cache_control
         ephemeral. Parse + validate the JSON response.
      5. Persist to cache. Return.

    Tests pass a MagicMock for `client` and a regular Session. Real
    callers (route in COMP-3) build both from config.
    """
    text_hash = hashlib.sha256(passage_text.encode("utf-8")).digest()

    cached = cache.get_cached(
        passage_hash=text_hash,
        question_type=question_type,
        model_id=model_id,
        prompt_version=PROMPT_VERSION,
        session=session,
    )
    if cached is not None:
        logger.info(
            "comprehension cache hit",
            extra={
                "text_hash": text_hash.hex(),
                "question_type": question_type,
                "model_id": model_id,
                "prompt_version": PROMPT_VERSION,
            },
        )
        return cached

    if len(passage_text) > MAX_INPUT_CHARS:
        logger.info(
            "comprehension passage too long",
            extra={
                "text_hash": text_hash.hex(),
                "char_count": len(passage_text),
                "max_chars": MAX_INPUT_CHARS,
            },
        )
        raise PassageTooLongError(char_count=len(passage_text))

    logger.info(
        "comprehension cache miss → calling Anthropic",
        extra={
            "text_hash": text_hash.hex(),
            "question_type": question_type,
            "model_id": model_id,
            "prompt_version": PROMPT_VERSION,
            "char_count": len(passage_text),
        },
    )

    response = client.messages.create(
        model=model_id,
        max_tokens=DEFAULT_MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": passage_text}],
    )

    questions = _parse_response(response, text_hash=text_hash)

    cache.put_cache(
        passage_hash=text_hash,
        question_type=question_type,
        model_id=model_id,
        prompt_version=PROMPT_VERSION,
        questions=questions,
        session=session,
    )
    session.commit()

    return questions


def _parse_response(response: Any, *, text_hash: bytes) -> list[dict[str, Any]]:
    """Extract + validate the JSON array from the LLM response.

    Raises GeneratorError with the (hashed-referenced) raw response on
    any parse / schema failure. Never logs the response body verbatim
    because the LLM might echo passage content back.
    """
    try:
        raw_text = response.content[0].text
    except (AttributeError, IndexError) as exc:
        raise GeneratorError("Anthropic response had no text content block") from exc

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.warning(
            "comprehension response was not valid JSON",
            extra={"text_hash": text_hash.hex()},
        )
        raise GeneratorError("LLM response was not valid JSON") from exc

    try:
        validated = _QUESTIONS_ADAPTER.validate_python(parsed)
    except ValidationError as exc:
        logger.warning(
            "comprehension response did not match schema",
            extra={"text_hash": text_hash.hex()},
        )
        raise GeneratorError("LLM response did not match expected schema") from exc

    return [q.model_dump() for q in validated]
