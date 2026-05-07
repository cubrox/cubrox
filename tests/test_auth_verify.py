"""Tests for GET /auth/verify and the session-cookie sign/verify helpers.

Covers the Definition of Done from issue #10 (AUTH-2):
  - Valid unconsumed token → 303 redirect to / with a signed cookie
  - Cookie has HttpOnly, Secure, SameSite=Lax, Max-Age = 30 * 86400
  - Cookie payload contains user_id + issued_at; issued_at within last second
  - Re-using a consumed token → 410
  - Expired token → 410
  - Forged / unknown token → 410
  - Cookie payload does NOT contain email or any PII

Also: unit tests on the sign_session / verify_session helpers (round-trip,
wrong secret, tampered value, expired).
"""

import hashlib
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.magic_link_token import MagicLinkToken
from app.models.user import User
from app.services.identity.session import (
    SESSION_COOKIE_NAME,
    sign_session,
    verify_session,
)

# Test environment runs with the config default SESSION_SECRET ("dev-only");
# the validator only rejects that default outside development.
TEST_SECRET = "dev-only"


def _seed_active_token(
    session: Session,
    *,
    email: str = "reader@example.com",
    expires_in_minutes: int = 15,
) -> tuple[User, str]:
    """Seed a user + active magic-link token. Returns (user, raw_token)."""
    user = User(email=email)
    session.add(user)
    session.flush()

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).digest()
    session.add(
        MagicLinkToken(
            token_hash=token_hash,
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(minutes=expires_in_minutes),
        )
    )
    session.commit()
    return user, raw_token


# ---------------------------------------------------------------------------
# Route-level tests
# ---------------------------------------------------------------------------


def test_valid_token_returns_303_redirect_to_root(
    client: TestClient,
    session: Session,
) -> None:
    _, raw_token = _seed_active_token(session)
    response = client.get(f"/auth/verify?token={raw_token}", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_valid_token_sets_session_cookie(
    client: TestClient,
    session: Session,
) -> None:
    user, raw_token = _seed_active_token(session)
    response = client.get(f"/auth/verify?token={raw_token}", follow_redirects=False)

    cookie_value = response.cookies.get(SESSION_COOKIE_NAME)
    assert cookie_value is not None
    payload = verify_session(value=cookie_value, secret=TEST_SECRET, max_age_seconds=30 * 86400)
    assert payload is not None
    assert payload["user_id"] == str(user.id)


def test_cookie_attributes_match_spec(
    client: TestClient,
    session: Session,
) -> None:
    _, raw_token = _seed_active_token(session)
    response = client.get(f"/auth/verify?token={raw_token}", follow_redirects=False)

    set_cookie = response.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=lax" in set_cookie or "SameSite=Lax" in set_cookie
    # 30 days * 86400 seconds = 2,592,000
    assert "Max-Age=2592000" in set_cookie


def test_cookie_payload_contains_user_id_and_issued_at(
    client: TestClient,
    session: Session,
) -> None:
    user, raw_token = _seed_active_token(session)
    before = datetime.now(UTC)
    response = client.get(f"/auth/verify?token={raw_token}", follow_redirects=False)
    after = datetime.now(UTC)

    cookie_value = response.cookies[SESSION_COOKIE_NAME]
    payload = verify_session(value=cookie_value, secret=TEST_SECRET, max_age_seconds=30 * 86400)
    assert payload is not None

    assert payload["user_id"] == str(user.id)
    issued_at = datetime.fromisoformat(payload["issued_at"])
    assert before - timedelta(seconds=1) <= issued_at <= after + timedelta(seconds=1)


def test_cookie_payload_does_not_leak_email(
    client: TestClient,
    session: Session,
) -> None:
    user, raw_token = _seed_active_token(session, email="leakable-handle@example.com")
    response = client.get(f"/auth/verify?token={raw_token}", follow_redirects=False)

    cookie_value = response.cookies[SESSION_COOKIE_NAME]
    # The signed cookie is base64-ish; if 'leakable-handle' appears in it we
    # leaked PII. itsdangerous payloads ARE base64-encoded JSON, so any
    # plaintext substring would survive.
    assert "leakable-handle" not in cookie_value
    assert "@example.com" not in cookie_value

    payload = verify_session(value=cookie_value, secret=TEST_SECRET, max_age_seconds=30 * 86400)
    assert payload is not None
    assert "email" not in payload
    assert payload["user_id"] == str(user.id)


def test_reusing_token_returns_410(
    client: TestClient,
    session: Session,
) -> None:
    _, raw_token = _seed_active_token(session)

    first = client.get(f"/auth/verify?token={raw_token}", follow_redirects=False)
    assert first.status_code == 303

    second = client.get(f"/auth/verify?token={raw_token}", follow_redirects=False)
    assert second.status_code == 410


def test_expired_token_returns_410(
    client: TestClient,
    session: Session,
) -> None:
    _, raw_token = _seed_active_token(session, expires_in_minutes=-60)
    response = client.get(f"/auth/verify?token={raw_token}", follow_redirects=False)
    assert response.status_code == 410


def test_forged_or_unknown_token_returns_410(
    client: TestClient,
) -> None:
    """A token that was never issued — or has been tampered with — must be
    rejected with the same response as expired/consumed tokens. Same status
    means an attacker can't tell which case applied.
    """
    response = client.get(
        "/auth/verify?token=this-token-was-never-issued-and-is-completely-forged",
        follow_redirects=False,
    )
    assert response.status_code == 410


def test_token_marked_consumed_after_successful_verify(
    client: TestClient,
    session: Session,
) -> None:
    _, raw_token = _seed_active_token(session)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).digest()

    client.get(f"/auth/verify?token={raw_token}", follow_redirects=False)
    session.expire_all()

    row = session.get(MagicLinkToken, token_hash)
    assert row is not None
    assert row.consumed_at is not None


