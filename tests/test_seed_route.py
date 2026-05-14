"""Route-level tests for the test-only seed endpoint (A11Y-2 #25).

These tests exercise the actual POST /test/seed-passage-and-login
route. The conftest doesn't normally register this router (the
conditional in `app/main.py` only fires when `CUBROX_TEST_SEED_ENABLED=true`
at app boot), so we mount the router onto the existing test app via
FastAPI's `include_router` for the duration of each test.

This is functional coverage of the seed handler — the variant
matrix, the cookie shape, the row counts that the Playwright suite
implicitly relies on. Pytest catches regressions before Playwright
has to.
"""

import importlib
import sys
import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.main import app
from app.models.passage import Passage
from app.models.preference import Preference
from app.models.user import User


@pytest.fixture
def seed_client(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> Generator[TestClient, None, None]:
    """TestClient with the seed router temporarily mounted on the app.

    The guard inside app/api/test_seed.py needs ENVIRONMENT=test (the
    pytest default for our conftest is `development`, so set it
    explicitly). After the test runs, the router is removed from the
    app so other tests don't see it.
    """
    monkeypatch.setenv("ENVIRONMENT", "test")
    sys.modules.pop("app.api.test_seed", None)
    test_seed = importlib.import_module("app.api.test_seed")

    app.include_router(test_seed.router)
    try:
        yield client
    finally:
        # Remove the seed routes so subsequent tests don't see them.
        # FastAPI doesn't expose a public "remove_router"; pop the
        # routes we just added by path-prefix match.
        app.router.routes = [
            r
            for r in app.router.routes
            if not (
                hasattr(r, "path") and r.path == "/test/seed-passage-and-login"  # type: ignore[attr-defined]
            )
        ]


def test_seed_default_variant_creates_user_passage_no_preference(
    seed_client: TestClient, session: Session
) -> None:
    """`default` is the no-Preference path — the reading view falls back
    to DEFAULT_PREFERENCES without a row."""
    response = seed_client.post(
        "/test/seed-passage-and-login?variant=default", follow_redirects=False
    )
    assert response.status_code == 200
    body = response.json()
    assert body["variant"] == "default"
    # passage_id is a parseable UUID.
    uuid.UUID(body["passage_id"])

    # Exactly one user + one passage + zero preferences.
    assert len(session.exec(select(User)).all()) == 1
    assert len(session.exec(select(Passage)).all()) == 1
    assert len(session.exec(select(Preference)).all()) == 0

    # Cookie was set so subsequent /read/{id} requests are authenticated.
    assert "session" in response.cookies


def test_seed_high_contrast_variant_writes_dark_bg_fg(
    seed_client: TestClient, session: Session
) -> None:
    response = seed_client.post(
        "/test/seed-passage-and-login?variant=high-contrast", follow_redirects=False
    )
    assert response.status_code == 200

    prefs = session.exec(select(Preference)).all()
    assert len(prefs) == 1
    assert prefs[0].values == {"bg": "#1a1a1a", "fg": "#e8e8e8"}


def test_seed_large_text_variant_writes_28px(seed_client: TestClient, session: Session) -> None:
    response = seed_client.post(
        "/test/seed-passage-and-login?variant=large-text", follow_redirects=False
    )
    assert response.status_code == 200

    prefs = session.exec(select(Preference)).all()
    assert len(prefs) == 1
    assert prefs[0].values == {"size": "28px"}


def test_seed_bionic_variant_writes_bionic_enabled_true(
    seed_client: TestClient, session: Session
) -> None:
    response = seed_client.post(
        "/test/seed-passage-and-login?variant=bionic", follow_redirects=False
    )
    assert response.status_code == 200

    prefs = session.exec(select(Preference)).all()
    assert len(prefs) == 1
    assert prefs[0].values == {"bionic_enabled": True}


def test_seed_unknown_variant_returns_422(seed_client: TestClient) -> None:
    """The route uses a typing.Literal for the variant param. FastAPI
    rejects unknown values with 422 automatically."""
    response = seed_client.post(
        "/test/seed-passage-and-login?variant=does-not-exist",
        follow_redirects=False,
    )
    assert response.status_code == 422


def test_seed_creates_independent_users_across_calls(
    seed_client: TestClient, session: Session
) -> None:
    """Each call creates a unique user (UUID-suffixed email) so
    Playwright tests can run in parallel without colliding on the
    email unique constraint."""
    seed_client.post("/test/seed-passage-and-login?variant=default")
    seed_client.post("/test/seed-passage-and-login?variant=default")

    users = session.exec(select(User)).all()
    assert len(users) == 2
    assert users[0].email != users[1].email
    assert all(u.email.startswith("a11y-") for u in users)
