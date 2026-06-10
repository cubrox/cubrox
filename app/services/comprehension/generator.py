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
from typing import Annotated, Any, Literal

import anthropic
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from sqlmodel import Session

from app.services.comprehension import cache
from app.services.comprehension.prompts import PROMPT_VERSION, SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Max chars sent to the LLM per generation. ~4 chars per token, so 16_000
# chars ≈ 4_000 input tokens — the cost bound. A passage longer than this is
# TRUNCATED to this many chars (at a word boundary) for question generation
# rather than rejected: comprehension questions about the opening of a long
# passage beat no questions at all (and INGEST-3 already splits big documents
# into parts). Cost stays bounded because we never send more than this.
MAX_INPUT_CHARS = 16_000

DEFAULT_MAX_TOKENS = 1024


def _truncate_for_llm(text: str) -> str:
    """Cap `text` at MAX_INPUT_CHARS for question generation, trimming back to
    the last word boundary so we don't cut a word in half."""
    if len(text) <= MAX_INPUT_CHARS:
        return text
    cut = text[:MAX_INPUT_CHARS]
    space = cut.rfind(" ")
    # Only honor the boundary if it doesn't lop off most of the budget (a
    # passage with no spaces in the first 16k just gets a hard cut).
    return cut[:space] if space > MAX_INPUT_CHARS // 2 else cut


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
      1. SHA-256 the passage text (the cache key is the FULL text).
      2. Look up the cache. On hit, return immediately. No LLM call.
      3. On miss, truncate the input to MAX_INPUT_CHARS (bounds token cost;
         a long passage still gets questions about its opening).
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

    # Long passages are truncated (not rejected) so they still get questions
    # while keeping the per-call token cost bounded. The cache key is the FULL
    # passage hash, so the same passage always yields the same questions.
    llm_input = _truncate_for_llm(passage_text)

    logger.info(
        "comprehension cache miss → calling Anthropic",
        extra={
            "text_hash": text_hash.hex(),
            "question_type": question_type,
            "model_id": model_id,
            "prompt_version": PROMPT_VERSION,
            "char_count": len(passage_text),
            "input_chars": len(llm_input),
            "truncated": len(llm_input) < len(passage_text),
        },
    )

    try:
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
            messages=[{"role": "user", "content": llm_input}],
        )
    except anthropic.AnthropicError as exc:
        # Auth failure (missing/invalid key), bad model id, rate limit,
        # overload, network — all degrade to the "unavailable" fragment
        # rather than 500ing the reading view. Comprehension is a feature,
        # not a hard dependency. Log the error TYPE (never the message —
        # it can echo request content) so prod failures are diagnosable.
        logger.warning(
            "comprehension Anthropic call failed",
            extra={"text_hash": text_hash.hex(), "error_type": type(exc).__name__},
        )
        raise GeneratorError("Anthropic API call failed") from exc

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


def _extract_json_array(text: str) -> str:
    """Pull the JSON array out of a model response that may be wrapped.

    The prompt asks for a bare JSON array with no markdown or preamble,
    but real models (Haiku especially) frequently fence the output in
    ```json … ``` or add a sentence before/after. A bare `json.loads`
    rejects those, which surfaced in prod as "comprehension unavailable"
    on the first real (non-mocked, non-cached) generation. This strips a
    surrounding code fence and, failing that, slices to the outermost
    `[ … ]` so well-formed JSON wrapped in chatter still parses.
    """
    s = text.strip()

    # Strip a leading ``` / ```json fence and its trailing ``` partner.
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
        s = s.strip()

    # If prose still surrounds the array, slice to the outermost brackets.
    start, end = s.find("["), s.rfind("]")
    if start != -1 and end > start:
        s = s[start : end + 1]

    return s


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
        parsed = json.loads(_extract_json_array(raw_text))
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
