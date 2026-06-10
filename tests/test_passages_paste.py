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
from tests.conftest import signed_in

# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_post_passage_redirects_to_read_route(client: TestClient, session: Session) -> None:
    signed_in(session)
    response = client.post("/passages", data={"text": "Hello, world."}, follow_redirects=False)
    assert response.status_code == 303

    location = response.headers["location"]
    assert location.startswith("/read/")

    # Tail of the URL must be a parseable UUID.
    passage_id_str = location.split("/")[-1]
    uuid.UUID(passage_id_str)  # raises if invalid


def test_passage_row_has_correct_fields(client: TestClient, session: Session) -> None:
    user = signed_in(session)
    text = "O Son of Spirit! My first counsel is this..."

    client.post("/passages", data={"text": text}, follow_redirects=False)

    passages = session.exec(select(Passage)).all()
    assert len(passages) == 1
    p = passages[0]
    assert p.owner_id == user.id
    assert p.text == text
    assert p.source_type == "paste"
    assert p.source_filename is None


def test_text_hash_matches_sha256_of_submitted_bytes(client: TestClient, session: Session) -> None:
    """The hash must be derived from the EXACT submitted bytes — no
    strip, no lowercase. This is the property that makes cross-user
    cache hits work."""
    signed_in(session)
    text = "  the quick brown fox\nJUMPED over the lazy dog  "

    client.post("/passages", data={"text": text}, follow_redirects=False)

    passages = session.exec(select(Passage)).all()
    expected = hashlib.sha256(text.encode("utf-8")).digest()
    assert passages[0].text_hash == expected


def test_text_hash_is_thirty_two_bytes(client: TestClient, session: Session) -> None:
    signed_in(session)
    client.post("/passages", data={"text": "x"}, follow_redirects=False)
    passages = session.exec(select(Passage)).all()
    assert len(passages[0].text_hash) == 32  # SHA-256 is exactly 32 bytes


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_empty_text_returns_422(client: TestClient, session: Session) -> None:
    signed_in(session)
    response = client.post("/passages", data={"text": ""}, follow_redirects=False)
    assert response.status_code == 422


def test_text_at_limit_succeeds(client: TestClient, session: Session) -> None:
    """The boundary case: exactly 100,000 chars must still succeed."""
    signed_in(session)
    text = "a" * 100_000
    response = client.post("/passages", data={"text": text}, follow_redirects=False)
    assert response.status_code == 303


def test_text_over_limit_auto_splits_into_linked_parts(
    client: TestClient, session: Session
) -> None:
    """INGEST-3 (#145): over-cap text is auto-split into linked parts instead
    of rejected. Redirects to part 0; the parts share a document_id, are
    ordered, and concatenate back to the original (no loss)."""
    user = signed_in(session)
    text = "a" * 100_001  # just over MAX_TEXT_LEN → 2 parts at the 80k target
    response = client.post("/passages", data={"text": text}, follow_redirects=False)
    assert response.status_code == 303

    rows = session.exec(
        select(Passage).where(Passage.owner_id == user.id).order_by(Passage.part_index)  # type: ignore[arg-type]
    ).all()
    assert len(rows) == 2
    assert {r.part_index for r in rows} == {0, 1}
    assert all(r.part_count == 2 for r in rows)
    # All parts belong to the same (non-null) document.
    doc_ids = {r.document_id for r in rows}
    assert len(doc_ids) == 1 and None not in doc_ids
    # No text lost or reordered.
    assert "".join(r.text for r in rows) == text
    # Redirect lands on part 0.
    assert response.headers["location"] == f"/read/{rows[0].id}"


def test_text_at_limit_stays_a_single_standalone_passage(
    client: TestClient, session: Session
) -> None:
    """At/under the cap, behavior is unchanged: one standalone passage with
    document_id=None and part_count=1 (no nav)."""
    user = signed_in(session)
    text = "a" * 100_000
    client.post("/passages", data={"text": text}, follow_redirects=False)

    rows = session.exec(select(Passage).where(Passage.owner_id == user.id)).all()  # type: ignore[arg-type]
    assert len(rows) == 1
    assert rows[0].document_id is None
    assert rows[0].part_count == 1
    assert rows[0].part_index == 0


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_unauthenticated_post_redirects_to_landing(client: TestClient) -> None:
    response = client.post("/passages", data={"text": "anything"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_unauthenticated_get_form_redirects_to_landing(client: TestClient) -> None:
    response = client.get("/passages/new", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"


# ---------------------------------------------------------------------------
# Cross-user isolation
# ---------------------------------------------------------------------------


def test_same_text_from_two_users_creates_two_distinct_rows(
    client: TestClient, session: Session
) -> None:
    """Different users pasting the same text get separate Passage rows
    (no cross-user dedup at the row level — only the comprehension cache
    is shared, via text_hash)."""
    user_a = signed_in(session, email="a@example.com")
    same_text = "The same passage, pasted by two different readers."
    client.post("/passages", data={"text": same_text}, follow_redirects=False)

    # Swap who's "current" for the second post — signed_in resets the
    # dependency override to the new user.
    user_b = signed_in(session, email="b@example.com")
    client.post("/passages", data={"text": same_text}, follow_redirects=False)

    passages = session.exec(select(Passage)).all()
    assert len(passages) == 2
    assert {p.owner_id for p in passages} == {user_a.id, user_b.id}
    # Both rows share the same text_hash (the cache lookup key).
    assert passages[0].text_hash == passages[1].text_hash


# ---------------------------------------------------------------------------
# Form rendering
# ---------------------------------------------------------------------------


def test_get_passages_new_renders_form(client: TestClient, session: Session) -> None:
    signed_in(session)
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
    signed_in(session)
    response = client.get("/passages/new")
    assert "required" in response.text
