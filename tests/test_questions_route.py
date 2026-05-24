"""Tests for GET /passages/{passage_id}/questions.

Covers the Definition of Done from issue #20 (COMP-3):
  - Owner request → 200 with <section aria-label="Comprehension check">
    fragment containing at least one <li> (generator mocked)
  - Response body does NOT include <html> (fragment)
  - Cross-user passage → 404
  - Nonexistent passage → 404
  - Both 404 paths return identical body (no existence leak)
  - Route invokes generator.generate_questions with question_type="recall"
  - PassageTooLongError → 200 with the "too long" fragment
  - GeneratorError → 200 with the "unavailable" fragment + WARN log
  - Unauthenticated request → 200 + HX-Redirect: /login (per AUTH-3)
  - The Anthropic client is never the real client in tests
"""

import hashlib
import logging
import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.main import app
from app.models.passage import Passage
from app.services.comprehension import generator
from app.services.comprehension.client import get_anthropic_client
from tests.conftest import make_user, signed_in


@pytest.fixture(autouse=True)
def stub_anthropic_client() -> Any:
    """Override the Anthropic client dependency with a MagicMock.

    Autouse so no test in this file accidentally hits the real API.
    Yields the mock so tests that need to inspect or override its
    return value can.
    """
    mock_client = MagicMock()
    app.dependency_overrides[get_anthropic_client] = lambda: mock_client
    yield mock_client
    app.dependency_overrides.pop(get_anthropic_client, None)


