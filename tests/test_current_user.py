"""Tests for the current_user dependency.

Covers the Definition of Done from issue #11 (AUTH-3):
  - Auth-protected route + valid cookie → 200 with the right user
  - Missing cookie + browser request → 303 to /login
  - Missing cookie + HX-Request: true → 200 + HX-Redirect: /login
  - Tampered cookie → 303 (browser) / HX-Redirect (HTMX)
  - Cookie issued > 7 days ago → accepted AND re-issued (Set-Cookie present)
  - Cookie issued <= 7 days ago → accepted, NO re-issue
  - Cookie whose user_id is not in DB → 303
  - Malformed user_id in cookie → 303

The /api/me route is the canonical test target — it's protected by
Depends(current_user) and returns {id, email} for the signed-in user.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.user import User
from app.services.identity.session import (
    SESSION_COOKIE_NAME,
    _serializer,
    sign_session,
)

# Test environment uses the config default SESSION_SECRET ("dev-only").
TEST_SECRET = "dev-only"


def _seed_user(session: Session, email: str = "reader@example.com") -> User:
    user = User(email=email)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _craft_cookie_with_issued_at(
    *, user_id: uuid.UUID, issued_at: datetime, secret: str = TEST_SECRET
) -> str:
    """Sign a cookie with an explicit issued_at field.

    Used to test the rolling re-issue logic. The signature timestamp is
    `now` (so max_age verification passes), but the payload's issued_at
    can be back-dated to trigger the re-issue branch.
    """
    payload = {"user_id": str(user_id), "issued_at": issued_at.isoformat()}
    return _serializer(secret).dumps(payload)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_valid_cookie_returns_user_info(client: TestClient, session: Session) -> None:
    user = _seed_user(session, email="reader@example.com")
    cookie = sign_session(user_id=user.id, secret=TEST_SECRET)

    client.cookies.set(SESSION_COOKIE_NAME, cookie)
    response = client.get("/api/me")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(user.id)
    assert body["email"] == "reader@example.com"


# ---------------------------------------------------------------------------
# Unauthenticated → 303 (browser) / HX-Redirect (HTMX)
# ---------------------------------------------------------------------------


def test_missing_cookie_browser_request_redirects_to_landing(client: TestClient) -> None:
    response = client.get("/api/me", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_missing_cookie_htmx_request_returns_hx_redirect(client: TestClient) -> None:
    response = client.get("/api/me", headers={"HX-Request": "true"}, follow_redirects=False)
    assert response.status_code == 200
    assert response.headers.get("hx-redirect") == "/"


def test_tampered_cookie_browser_request_redirects(client: TestClient, session: Session) -> None:
    user = _seed_user(session)
    cookie = sign_session(user_id=user.id, secret=TEST_SECRET) + "x"  # tamper the suffix

    client.cookies.set(SESSION_COOKIE_NAME, cookie)
    response = client.get("/api/me", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_tampered_cookie_htmx_returns_hx_redirect(client: TestClient, session: Session) -> None:
    user = _seed_user(session)
    cookie = sign_session(user_id=user.id, secret=TEST_SECRET) + "x"

    client.cookies.set(SESSION_COOKIE_NAME, cookie)
    response = client.get("/api/me", headers={"HX-Request": "true"}, follow_redirects=False)

    assert response.status_code == 200
    assert response.headers.get("hx-redirect") == "/"


def test_cookie_for_deleted_user_redirects(client: TestClient, session: Session) -> None:
    """A cookie that's cryptographically valid but references a user_id
    that no longer exists in the DB must be treated as unauthenticated.
    Same outcome as forged or expired — preserves the "we don't reveal
    why" invariant.
    """
    cookie = sign_session(user_id=uuid.uuid4(), secret=TEST_SECRET)

    client.cookies.set(SESSION_COOKIE_NAME, cookie)
    response = client.get("/api/me", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_cookie_with_signed_secret_mismatch_redirects(client: TestClient) -> None:
    """A cookie signed with a different secret (e.g., from a previous
    SESSION_SECRET rotation) must not authenticate."""
    cookie = sign_session(user_id=uuid.uuid4(), secret="some-other-secret")

    client.cookies.set(SESSION_COOKIE_NAME, cookie)
    response = client.get("/api/me", follow_redirects=False)

    assert response.status_code == 303


# ---------------------------------------------------------------------------
# Rolling re-issue
# ---------------------------------------------------------------------------


def test_old_cookie_triggers_reissue(client: TestClient, session: Session) -> None:
    user = _seed_user(session)
    eight_days_ago = datetime.now(UTC) - timedelta(days=8)
    old_cookie = _craft_cookie_with_issued_at(user_id=user.id, issued_at=eight_days_ago)

    client.cookies.set(SESSION_COOKIE_NAME, old_cookie)
    response = client.get("/api/me", follow_redirects=False)

    assert response.status_code == 200

    # A new Set-Cookie header must be present (the rolling re-issue).
    set_cookie = response.headers.get("set-cookie", "")
    assert SESSION_COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Max-Age=2592000" in set_cookie


def test_fresh_cookie_does_not_trigger_reissue(client: TestClient, session: Session) -> None:
    """A cookie issued less than 7 days ago is accepted with no re-issue.
    This pins the threshold so a future tweak to SESSION_REISSUE_AFTER_DAYS
    can't silently re-issue on every request (which would be a perf and
    cookie-churn cost).
    """
    user = _seed_user(session)
    one_day_ago = datetime.now(UTC) - timedelta(days=1)
    fresh_cookie = _craft_cookie_with_issued_at(user_id=user.id, issued_at=one_day_ago)

    client.cookies.set(SESSION_COOKIE_NAME, fresh_cookie)
    response = client.get("/api/me", follow_redirects=False)

    assert response.status_code == 200
    # No Set-Cookie header; browser keeps using the cookie it sent.
    assert "set-cookie" not in {k.lower() for k in response.headers}


# ---------------------------------------------------------------------------
# Malformed payloads
# ---------------------------------------------------------------------------


def test_cookie_with_malformed_user_id_redirects(client: TestClient) -> None:
    """Cookie payload whose user_id is not a valid UUID string must
    redirect, not 500. Defensive: itsdangerous JSON decodes anything,
    so we rely on uuid.UUID(...) raising ValueError on garbage."""
    payload = {"user_id": "not-a-uuid", "issued_at": datetime.now(UTC).isoformat()}
    cookie = _serializer(TEST_SECRET).dumps(payload)

    client.cookies.set(SESSION_COOKIE_NAME, cookie)
    response = client.get("/api/me", follow_redirects=False)

    assert response.status_code == 303


def test_cookie_with_missing_user_id_redirects(client: TestClient) -> None:
    payload = {"issued_at": datetime.now(UTC).isoformat()}
    cookie = _serializer(TEST_SECRET).dumps(payload)

    client.cookies.set(SESSION_COOKIE_NAME, cookie)
    response = client.get("/api/me", follow_redirects=False)

    assert response.status_code == 303
