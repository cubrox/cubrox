"""Shared pytest fixtures.

Uses an in-memory SQLite database per test so tests don't touch Neon or
pollute each other. The app's `get_session` dependency is overridden
to yield sessions bound to the test engine; the `current_user`
dependency is overridden by the `signed_in_user` fixture / `signed_in`
helper so tests don't have to construct real Supabase JWTs.

Two ways tests authenticate after SUPA-5:

  - `signed_in_user` fixture — gives you a default User and configures
    `current_user` to return them. Most tests just want one signed-in
    user.
  - `signed_in(session, email=…)` helper — for tests that need
    multiple users (e.g. two-user isolation tests). Each call creates
    a User and swaps `current_user`'s override.

The `supabase_mock` fixture exposes the MagicMock that stands in for
`supabase.create_client`, so auth-flow tests (POST /login, GET
/auth/callback) can configure the OTP / get_user return values.
"""

from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.db import get_session
from app.integrations.supabase import client as supabase_client_module
from app.main import app
from app.models.user import User
from app.services.identity.session import current_user, try_current_user


@pytest.fixture
def supabase_mock(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace supabase.create_client with a MagicMock and return it.

    Tests configure return values via the standard MagicMock surface:
        supabase_mock.auth.get_user.return_value = SimpleNamespace(
            user=SimpleNamespace(id="...", email="..."),
        )
    """
    fake = MagicMock()
    monkeypatch.setattr(supabase_client_module, "create_client", lambda *a, **k: fake)
    supabase_client_module.anon_client.cache_clear()
    supabase_client_module.service_client.cache_clear()
    return fake


@pytest.fixture(autouse=True)
def _autouse_supabase_stub(supabase_mock: MagicMock) -> None:  # noqa: ARG001
    """Force every test to get the supabase_mock fixture so anon_client()
    never makes a real network call. Tests that need to introspect the
    mock can take `supabase_mock` directly; the rest inherit the stub.
    """


def make_user(session: Session, email: str = "other@example.com") -> User:
    """Create a User without configuring any dependency override.

    Use this when a test needs a *non-current* user — typically for
    ownership-isolation tests where the current user is signed_in()
    but another user owns the resource under test.
    """
    user = User(email=email)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def signed_in(session: Session, email: str = "reader@example.com") -> User:
    """Create a User and configure `current_user` to return them.

    Use this when you need to seed a specific user (custom email) or
    multiple users in one test (call it twice; the second call swaps
    the override). For the single-default-user case, prefer the
    `signed_in_user` fixture.
    """
    user = User(email=email)
    session.add(user)
    session.commit()
    session.refresh(user)
    # Override BOTH dependencies: try_current_user calls current_user
    # as a plain function (not via Depends), so overriding only
    # current_user wouldn't intercept the soft-auth path used by
    # routes that render differently for anonymous visitors (the
    # landing page is the canonical example).
    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[try_current_user] = lambda: user
    return user


@pytest.fixture
def signed_in_user(session: Session) -> User:
    """Default signed-in user fixture: one User, current_user overridden.

    Cleanup of `dependency_overrides` is handled by the `client`
    fixture's `app.dependency_overrides.clear()` after yield.
    """
    return signed_in(session)


@pytest.fixture(name="session")
def session_fixture() -> Generator[Session, None, None]:
    """Fresh in-memory SQLite database for each test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session) -> Generator[TestClient, None, None]:
    """TestClient with get_session overridden to use the test session."""

    def get_session_override() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_session] = get_session_override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