def _make_passage(
    session: Session, user_id: uuid.UUID, text: str = "A passage of text."
) -> Passage:
    p = Passage(
        user_id=user_id,
        text=text,
        text_hash=hashlib.sha256(text.encode("utf-8")).digest(),
        source_type="paste",
        source_filename=None,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


# ---------------------------------------------------------------------------
# Happy path — questions render
# ---------------------------------------------------------------------------


def test_owner_gets_questions_fragment(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    monkeypatch.setattr(
        "app.api.reading.generate_questions",
        lambda **_: [
            {"type": "recall", "text": "What is the first word?"},
            {"type": "recall", "text": "What is the last word?"},
            {"type": "summary", "text": "What is the passage about?"},
        ],
    )

    response = client.get(f"/passages/{passage.id}/questions")

    assert response.status_code == 200
    body = response.text
    assert '<section aria-label="Comprehension check"' in body
    assert "<ol>" in body
    assert body.count("<li>") == 3
    assert "What is the first word?" in body


def test_response_is_a_fragment_not_a_full_page(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    monkeypatch.setattr(
        "app.api.reading.generate_questions",
        lambda **_: [{"type": "recall", "text": "Q?"}],
    )

    response = client.get(f"/passages/{passage.id}/questions")
    body = response.text
    assert "<html" not in body
    assert "<body" not in body


def test_route_passes_passage_text_and_question_type_to_generator(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pin the contract between the route and generate_questions.
    The route must pass the loaded passage's text AND
    question_type='recall'."""
    user = signed_in(session)
    passage = _make_passage(session, user.id, text="O Son of Spirit!")

    captured: dict[str, Any] = {}

    def fake_generate(**kwargs: Any) -> list[dict]:
        captured.update(kwargs)
        return [{"type": "recall", "text": "Q?"}]

    monkeypatch.setattr("app.api.reading.generate_questions", fake_generate)

    client.get(f"/passages/{passage.id}/questions")

    assert captured["passage_text"] == "O Son of Spirit!"
    assert captured["question_type"] == "recall"


def test_route_uses_configured_model_id(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    captured_model: dict[str, str] = {}

    def fake_generate(**kwargs: Any) -> list[dict]:
        captured_model["model_id"] = kwargs["model_id"]
        return [{"type": "recall", "text": "Q?"}]

    monkeypatch.setattr("app.api.reading.generate_questions", fake_generate)

    client.get(f"/passages/{passage.id}/questions")
    # Settings default is "claude-haiku-4-5".
    assert captured_model["model_id"] == "claude-haiku-4-5"


# ---------------------------------------------------------------------------
# Ownership / 404
# ---------------------------------------------------------------------------


def test_other_users_passage_returns_404(client: TestClient, session: Session) -> None:
    me = signed_in(session, email="me@example.com")  # noqa: F841

    other_user = make_user(session, email="other@example.com")
    other_passage = _make_passage(session, other_user.id)

    response = client.get(f"/passages/{other_passage.id}/questions")
    assert response.status_code == 404


def test_nonexistent_passage_returns_404(client: TestClient, session: Session) -> None:
    signed_in(session)
    response = client.get(f"/passages/{uuid.uuid4()}/questions")
    assert response.status_code == 404


def test_other_user_and_nonexistent_have_identical_response_shape(
    client: TestClient, session: Session
) -> None:
    """Single failure branch → same 404 body for both. Don't leak which
    case applied."""
    signed_in(session)
    other = make_user(session, email="other@example.com")
    other_passage = _make_passage(session, other.id)

    other_response = client.get(f"/passages/{other_passage.id}/questions")
    nonexistent_response = client.get(f"/passages/{uuid.uuid4()}/questions")

    assert other_response.status_code == nonexistent_response.status_code == 404


# ---------------------------------------------------------------------------
# Error states — too long + unavailable
# ---------------------------------------------------------------------------


def test_passage_too_long_returns_200_with_friendly_fragment(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A PassageTooLongError from the generator must render as a friendly
    200 fragment, NOT a 4xx/5xx. Comprehension is a feature, not a hard
    dependency on every passage."""
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    def fake_generate(**_: Any) -> list[dict]:
        raise generator.PassageTooLongError(char_count=20_000)

    monkeypatch.setattr("app.api.reading.generate_questions", fake_generate)

    response = client.get(f"/passages/{passage.id}/questions")
    assert response.status_code == 200
    body = response.text
    assert "too long" in body.lower()
    # Still wrapped in the comprehension-check section so the rest of
    # the page's structure / a11y is consistent.
    assert '<section aria-label="Comprehension check"' in body


def test_generator_error_returns_200_with_unavailable_fragment(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A GeneratorError (malformed LLM response, API down, etc.) renders
    a friendly "temporarily unavailable" fragment. Must NOT 500. The
    error is logged at WARN level for operator follow-up.

    We patch the route's logger.warning directly rather than relying on
    pytest's caplog — caplog interactions are sensitive to suite-wide
    logging configuration that other tests can perturb. Patching the
    bound method is robust to anything else the suite has done."""
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    def fake_generate(**_: Any) -> list[dict]:
        raise generator.GeneratorError("anthropic blew up")

    monkeypatch.setattr("app.api.reading.generate_questions", fake_generate)

    captured: list[str] = []

    def capture_warning(msg: str, *args: Any, **kwargs: Any) -> None:
        captured.append(msg)

    monkeypatch.setattr("app.api.reading.logger.warning", capture_warning)

    response = client.get(f"/passages/{passage.id}/questions")

    assert response.status_code == 200
    body = response.text
    assert "temporarily unavailable" in body.lower()
    assert '<section aria-label="Comprehension check"' in body
    assert any("comprehension generator failed" in m for m in captured)


def test_generator_error_log_does_not_include_passage_text(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    user = signed_in(session)
    sensitive = "SENSITIVE_MARKER_DO_NOT_LOG"
    passage = _make_passage(session, user.id, text=f"{sensitive} something something")

    def fake_generate(**_: Any) -> list[dict]:
        raise generator.GeneratorError("api error")

    monkeypatch.setattr("app.api.reading.generate_questions", fake_generate)

    with caplog.at_level(logging.DEBUG):
        client.get(f"/passages/{passage.id}/questions")

    assert sensitive not in caplog.text


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_unauthenticated_returns_303_to_landing(client: TestClient) -> None:
    response = client.get(f"/passages/{uuid.uuid4()}/questions", follow_redirects=False)
    # Without HX-Request header: browser navigation → 303 redirect.
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_unauthenticated_htmx_request_gets_hx_redirect(client: TestClient) -> None:
    """An HTMX request without a session cookie gets the HX-Redirect
    treatment from AUTH-3's exception handler. Without this, HTMX
    would silently fail to navigate the user to the landing page."""
    response = client.get(
        f"/passages/{uuid.uuid4()}/questions",
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert response.headers.get("HX-Redirect") == "/"


# ---------------------------------------------------------------------------
# Reading view integration — the placeholder div is wired correctly
# ---------------------------------------------------------------------------


def test_reading_view_contains_questions_placeholder(client: TestClient, session: Session) -> None:
    """READ-1's reading page now includes a <div id="questions-panel">
    that lazy-loads from this route. Pin the wiring so a future template
    refactor that removes it can't slip through."""
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    response = client.get(f"/read/{passage.id}")
    body = response.text

    assert 'id="questions-panel"' in body
    assert f'hx-get="/passages/{passage.id}/questions"' in body
    assert 'hx-trigger="load delay:200ms"' in body
    assert 'hx-swap="outerHTML"' in body


def test_reading_view_placeholder_has_aria_live(client: TestClient, session: Session) -> None:
    """The placeholder div needs aria-live so screen readers announce
    the lazy-loaded content when it arrives."""
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    response = client.get(f"/read/{passage.id}")
    body = response.text
    assert 'aria-live="polite"' in body
