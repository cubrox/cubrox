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


def _make_passage(
    session: Session, owner_id: uuid.UUID, text: str = "The hidden words."
) -> Passage:
    p = Passage(
        owner_id=owner_id,
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


def test_reading_view_has_back_link_to_passage_input(client: TestClient, session: Session) -> None:
    """The reading view must offer a way back to the passage-input page
    (/passages/new) — otherwise a reader is stranded with no navigation.
    The link's accessible name is its visible text ('Add a passage'); the
    arrow glyph is decorative (aria-hidden)."""
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    response = client.get(f"/read/{passage.id}")
    body = response.text

    assert 'href="/passages/new"' in body
    # Pin the link's exact shape: decorative arrow (aria-hidden, not
    # announced) + the visible accessible name. A bare `aria-hidden`
    # substring check wouldn't guard this — the page has aria-hidden
    # elsewhere (the close beacon).
    assert '<span aria-hidden="true">&larr;</span> Add a passage' in body


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
    # Default max-width is "33em" (em, not ch — consistent across machines).
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
            owner_id=user.id,
            values={"size": "24px", "max_width": "28em"},
            updated_at=datetime.now(UTC),
        )
    )
    session.commit()

    response = client.get(f"/read/{passage.id}")
    body = response.text

    # Stored values take precedence.
    assert "--reader-size: 24px" in body
    assert "--reader-max-width: 28em" in body
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


# ---------------------------------------------------------------------------
# Multi-part document navigation (INGEST-3 #145)
# ---------------------------------------------------------------------------


def _make_document(session: Session, owner_id: uuid.UUID, n_parts: int) -> list[Passage]:
    """Create `n_parts` linked passages sharing one document_id."""
    document_id = uuid.uuid4()
    parts: list[Passage] = []
    for i in range(n_parts):
        text = f"Part {i} body text."
        p = Passage(
            owner_id=owner_id,
            text=text,
            text_hash=hashlib.sha256(text.encode("utf-8")).digest(),
            source_type="pdf",
            source_filename="big.pdf",
            document_id=document_id,
            part_index=i,
            part_count=n_parts,
        )
        session.add(p)
        parts.append(p)
    session.commit()
    for p in parts:
        session.refresh(p)
    return parts


def test_middle_part_shows_position_and_both_nav_links(
    client: TestClient, session: Session
) -> None:
    user = signed_in(session)
    parts = _make_document(session, user.id, 3)

    body = client.get(f"/read/{parts[1].id}").text

    assert 'aria-label="Document parts"' in body
    assert "Part 2 of 3" in body
    assert f"/read/{parts[0].id}" in body  # Previous
    assert f"/read/{parts[2].id}" in body  # Next


def test_first_part_has_next_but_no_previous(client: TestClient, session: Session) -> None:
    user = signed_in(session)
    parts = _make_document(session, user.id, 3)

    body = client.get(f"/read/{parts[0].id}").text

    assert "Part 1 of 3" in body
    assert "Next part" in body
    assert f"/read/{parts[1].id}" in body
    assert "Previous part" not in body


def test_last_part_has_previous_but_no_next(client: TestClient, session: Session) -> None:
    user = signed_in(session)
    parts = _make_document(session, user.id, 3)

    body = client.get(f"/read/{parts[2].id}").text

    assert "Part 3 of 3" in body
    assert "Previous part" in body
    assert f"/read/{parts[1].id}" in body
    assert "Next part" not in body


def test_standalone_passage_has_no_part_nav(client: TestClient, session: Session) -> None:
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    body = client.get(f"/read/{passage.id}").text

    assert 'aria-label="Document parts"' not in body
    assert "Part 1 of 1" not in body
