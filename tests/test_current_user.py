"""Tests for the `current_user` FastAPI dependency (Supabase path).

After SUPA-3 (#82), `current_user` is dual-path:
  1. Supabase JWT cookie (`sb-access-token`) — validated via Supabase
     Auth, then a lazy `_ensure_neon_user_mirror` upserts a row in the
     legacy `user` table so every other route keeps seeing the same
     `User` SQLModel.
  2. Legacy itsdangerous cookie — covered indirectly by the many
     tests that use `signed_in(session)` to authenticate (which
     overrides `current_user` via `app.dependency_overrides`, exercising
     the same dependency-resolution path).

This file focuses on path 1 — the Supabase half — since path 2 is
exercised across the whole test suite. After SUPA-2c (#91) deletes
the legacy fallback, only path 1 remains and this file stays valid.

Rewritten in SUPA-5 (#84). The pre-SUPA-3 tests covered the
itsdangerous signature / reissue / tamper semantics that no longer
apply.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models.user import User

SUPABASE_COOKIE = "sb-access-token"


def test_valid_supabase_jwt_returns_user_info(
    client: TestClient, supabase_mock: MagicMock
) -> None:
    """The happy path. A valid Supabase JWT cookie → /api/me returns
    the user's id + email. The lazy mirror creates a corresponding
    Neon User row keyed on the Supabase user.id."""
    fake_id = str(uuid4())
    fake_user = SimpleNamespace(id=fake_id, email="reader@example.com")
    supabase_mock.auth.get_user.return_value = SimpleNamespace(user=fake_user)
    client.cookies.set(SUPABASE_COOKIE, "valid-jwt")

    response = client.get("/api/me")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "reader@example.com"
    assert body["id"] == fake_id


def test_lazy_mirror_creates_neon_user_row(
    client: TestClient, session: Session, supabase_mock: MagicMock
) -> None:
    """First time a given Supabase user hits a protected route, the
    shim should insert a `User` row whose PK matches the Supabase
    user.id."""
    fake_id = str(uuid4())
    fake_user = SimpleNamespace(id=fake_id, email="newcomer@example.com")
    supabase_mock.auth.get_user.return_value = SimpleNamespace(user=fake_user)
    client.cookies.set(SUPABASE_COOKIE, "valid-jwt")

    # Before: no row for this id.
    import uuid as _uuid

    assert session.get(User, _uuid.UUID(fake_id)) is None

    client.get("/api/me")

    # After: row exists with the email Supabase reported.
    row = session.get(User, _uuid.UUID(fake_id))
    assert row is not None
    assert row.email == "newcomer@example.com"


def test_lazy_mirror_is_idempotent(
    client: TestClient, session: Session, supabase_mock: MagicMock
) -> None:
    """Two requests for the same user → still one row, no IntegrityError."""
    fake_id = str(uuid4())
    fake_user = SimpleNamespace(id=fake_id, email="returning@example.com")
    supabase_mock.auth.get_user.return_value = SimpleNamespace(user=fake_user)
    client.cookies.set(SUPABASE_COOKIE, "valid-jwt")

    client.get("/api/me")
    client.get("/api/me")

    import uuid as _uuid

    rows = session.exec(select(User).where(User.id == _uuid.UUID(fake_id))).all()  # type: ignore[arg-type]
    assert len(rows) == 1


def test_missing_cookie_browser_request_redirects_to_landing(
    client: TestClient,
) -> None:
    """No cookies of either kind → 303 to /. The dual-path falls
    through both branches before raising UnauthenticatedError, which
    the app-level handler converts to a redirect."""
    response = client.get("/api/me", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_missing_cookie_htmx_request_returns_hx_redirect(client: TestClient) -> None:
    """HTMX requests get the HX-Redirect header (HTMX intercepts the
    response before the browser sees a real redirect)."""
    response = client.get("/api/me", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert response.headers["HX-Redirect"] == "/"


def test_invalid_supabase_jwt_falls_through_and_redirects(
    client: TestClient, supabase_mock: MagicMock
) -> None:
    """sb-access-token present but Supabase returns no user → the
    transitional shim falls through to the legacy path (no legacy
    cookie either) → UnauthenticatedError → 303."""
    supabase_mock.auth.get_user.return_value = SimpleNamespace(user=None)
    client.cookies.set(SUPABASE_COOKIE, "expired-or-forged")
    response = client.get("/api/me", follow_redirects=False)
    assert response.status_code == 303


def test_supabase_raises_falls_through_and_redirects(
    client: TestClient, supabase_mock: MagicMock
) -> None:
    """If supabase-py raises, treat as unauthenticated (don't surface
    a 500 — the user just gets bounced to the landing page)."""
    supabase_mock.auth.get_user.side_effect = RuntimeError("network")
    client.cookies.set(SUPABASE_COOKIE, "garbage")
    response = client.get("/api/me", follow_redirects=False)
    assert response.status_code == 303