# ---------------------------------------------------------------------------
# Unit tests on the session helpers
# ---------------------------------------------------------------------------


def test_sign_and_verify_round_trip() -> None:
    user_id = uuid.uuid4()
    cookie = sign_session(user_id=user_id, secret="round-trip-secret")
    payload = verify_session(value=cookie, secret="round-trip-secret", max_age_seconds=3600)
    assert payload is not None
    assert payload["user_id"] == str(user_id)


def test_verify_with_wrong_secret_returns_none() -> None:
    cookie = sign_session(user_id=uuid.uuid4(), secret="real")
    assert verify_session(value=cookie, secret="forged", max_age_seconds=3600) is None


def test_verify_with_tampered_value_returns_none() -> None:
    cookie = sign_session(user_id=uuid.uuid4(), secret="s")
    tampered = cookie + "x"
    assert verify_session(value=tampered, secret="s", max_age_seconds=3600) is None


def test_verify_expired_returns_none() -> None:
    cookie = sign_session(user_id=uuid.uuid4(), secret="s")
    # itsdangerous rounds timestamps to 1-second granularity; sleep generously
    # past the max_age to ensure the SignatureExpired path is exercised
    # regardless of fractional-second alignment.
    time.sleep(2.1)
    assert verify_session(value=cookie, secret="s", max_age_seconds=1) is None


def test_verify_garbage_value_returns_none() -> None:
    assert verify_session(value="not-a-real-cookie", secret="s", max_age_seconds=3600) is None


# A fixed reference UUID so each parametrized run compares the SAME pair
# of values: a known reference vs. the parametrized "other." Without this,
# a randomly-chosen comparison UUID would mean the parametrize was
# decorative — the assertion would pass for the wrong structural reason.
_REFERENCE_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


@pytest.mark.parametrize(
    "other_user_id",
    [
        uuid.UUID("00000000-0000-0000-0000-000000000001"),
        uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
    ],
)
def test_sign_session_produces_distinct_cookies_per_user(other_user_id: uuid.UUID) -> None:
    """Two different user_ids must produce different cookie values.

    The parametrize varies the "other" user_id while a fixed reference
    user_id stays constant — so the property under test ("different inputs
    yield different outputs") is what's actually exercised, not just
    "two random sign_session calls produce different bytes."
    """
    reference = sign_session(user_id=_REFERENCE_USER_ID, secret="s")
    other = sign_session(user_id=other_user_id, secret="s")
    assert reference != other
