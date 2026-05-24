"""Tests for POST /passages/{passage_id}/close (METRIC-2 #22).

Covers the Definition of Done from issue #22:
  - Happy path: 204 + one reading_event row with the right user/passage/lines
  - Owner check: posting to another user's passage → 404, no row
  - Validation: lines=0, lines=-1, lines=100001 silently rejected (204, no row)
  - Auth: unauthenticated → HX-Redirect to landing page (per AUTH-3),
    no row inserted
  - Template wiring: GET /read/<id> contains the close-beacon div
    pointed at the right URL pattern
"""

import hashlib
import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models.passage import Passage
from app.models.reading_event import ReadingEvent
from tests.conftest import make_user, signed_in


def _make_passage(
    session: Session, user_id: uuid.UUID, text: str = "Some lines\nto read."
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
# Happy path
# ---------------------------------------------------------------------------


def test_close_inserts_reading_event_and_returns_204(client: TestClient, session: Session) -> None:
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    response = client.post(f"/passages/{passage.id}/close", data={"lines": 42})
    assert response.status_code == 204
    # 204 by spec carries no body.
    assert response.text == ""

    rows = session.exec(select(ReadingEvent)).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.user_id == user.id
    assert row.passage_id == passage.id
    assert row.lines_processed == 42


def test_close_with_lines_at_lower_bound_persists(client: TestClient, session: Session) -> None:
    """`lines=1` is the minimum allowed value (the route's CHECK is >= 1)."""
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    response = client.post(f"/passages/{passage.id}/close", data={"lines": 1})
    assert response.status_code == 204

    rows = session.exec(select(ReadingEvent)).all()
    assert len(rows) == 1
    assert rows[0].lines_processed == 1


def test_close_with_lines_at_upper_bound_persists(client: TestClient, session: Session) -> None:
    """`lines=100_000` is the maximum allowed value (matches the
    INGEST-1 paste cap)."""
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    response = client.post(f"/passages/{passage.id}/close", data={"lines": 100_000})
    assert response.status_code == 204

    rows = session.exec(select(ReadingEvent)).all()
    assert len(rows) == 1
    assert rows[0].lines_processed == 100_000


# ---------------------------------------------------------------------------
# Owner check
# ---------------------------------------------------------------------------


def test_close_on_other_users_passage_returns_404_no_row(
    client: TestClient, session: Session
) -> None:
    """Same 404 + same body as cross-user GET /read. Existence isn't
    leaked, and crucially no reading_event row is attributed to the
    wrong user."""
    signed_in(session)
    # The signed-in user is irrelevant to the passage we'll target —
    # create a separate user and a passage they own.
    other = make_user(session, email="someone-else@example.com")
    other_passage = _make_passage(session, other.id)

    response = client.post(f"/passages/{other_passage.id}/close", data={"lines": 5})
    assert response.status_code == 404

    rows = session.exec(select(ReadingEvent)).all()
    assert rows == []


def test_close_on_nonexistent_passage_returns_404_no_row(
    client: TestClient, session: Session
) -> None:
    """A UUID that doesn't exist gets the same 404 as a cross-user
    passage. Same code path."""
    signed_in(session)
    response = client.post(
        f"/passages/{uuid.uuid4()}/close",
        data={"lines": 5},
    )
    assert response.status_code == 404
    assert session.exec(select(ReadingEvent)).all() == []


# ---------------------------------------------------------------------------
# Validation — out-of-range silently rejected
# ---------------------------------------------------------------------------


def test_close_with_lines_zero_silently_rejected(client: TestClient, session: Session) -> None:
    """`lines=0` is meaningless noise. The unload path can't surface
    errors, so the route returns 204 + drops the data + logs a WARN."""
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    response = client.post(f"/passages/{passage.id}/close", data={"lines": 0})
    assert response.status_code == 204
    assert session.exec(select(ReadingEvent)).all() == []


def test_close_with_lines_negative_silently_rejected(client: TestClient, session: Session) -> None:
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    response = client.post(f"/passages/{passage.id}/close", data={"lines": -1})
    assert response.status_code == 204
    assert session.exec(select(ReadingEvent)).all() == []


def test_close_with_lines_over_max_silently_rejected(client: TestClient, session: Session) -> None:
    """100_001 is one above the cap. Mirrors INGEST-1's text-length
    limit; anything higher means the client is lying or the
    measurement broke."""
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    response = client.post(
        f"/passages/{passage.id}/close",
        data={"lines": 100_001},
    )
    assert response.status_code == 204
    assert session.exec(select(ReadingEvent)).all() == []


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_close_unauthenticated_redirects_no_row(client: TestClient, session: Session) -> None:
    """Unauth requests get the AUTH-3 redirect (HX-Redirect when the
    request is HTMX, 303 otherwise — both target the landing page `/`
    since PR #40, not `/login`). No reading_event row is created.

    Note: ticket text references `/login` from before the redirect-fix
    PR landed. The current production behavior is `/`. Tests pin the
    real target."""
    passage_id = uuid.uuid4()

    # HTMX-style request (matches the unload beacon in production).
    response = client.post(
        f"/passages/{passage_id}/close",
        data={"lines": 5},
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert response.headers.get("hx-redirect") == "/"
    assert session.exec(select(ReadingEvent)).all() == []

    # Browser-style request (no HX-Request header) → 303 to landing.
    response = client.post(
        f"/passages/{passage_id}/close",
        data={"lines": 5},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert session.exec(select(ReadingEvent)).all() == []


# ---------------------------------------------------------------------------
# Template wiring
# ---------------------------------------------------------------------------


def test_reading_view_template_contains_close_beacon(client: TestClient, session: Session) -> None:
    """The reading view must emit the hidden close-beacon div pointed
    at the right URL. Without this, the route exists but no client
    ever calls it."""
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    response = client.get(f"/read/{passage.id}")
    body = response.text
    assert f'hx-post="/passages/{passage.id}/close"' in body
    assert 'hx-trigger="unload from:body"' in body
    # The hx-vals JS expression pulls from the inline-script-set global.
    assert "window.cubroxLineCount" in body


def test_reading_view_template_contains_line_count_script(
    client: TestClient, session: Session
) -> None:
    """The inline <script> that measures the rendered <article>'s
    height and sets window.cubroxLineCount must be present. Pin it
    so a future refactor doesn't silently drop the measurement."""
    user = signed_in(session)
    passage = _make_passage(session, user.id)

    body = client.get(f"/read/{passage.id}").text
    assert "window.cubroxLineCount" in body
    # The script reads computed line-height — pin the property reference
    # so a refactor that drops it surfaces here, not in production.
    assert "lineHeight" in body
