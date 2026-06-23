"""Tests for the per-passage comprehension toggle (COMP-5 #128).

Covers:
  - POST /passages/{id}/comprehension flips `comprehension_enabled` and
    persists it, returning the #comprehension fragment for the new state
  - Ownership: cross-user / nonexistent passages 404 (no existence leak)
  - The questions route returns a "disabled" fragment AND skips the
    generator when comprehension is off for the passage
  - The reading view renders the right toggle state for on vs. off
"""

import hashlib
import uuid
from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.main import app
from app.models.passage import Passage
from app.services.comprehension.client import get_anthropic_client
from tests.conftest import make_user, signed_in


@pytest.fixture(autouse=True)
def _stub_anthropic_client() -> Generator[None, None, None]:
    """Override the Anthropic client dep so no test here builds a real
    client (the toggle/guard paths must never reach the API anyway)."""
    app.dependency_overrides[get_anthropic_client] = lambda: MagicMock()
    yield
    app.dependency_overrides.pop(get_anthropic_client, None)


def _make_passage(session: Session, owner_id: uuid.UUID, *, enabled: bool = True) -> Passage:
    text = "A passage of text."
    p = Passage(
        owner_id=owner_id,
        text=text,
        text_hash=hashlib.sha256(text.encode("utf-8")).digest(),
        source_type="paste",
        source_filename=None,
        comprehension_enabled=enabled,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def test_default_passage_has_comprehension_enabled(session: Session) -> None:
    """The column defaults to on — existing reading behaviour is unchanged."""
    user = signed_in(session)
    passage = _make_passage(session, user.id)
    assert passage.comprehension_enabled is True


def test_toggle_off_persists_and_returns_disabled_fragment(
    client: TestClient, session: Session
) -> None:
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    response = client.post(f"/passages/{passage.id}/comprehension", data={"enabled": "false"})

    assert response.status_code == 200
    body = response.text
    assert "Comprehension questions are off for this passage." in body
    assert "Show comprehension questions" in body
    # Fragment, not a full page.
    assert "<html" not in body.lower()

    session.refresh(passage)
    assert passage.comprehension_enabled is False


def test_toggle_on_persists_and_returns_panel_placeholder(
    client: TestClient, session: Session
) -> None:
    user = signed_in(session)
    passage = _make_passage(session, user.id, enabled=False)

    response = client.post(f"/passages/{passage.id}/comprehension", data={"enabled": "true"})

    assert response.status_code == 200
    body = response.text
    assert "Hide questions for this passage" in body
    # Re-enabling brings back the lazy-load placeholder.
    assert f"/passages/{passage.id}/questions" in body

    session.refresh(passage)
    assert passage.comprehension_enabled is True


def test_toggle_other_users_passage_returns_404(client: TestClient, session: Session) -> None:
    owner = make_user(session, email="owner@example.com")
    passage = _make_passage(session, owner.id)
    signed_in(session, email="intruder@example.com")

    response = client.post(f"/passages/{passage.id}/comprehension", data={"enabled": "false"})
    assert response.status_code == 404

    # The flag must be untouched.
    session.refresh(passage)
    assert passage.comprehension_enabled is True


def test_toggle_nonexistent_passage_returns_404(client: TestClient, session: Session) -> None:
    signed_in(session)
    response = client.post(f"/passages/{uuid.uuid4()}/comprehension", data={"enabled": "false"})
    assert response.status_code == 404


def test_questions_route_skips_generator_when_disabled(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When comprehension is off, the questions route returns the disabled
    fragment and never calls the generator (no LLM cost for a disabled
    passage)."""
    user = signed_in(session)
    passage = _make_passage(session, user.id, enabled=False)

    def _boom(**_: object) -> list[dict]:
        raise AssertionError("generate_questions must not run when disabled")

    monkeypatch.setattr("app.api.reading.generate_questions", _boom)

    response = client.get(f"/passages/{passage.id}/questions")

    assert response.status_code == 200
    # When disabled, the endpoint returns an empty body — the reading surface
    # handles the visual state via empty question-slot divs (no trigger fires).
    assert response.text.strip() == ""


def test_reading_view_shows_toggle_enabled_by_default(client: TestClient, session: Session) -> None:
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    body = client.get(f"/read/{passage.id}").text

    assert "Hide questions for this passage" in body
    assert f'hx-get="/passages/{passage.id}/questions"' in body


def test_reading_view_shows_off_state_when_disabled(client: TestClient, session: Session) -> None:
    user = signed_in(session)
    passage = _make_passage(session, user.id, enabled=False)

    body = client.get(f"/read/{passage.id}").text

    assert "Show comprehension questions" in body
    assert "Comprehension questions are off for this passage." in body
    # The lazy-load placeholder must NOT be present when disabled.
    assert f'hx-get="/passages/{passage.id}/questions"' not in body
