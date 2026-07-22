"""Shared pytest fixtures.

Uses an in-memory SQLite database per test so tests don't touch the
real Supabase Postgres. The app's `get_session` dependency is
overridden to yield sessions bound to the test engine; the
`current_user` / `try_current_user` dependencies are overridden by
the `signed_in_user` fixture / `signed_in` helper so tests don't have
to construct real Supabase JWTs.

Two ways tests authenticate after SUPA-2c:

  - `signed_in_user` fixture — gives you a default user (SimpleNamespace
    with `.id` and `.email`) and configures `current_user` to return them.
  - `signed_in(session, email=…)` helper — for tests that need multiple
    users (two-user isolation tests). Each call creates a fresh user
    and swaps `current_user`'s override.

`make_user(session, email=…)` is the helper for non-current users
(cross-user isolation tests). Returns a SimpleNamespace; does not
touch dependency overrides.

The `supabase_mock` fixture exposes the MagicMock that stands in for
`supabase.create_client`, so auth-flow tests (POST /login, GET
/auth/callback) can configure the OTP / get_user return values.

The user type returned by these helpers matches the shape of the
Supabase `gotrue.types.User`: it has `.id` (UUID) and `.email` (str).
That's all the routes touch.
"""

import os
import uuid
from collections.abc import Generator
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

# OBS-1 (#167): guarantee the test session never initialises Sentry.
#
# `app/main.py` calls `sentry_sdk.init()` at import time when SENTRY_DSN is
# set. `from app.main import app` below runs at COLLECTION time, so on a
# machine with a real SENTRY_DSN exported (or present in `.env` — Settings
# sets `env_file=".env"`) the whole test run would execute against a LIVE
# Sentry client, shipping test failures to the real project as fake
# production errors. Blanking the var here, before that import, is what
# enforces the ticket's "no sentry_sdk.init() in test runs" guardrail.
#
# MUST stay above the `app.*` imports — moving it below re-opens the hole.
os.environ["SENTRY_DSN"] = ""

from app.db import get_session  # noqa: E402
from app.integrations.supabase import client as supabase_client_module  # noqa: E402
from app.integrations.supabase.auth import current_user, try_current_user  # noqa: E402
from app.main import app  # noqa: E402


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


def make_user(session: Session, email: str = "other@example.com") -> SimpleNamespace:  # noqa: ARG001
    """Create a stand-in user object for tests.

    The `session` parameter is unused after SUPA-2c (there's no User
    table anymore) but the signature is preserved so the migration
    didn't have to rewrite every call site. Returns a SimpleNamespace
    whose shape matches Supabase's `gotrue.types.User` for the
    attributes routes access: `.id` (UUID) and `.email` (str).
    """
    return SimpleNamespace(id=uuid.uuid4(), email=email)


def signed_in(session: Session, email: str = "reader@example.com") -> SimpleNamespace:
    """Create a stand-in user and configure `current_user` to return them.

    Use this when you need a specific user (custom email) or multiple
    users in one test (call it twice; the second call swaps the
    override). For the single-default-user case, prefer the
    `signed_in_user` fixture.
    """
    user = make_user(session, email=email)
    # Override BOTH dependencies: try_current_user calls current_user
    # as a plain function (not via Depends), so overriding only
    # current_user wouldn't intercept the soft-auth path used by
    # routes that render differently for anonymous visitors.
    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[try_current_user] = lambda: user
    return user


@pytest.fixture
def signed_in_user(session: Session) -> SimpleNamespace:
    """Default signed-in user fixture: one user, current_user overridden.

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
