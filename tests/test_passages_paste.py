"""Tests for the paste-text ingestion flow.

Covers the Definition of Done from issue #13 (INGEST-1):
  - POST /passages with valid text → 303 to /read/<uuid>
  - Passage row has correct user_id, text, source_type='paste'
  - source_filename is NULL
  - text_hash exactly matches sha256(text.encode('utf-8'))
  - Empty text → 422
  - Text > 100,000 chars → 422
  - Unauthenticated POST → 303 to /login
  - Same text from two different users → two distinct rows
  - GET /passages/new renders a form posting to /passages
  - Unauthenticated GET → 303 to /login
"""

import hashlib
import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models.passage import Passage
from app.models.user import User
from app.services.identity.session import SESSION_COOKIE_NAME, sign_session

TEST_SECRET = "dev-only"


def _signed_in(client: TestClient, session: Session, email: str = "reader@example.com") -> User:
    """Seed a User and set a valid session cookie on the client."""
    user = User(email=email)
    session.add(user)
    session.commit()
    session.refresh(user)
    client.cookies.set(SESSION_COOKIE_NAME, sign_session(user_id=user.id, secret=TEST_SECRET))
    return user


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_post_passage_redirects_to_read_route(client: TestClient, session: Session) -> None:
    _signed_in(client, session)
    response = client.post("/passages", data={"text": "Hello, world."}, follow_redirects=False)
    assert response.status_code == 303

    location = response.headers["location"]
    assert location.startswith("/read/")

    # Tail of the URL must be a parseable UUID.
    passage_id_str = location.split("/")[-1]
    uuid.UUID(passage_id_str)  # raises if invalid


def test_passage_row_has_correct_fields(client: TestClient, session: Session) -> None:
    user = _signed_in(client, session)
    text = "O Son of Spirit! My first counsel is this..."

    client.post("/passages", data={"text": text}, follow_redirects=False)

    passages = session.exec(select(Passage)).all()
    assert len(passages) == 1
    p = passages[0]
    assert p.user_id == user.id
    assert p.text == text
    assert p.source_type == "paste"
    assert p.source_filename is None


def test_text_hash_matches_sha256_of_submitted_bytes(client: TestClient, session: Session) -> None:
    """The hash must be derived from the EXACT submitted bytes — no
    strip, no lowercase. This is the property that makes cross-user
    cache hits work."""
    _signed_in(client, session)
    text = "  the quick brown fox\nJUMPED over the lazy dog  "

    client.post("/passages", data={"text": text}, follow_redirects=False)

    passages = session.exec(select(Passage)).all()
    expected = hashlib.sha256(text.encode("utf-8")).digest()
    assert passages[0].text_hash == expected


def test_text_hash_is_thirty_two_bytes(client: TestClient, session: Session) -> None:
    _signed_in(client, session)
    client.post("/passages", data={"text": "x"}, follow_redirects=False)
    passages = session.exec(select(Passage)).all()
    assert len(passages[0].text_hash) == 32  # SHA-256 is exactly 32 bytes


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_empty_text_returns_422(client: TestClient, session: Session) -> None:
    _signed_in(client, session)
    response = client.post("/passages", data={"text": ""}, follow_redirects=False)
    assert response.status_code == 422


def test_text_at_limit_succeeds(client: TestClient, session: Session) -> None:
    """The boundary case: exactly 100,000 chars must still succeed."""
    _signed_in(client, session)
    text = "a" * 100_000
    response = client.post("/passages", data={"text": text}, follow_redirects=False)
    assert response.status_code == 303


def test_text_over_limit_returns_422(client: TestClient, session: Session) -> None:
    _signed_in(client, session)
    text = "a" * 100_001
    response = client.post("/passages", data={"text": text}, follow_redirects=False)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_unauthenticated_post_redirects_to_login(client: TestClient) -> None:
    response = client.post("/passages", data={"text": "anything"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_unauthenticated_get_form_redirects_to_login(client: TestClient) -> None:
    response = client.get("/passages/new", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


# ---------------------------------------------------------------------------
# Cross-user isolation
# ---------------------------------------------------------------------------


def test_same_text_from_two_users_creates_two_distinct_rows(
    client: TestClient, session: Session
) -> None:
    """Different users pasting the same text get separate Passage rows
    (no cross-user dedup at the row level — only the comprehension cache
    is shared, via text_hash)."""
    user_a = User(email="a@example.com")
    user_b = User(email="b@example.com")
    session.add(user_a)
    session.add(user_b)
    session.commit()
    session.refresh(user_a)
    session.refresh(user_b)

    same_text = "The same passage, pasted by two different readers."

    client.cookies.set(SESSION_COOKIE_NAME, sign_session(user_id=user_a.id, secret=TEST_SECRET))
    client.post("/passages", data={"text": same_text}, follow_redirects=False)

    client.cookies.set(SESSION_COOKIE_NAME, sign_session(user_id=user_b.id, secret=TEST_SECRET))
    client.post("/passages", data={"text": same_text}, follow_redirects=False)

    passages = session.exec(select(Passage)).all()
    assert len(passages) == 2
    assert {p.user_id for p in passages} == {user_a.id, user_b.id}
    # Both rows share the same text_hash (the cache lookup key).
    assert passages[0].text_hash == passages[1].text_hash


# ---------------------------------------------------------------------------
# Form rendering
# ---------------------------------------------------------------------------


def test_get_passages_new_renders_form(client: TestClient, session: Session) -> None:
    _signed_in(client, session)
    response = client.get("/passages/new")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<form" in response.text
    assert "<textarea" in response.text
    assert 'action="/passages"' in response.text
    assert 'method="post"' in response.text


def test_get_passages_new_form_includes_required_attribute(
    client: TestClient, session: Session
) -> None:
    """Browsers should refuse to submit an empty textarea client-side
    too — server validation is the gate, but the HTML attribute is the
    UX courtesy."""
    _signed_in(client, session)
    response = client.get("/passages/new")
    assert "required" in response.text
