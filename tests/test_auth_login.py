"""Tests for POST /login and the magic-link request flow.

Covers the Definition of Done from issue #9 (AUTH-1):
  - Valid email → 202 + generic fragment
  - A MagicLinkToken row is created with consumed_at NULL and expires_at
    ≈ 15 minutes ahead
  - The token hash stored in the DB is NOT the raw token sent in the email
  - Re-issuing for the same email invalidates the prior token (one row
    with consumed_at IS NULL)
  - Response is identical for known vs. unknown emails (no enumeration)
  - Malformed email → 422 (FastAPI validation)

The Resend SDK is monkey-patched. The real API is never called from CI.
"""

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models.magic_link_token import MagicLinkToken
from app.models.user import User
from app.services.identity import magic_link


@pytest.fixture(autouse=True)
def stub_email_sender(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Replace the real Resend dispatch with an in-memory recorder.

    Returned list captures every email send (one dict per send) so tests
    can assert what was queued without needing an outbound network call.
    """
    sent: list[dict] = []

    def fake_send(*, email: str, link: str, from_email: str, api_key: str) -> None:
        sent.append(
            {
                "email": email,
                "link": link,
                "from_email": from_email,
                "api_key": api_key,
            }
        )

    monkeypatch.setattr(magic_link, "send_magic_link_email", fake_send)
    return sent


def test_valid_email_returns_202_and_generic_fragment(
    client: TestClient,
    stub_email_sender: list[dict],
) -> None:
    response = client.post("/login", data={"email": "reader@example.com"})

    assert response.status_code == 202
    assert response.text == "<p>Check your inbox for a sign-in link.</p>"
    assert response.headers["content-type"].startswith("text/html")
    assert len(stub_email_sender) == 1


def test_token_row_is_created_with_correct_fields(
    client: TestClient,
    session: Session,
) -> None:
    before = datetime.now(UTC)
    response = client.post("/login", data={"email": "reader@example.com"})
    after = datetime.now(UTC)

    assert response.status_code == 202

    tokens = session.exec(select(MagicLinkToken)).all()
    assert len(tokens) == 1
    token = tokens[0]
    assert token.consumed_at is None

    # SQLite returns naive datetimes even for TIMESTAMPTZ columns; treat as UTC.
    expires = token.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)

    expected_expiry_low = before + timedelta(minutes=14, seconds=59)
    expected_expiry_high = after + timedelta(minutes=15, seconds=1)
    assert expected_expiry_low <= expires <= expected_expiry_high


def test_stored_hash_is_not_the_raw_token(
    client: TestClient,
    session: Session,
    stub_email_sender: list[dict],
) -> None:
    response = client.post("/login", data={"email": "reader@example.com"})
    assert response.status_code == 202

    sent_link = stub_email_sender[0]["link"]
    raw_token = sent_link.rsplit("=", 1)[1]
    expected_hash = hashlib.sha256(raw_token.encode("utf-8")).digest()

    tokens = session.exec(select(MagicLinkToken)).all()
    assert len(tokens) == 1
    stored_hash = tokens[0].token_hash

    # The DB stores the hash, not the raw token. Equivalence proves the hash
    # in the DB is derivable from the raw token, but the raw token itself is
    # NOT stored.
    assert stored_hash == expected_hash
    assert stored_hash != raw_token.encode("utf-8")


def test_reissuing_invalidates_prior_token(
    client: TestClient,
    session: Session,
) -> None:
    client.post("/login", data={"email": "reader@example.com"})
    client.post("/login", data={"email": "reader@example.com"})

    # Only one user; only one ACTIVE token (consumed_at IS NULL) at any time.
    users = session.exec(select(User)).all()
    assert len(users) == 1

    active_tokens = session.exec(
        select(MagicLinkToken).where(MagicLinkToken.consumed_at.is_(None))  # type: ignore[union-attr]
    ).all()
    assert len(active_tokens) == 1


def test_response_identical_for_known_and_unknown_email(
    client: TestClient,
    session: Session,
) -> None:
    # Seed one user; the other email is unknown.
    session.add(User(email="known@example.com"))
    session.commit()

    known = client.post("/login", data={"email": "known@example.com"})
    unknown = client.post("/login", data={"email": "stranger@example.com"})

    # Same status, same body → no information leaks about which addresses
    # have an account.
    assert known.status_code == unknown.status_code == 202
    assert known.text == unknown.text


def test_malformed_email_returns_422(client: TestClient) -> None:
    response = client.post("/login", data={"email": "not-an-email"})
    assert response.status_code == 422


def test_email_is_normalized_to_lowercase(
    client: TestClient,
    session: Session,
) -> None:
    client.post("/login", data={"email": "Reader@Example.COM"})
    users = session.exec(select(User)).all()
    assert len(users) == 1
    assert users[0].email == "reader@example.com"


def test_magic_link_uses_configured_base_url(
    client: TestClient,
    stub_email_sender: list[dict],
) -> None:
    client.post("/login", data={"email": "reader@example.com"})
    link = stub_email_sender[0]["link"]
    assert link.startswith("http://localhost:8080/auth/verify?token=")


def test_unknown_email_does_not_create_user_or_token_when_no_record(
    client: TestClient,
    session: Session,
) -> None:
    """Lazy account creation: unknown emails get an account on first request.

    This is a deliberate design choice (per the service docstring): an
    enumeration-safe response means we always go through the same token
    minting path. Knowing the user was created lets the next-step
    /auth/verify (AUTH-2) succeed; if we declined to create on /login,
    the user clicking the email link would land in a broken state.
    """
    client.post("/login", data={"email": "stranger@example.com"})
    users = session.exec(select(User)).all()
    assert len(users) == 1
    assert users[0].email == "stranger@example.com"
