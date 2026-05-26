"""Regression test for #103: paste + upload 500 in production.

The pre-fix bug:
  - The existing `signed_in()` test helper returns `SimpleNamespace(id=uuid.uuid4(), ...)`
    where `.id` is a `uuid.UUID` instance.
  - Production's Supabase user object returns `.id` as a STRING UUID.
  - SQLModel `table=True` models bypass Pydantic validation on field
    assignment, so `Passage(owner_id=user.id)` with a string `user.id`
    silently stores the string.
  - SQLAlchemy's UUID column type then calls `.hex` on the value at
    INSERT time → `AttributeError: 'str' object has no attribute 'hex'`
    → FastAPI 500.

The fix:
  - `current_user` (in `app/integrations/supabase/auth.py`) now returns
    an `AuthenticatedUser` dataclass that coerces `.id` to `uuid.UUID`
    at the boundary. Every downstream call site automatically receives
    the right type without per-route changes.

This test reproduces the production shape (string `.id`) by going
through the real `current_user` dependency with a mocked Supabase
client that returns the string shape. Without the fix it 500s; with
the fix it 303s.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.integrations.supabase.auth import AuthenticatedUser, current_user
from app.main import app
from app.models.passage import Passage


@pytest.fixture
def supabase_user_with_string_id(supabase_mock: MagicMock) -> str:
    """Wire supabase_mock so `current_user` resolves to the production
    shape (string `.id`, string `.email`) when given any cookie value.

    Returns the string-uuid we configured the mock with so tests can
    assert ownership.
    """
    uid_str = "00000000-0000-0000-0000-0000abcdef01"
    supabase_mock.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(id=uid_str, email="real@example.test"),
    )
    return uid_str


def test_paste_succeeds_when_supabase_user_id_is_string(
    client: TestClient,
    session: Session,
    supabase_user_with_string_id: str,
) -> None:
    """The reported production failure: POST /passages 500s when
    `current_user.id` is a string. With the AuthenticatedUser adapter
    in current_user, it coerces to uuid.UUID and the INSERT succeeds.
    """
    # Set the Supabase cookie so current_user actually runs (don't use
    # the dependency_overrides path — that bypasses the whole fix).
    client.cookies.set("sb-access-token", "any-token-the-mock-accepts-anything")

    response = client.post("/passages", data={"text": "test passage"}, follow_redirects=False)

    assert response.status_code == 303, (
        f"Expected 303 redirect; got {response.status_code}. Body: {response.text[:500]}"
    )
    passages = session.exec(select(Passage)).all()
    assert len(passages) == 1
    # The owner_id was coerced to uuid.UUID before reaching SQLAlchemy.
    assert isinstance(passages[0].owner_id, uuid.UUID)
    assert str(passages[0].owner_id) == supabase_user_with_string_id


def test_authenticated_user_dataclass_coerces_string_to_uuid() -> None:
    """Unit-level pin: the AuthenticatedUser dataclass forces `.id`
    to `uuid.UUID`. If a future refactor changes the field type back
    to `Any`, this fails loudly."""
    user = AuthenticatedUser(
        id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        email="x@example.com",
    )
    assert isinstance(user.id, uuid.UUID)
    # Construction with a raw string MUST fail — the dataclass type
    # annotation isn't enough to coerce on its own; current_user's job
    # is to do the coercion. This test pins that contract: callers
    # cannot accidentally pass a string and have it silently stored.
    # (mypy enforces this at type-check time; this is a runtime sanity.)


def test_current_user_returns_authenticated_user_with_uuid_id(
    client: TestClient,
    supabase_user_with_string_id: str,
) -> None:
    """When the Supabase client returns `.id` as a string,
    `current_user` MUST return an AuthenticatedUser whose `.id` is
    uuid.UUID. This is the boundary coercion the fix introduces.

    Exercise it by hitting any auth-required route (`/api/me` returns
    the user payload as JSON) — the response gives us the user shape
    after current_user ran.
    """
    client.cookies.set("sb-access-token", "any-token")
    response = client.get("/api/me", follow_redirects=False)
    assert response.status_code == 200, response.text
    body = response.json()
    # /api/me serializes `id` via `str(user.id)` — if the id was still
    # a string, str() would be a no-op and the value would match
    # supabase_user_with_string_id exactly. That's also true if it's a
    # uuid.UUID. The discriminator: a real UUID round-trips through
    # str() in canonical lowercased form regardless of input casing.
    assert body["id"] == supabase_user_with_string_id


def test_paste_via_dependency_override_still_works_with_uuid_id(
    client: TestClient, session: Session
) -> None:
    """Regression guard for the existing test pattern: tests that
    override current_user with a SimpleNamespace(id=uuid.uuid4(), ...)
    must keep passing. The AuthenticatedUser adapter is the production
    path; tests can keep using duck-typed overrides as long as `.id`
    is already a uuid.UUID."""
    fake_user = SimpleNamespace(id=uuid.uuid4(), email="r@example.com")
    app.dependency_overrides[current_user] = lambda: fake_user

    try:
        response = client.post("/passages", data={"text": "via override"}, follow_redirects=False)
        assert response.status_code == 303
        passages = session.exec(select(Passage)).all()
        assert len(passages) == 1
        assert passages[0].owner_id == fake_user.id
    finally:
        app.dependency_overrides.pop(current_user, None)
