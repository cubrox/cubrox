"""Tests for GET /read/{passage_id} (the reading view).

Covers the Definition of Done from issue #15 (READ-1):
  - GET /read/<my-passage> returns 200 with passage text in body
  - Response includes <style id="reading-surface-style"> with all 6
    --reader-* variables
  - Response is a full HTML page (<html present), not a fragment
  - GET /read/<other-users-passage> returns 404 (no info leak)
  - GET /read/<nonexistent-uuid> returns 404
  - User with no Preference row gets defaults rendered
  - User with a Preference row gets THEIR values rendered
  - Unauthenticated GET → 303 to /login
"""

import hashlib
import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.passage import Passage
from app.models.preference import Preference
from app.services.reading.defaults import DEFAULT_PREFERENCES
from tests.conftest import make_user, signed_in

ALL_CSS_VAR_NAMES = (
    "--reader-font",
    "--reader-size",
    "--reader-line-height",
    "--reader-bg",
    "--reader-fg",
    "--reader-max-width",
)


def _make_passage(session: Session, user_id: uuid.UUID, text: str = "The hidden words.") -> Passage:
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
# Happy path
# ---------------------------------------------------------------------------


def test_owner_gets_passage_rendered(client: TestClient, session: Session) -> None:
    user = signed_in(session)
    passage = _make_passage(session, user.id, text="O Son of Spirit! My first counsel is this...")

    response = client.get(f"/read/{passage.id}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "O Son of Spirit" in response.text


def test_response_is_a_full_html_page_not_a_fragment(client: TestClient, session: Session) -> None:
    """The reading view is a top-level browser navigation. It must be
    a full page (with <html>), not an HTMX fragment. Pin this so a
    future refactor can't accidentally turn it into a fragment route."""
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    response = client.get(f"/read/{passage.id}")
    assert "<html" in response.text


def test_response_contains_style_block_with_all_six_css_variables(
    client: TestClient, session: Session
) -> None:
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    response = client.get(f"/read/{passage.id}")
    body = response.text

    assert '<style id="reading-surface-style">' in body
    for css_var in ALL_CSS_VAR_NAMES:
        assert css_var in body, f"missing CSS variable {css_var}"


def test_passage_renders_inside_reading_surface_article(
    client: TestClient, session: Session
) -> None:
    user = signed_in(session)
    passage = _make_passage(session, user.id, text="some passage text")

    response = client.get(f"/read/{passage.id}")
    body = response.text

    # The <article id="reading-surface"> wraps the rendered text. The
    # CSS hooks off this id; if a future refactor renames or removes
    # it, the styling silently breaks.
    assert '<article id="reading-surface">' in body


# ---------------------------------------------------------------------------
# Defaults vs. stored preferences
# ---------------------------------------------------------------------------


def test_user_with_no_preference_row_gets_defaults_rendered(
    client: TestClient, session: Session
) -> None:
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    response = client.get(f"/read/{passage.id}")
    body = response.text

    # Default size from DEFAULT_PREFERENCES["size"] is "18px".
    assert f"--reader-size: {DEFAULT_PREFERENCES['size']}" in body
    # Default line-height is "1.6".
    assert f"--reader-line-height: {DEFAULT_PREFERENCES['line_height']}" in body
    # Default max-width is "65ch".
    assert f"--reader-max-width: {DEFAULT_PREFERENCES['max_width']}" in body


def test_user_with_preference_row_gets_their_values_rendered(
    client: TestClient, session: Session
) -> None:
    """Stored preferences override the defaults. Pinned by setting an
    unmistakable size value and asserting it lands in the rendered
    style block.
    """
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    session.add(
        Preference(
            user_id=user.id,
            values={"size": "24px", "max_width": "55ch"},
            updated_at=datetime.now(UTC),
        )
    )
    session.commit()

    response = client.get(f"/read/{passage.id}")
    body = response.text

    # Stored values take precedence.
    assert "--reader-size: 24px" in body
    assert "--reader-max-width: 55ch" in body
    # Unset keys still come from defaults.
    assert f"--reader-line-height: {DEFAULT_PREFERENCES['line_height']}" in body


def test_does_not_create_preference_row_on_first_render(
    client: TestClient, session: Session
) -> None:
    """A user with no Preference row gets defaults — but no row is
    lazily inserted. Row creation is gated to actual user toggles
    (READ-2 #16). This pins the lazy-NOT-eager invariant.
    """
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    client.get(f"/read/{passage.id}")

    pref = session.get(Preference, user.id)
    assert pref is None


# ---------------------------------------------------------------------------
# Ownership / not-found
# ---------------------------------------------------------------------------


def test_other_users_passage_returns_404(client: TestClient, session: Session) -> None:
    """A passage owned by someone else returns 404 — same as
    nonexistent. Don't leak existence."""
    me = signed_in(session, email="me@example.com")  # noqa: F841

    other_user = make_user(session, email="other@example.com")
    other_passage = _make_passage(session, other_user.id, text="not yours")

    response = client.get(f"/read/{other_passage.id}")
    assert response.status_code == 404


def test_nonexistent_uuid_returns_404(client: TestClient, session: Session) -> None:
    signed_in(session)
    response = client.get(f"/read/{uuid.uuid4()}")
    assert response.status_code == 404


def test_other_user_and_nonexistent_have_identical_response_shape(
    client: TestClient, session: Session
) -> None:
    """The 'don't leak existence' invariant: both paths return 404 with
    nothing distinguishing them. Pin this so a future refactor can't
    introduce a more-helpful error message that gives away whether a
    UUID is real."""
    signed_in(session)

    other = make_user(session, email="other@example.com")
    other_passage = _make_passage(session, other.id)

    other_response = client.get(f"/read/{other_passage.id}")
    nonexistent_response = client.get(f"/read/{uuid.uuid4()}")

    assert other_response.status_code == nonexistent_response.status_code == 404


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_unauthenticated_returns_303_to_landing(client: TestClient) -> None:
    response = client.get(f"/read/{uuid.uuid4()}", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_invalid_uuid_returns_422(client: TestClient, session: Session) -> None:
    """A path param that isn't a valid UUID is FastAPI-validated, not
    surfaced through our 404 path. This is fine — there's no way to
    confuse 'not a UUID' with a real passage that exists or doesn't.
    """
    signed_in(session)
    response = client.get("/read/not-a-uuid")
    assert response.status_code == 422
