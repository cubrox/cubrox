"""Route-level tests for the test-only seed endpoint (A11Y-2 #25, restored in #97).

These tests exercise the actual POST /test/seed-passage-and-login
route. The conftest doesn't normally register this router (the
conditional in `app/main.py` only fires when `MASTERKEY_TEST_SEED_ENABLED=true`
at app boot), so we mount the router onto the existing test app via
FastAPI's `include_router` for the duration of each test.

This is functional coverage of the seed handler — the variant matrix,
the cookie shape, the row counts that the Playwright suite implicitly
relies on. Pytest catches regressions before Playwright has to. The
Supabase admin/sign-in calls are mocked by the conftest's
`supabase_mock` fixture — see conftest.py for the shape.
"""

import importlib
import sys
import uuid
from collections.abc import Generator
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.main import app
from app.models.passage import Passage
from app.models.preference import Preference


def _wire_supabase_for_seed(supabase_mock: MagicMock, user_id: str | None = None) -> str:
    """Wire the supabase_mock so admin.create_user no-ops and
    sign_in_with_password returns a session for a known user UUID.

    Returns the UUID string so callers can assert that ownership rows
    on Passage / Preference match.
    """
    uid = user_id or str(uuid.uuid4())
    supabase_mock.auth.sign_in_with_password.return_value = SimpleNamespace(
        user=SimpleNamespace(id=uid, email="ignored-by-route@example.test"),
        session=SimpleNamespace(access_token=f"fake-jwt-{uid[:8]}"),
    )
    return uid


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


def test_seed_default_variant_creates_passage_no_preference(
    seed_client: TestClient, session: Session, supabase_mock: MagicMock
) -> None:
    """`default` is the no-Preference path — the reading view falls back
    to DEFAULT_PREFERENCES without a row."""
    _wire_supabase_for_seed(supabase_mock)

    response = seed_client.post(
        "/test/seed-passage-and-login?variant=default", follow_redirects=False
    )
    assert response.status_code == 200
    body = response.json()
    assert body["variant"] == "default"
    # passage_id is a parseable UUID.
    uuid.UUID(body["passage_id"])

    # Exactly one passage, zero preferences. (User identity now lives
    # in Supabase, not a local table, so we don't count User rows.)
    assert len(session.exec(select(Passage)).all()) == 1
    assert len(session.exec(select(Preference)).all()) == 0

    # Cookie is the Supabase access-token cookie, carrying the fake JWT
    # the mock returned. Subsequent /read/{id} requests will hit the
    # `current_user` dependency, which is independently mocked.
    assert "sb-access-token" in response.cookies


def test_seed_creates_supabase_user_via_admin_api(
    seed_client: TestClient, supabase_mock: MagicMock
) -> None:
    """The route MUST go through service_client().auth.admin.create_user
    so the user has `email_confirm=True` and no email round-trip
    happens. Lock down the API call shape so a future refactor
    (e.g. accidentally switching to sign_up) breaks loudly."""
    _wire_supabase_for_seed(supabase_mock)

    response = seed_client.post("/test/seed-passage-and-login?variant=default")
    assert response.status_code == 200

    create_user_call = supabase_mock.auth.admin.create_user.call_args
    assert create_user_call is not None, "admin.create_user was never invoked"
    payload = create_user_call.args[0]
    assert payload["email"].startswith("a11y-")
    assert payload["email"].endswith("@example.test")
    assert payload["email_confirm"] is True
    # A random password is generated and passed to Supabase, then
    # immediately exchanged via sign_in_with_password. We don't pin
    # the value, just that one was set.
    assert payload["password"]


def test_seed_uses_password_grant_for_session_jwt(
    seed_client: TestClient, supabase_mock: MagicMock
) -> None:
    """After admin.create_user, the route must call
    anon_client().auth.sign_in_with_password to get a real JWT. The
    alternative (generate_link) returns a URL that still requires a
    callback exchange, so the password-grant path is the right one."""
    _wire_supabase_for_seed(supabase_mock)

    seed_client.post("/test/seed-passage-and-login?variant=default")

    sign_in_call = supabase_mock.auth.sign_in_with_password.call_args
    assert sign_in_call is not None, "sign_in_with_password was never invoked"
    payload = sign_in_call.args[0]
    assert payload["email"].startswith("a11y-")
    assert payload["password"]


def test_seed_high_contrast_variant_writes_dark_bg_fg(
    seed_client: TestClient, session: Session, supabase_mock: MagicMock
) -> None:
    _wire_supabase_for_seed(supabase_mock)
    response = seed_client.post(
        "/test/seed-passage-and-login?variant=high-contrast", follow_redirects=False
    )
    assert response.status_code == 200

    prefs = session.exec(select(Preference)).all()
    assert len(prefs) == 1
    assert prefs[0].values == {"bg": "#1a1a1a", "fg": "#e8e8e8"}


def test_seed_large_text_variant_writes_28px(
    seed_client: TestClient, session: Session, supabase_mock: MagicMock
) -> None:
    _wire_supabase_for_seed(supabase_mock)
    response = seed_client.post(
        "/test/seed-passage-and-login?variant=large-text", follow_redirects=False
    )
    assert response.status_code == 200

    prefs = session.exec(select(Preference)).all()
    assert len(prefs) == 1
    assert prefs[0].values == {"size": "28px"}


def test_seed_bionic_variant_writes_bionic_enabled_true(
    seed_client: TestClient, session: Session, supabase_mock: MagicMock
) -> None:
    _wire_supabase_for_seed(supabase_mock)
    response = seed_client.post(
        "/test/seed-passage-and-login?variant=bionic", follow_redirects=False
    )
    assert response.status_code == 200

    prefs = session.exec(select(Preference)).all()
    assert len(prefs) == 1
    assert prefs[0].values == {"bionic_enabled": True}


def test_seed_unknown_variant_returns_422(
    seed_client: TestClient, supabase_mock: MagicMock
) -> None:
    """The route uses a typing.Literal for the variant param. FastAPI
    rejects unknown values with 422 automatically — and short-circuits
    before any Supabase call."""
    _wire_supabase_for_seed(supabase_mock)
    response = seed_client.post(
        "/test/seed-passage-and-login?variant=does-not-exist",
        follow_redirects=False,
    )
    assert response.status_code == 422
    # Confirm we didn't waste a Supabase call on a bad variant.
    supabase_mock.auth.admin.create_user.assert_not_called()


def test_seed_creates_independent_users_across_calls(
    seed_client: TestClient, session: Session, supabase_mock: MagicMock
) -> None:
    """Each call creates a unique user (UUID-suffixed email) so
    Playwright tests can run in parallel without colliding on Supabase
    Auth's email unique constraint. We also verify the two created
    passages are owned by distinct UUIDs (since each call mints a
    different fake user in the mock)."""
    uid_1 = _wire_supabase_for_seed(supabase_mock)
    seed_client.post("/test/seed-passage-and-login?variant=default")

    uid_2 = _wire_supabase_for_seed(supabase_mock)
    seed_client.post("/test/seed-passage-and-login?variant=default")

    assert uid_1 != uid_2

    # Two admin.create_user calls with two distinct emails.
    calls = supabase_mock.auth.admin.create_user.call_args_list
    assert len(calls) == 2
    emails = [c.args[0]["email"] for c in calls]
    assert emails[0] != emails[1]
    assert all(e.startswith("a11y-") for e in emails)

    # Two passages, each owned by the respective Supabase user UUID.
    passages = session.exec(select(Passage)).all()
    assert len(passages) == 2
    owner_ids = {str(p.owner_id) for p in passages}
    assert owner_ids == {uid_1, uid_2}


def test_seed_500s_when_supabase_sign_in_returns_no_session(
    seed_client: TestClient, supabase_mock: MagicMock
) -> None:
    """Defensive guard: if Supabase's sign_in_with_password returns
    `None` or a response without a session, we 500 instead of trying
    to set a cookie with `None` as its value."""
    supabase_mock.auth.sign_in_with_password.return_value = None
    response = seed_client.post(
        "/test/seed-passage-and-login?variant=default", follow_redirects=False
    )
    assert response.status_code == 500


def test_seed_with_questions_seeds_cache_the_route_will_hit(
    seed_client: TestClient, session: Session, supabase_mock: MagicMock
) -> None:
    """A11Y-5 (#126): `with_questions=true` seeds the comprehension cache
    with the EXACT key the questions route looks up. Proven end-to-end:
    after the seed, `generate_questions` for the seed passage returns the
    seeded set WITHOUT calling Anthropic — i.e. a cache hit, which is what
    lets the a11y harness render the real answer UI without an API key."""
    import app.api.test_seed as test_seed
    from app.config import get_settings
    from app.services.comprehension.generator import generate_questions

    _wire_supabase_for_seed(supabase_mock)
    response = seed_client.post("/test/seed-passage-and-login?variant=default&with_questions=true")
    assert response.status_code == 200

    client = MagicMock()
    result = generate_questions(
        passage_text=test_seed.SEED_PASSAGE_TEXT,
        question_type="recall",
        client=client,
        model_id=get_settings().anthropic_model,
        session=session,
    )
    assert client.messages.create.call_count == 0  # cache hit, no LLM call
    assert result == test_seed.SEED_QUESTIONS


def test_seed_without_questions_leaves_comprehension_cache_empty(
    seed_client: TestClient, session: Session, supabase_mock: MagicMock
) -> None:
    """The default path must NOT seed the cache — existing reading-surface
    a11y tests keep rendering the panel's "unavailable" state, unchanged."""
    import hashlib

    import app.api.test_seed as test_seed
    from app.config import get_settings
    from app.services.comprehension import cache
    from app.services.comprehension.prompts import PROMPT_VERSION

    _wire_supabase_for_seed(supabase_mock)
    seed_client.post("/test/seed-passage-and-login?variant=default")

    cached = cache.get_cached(
        passage_hash=hashlib.sha256(test_seed.SEED_PASSAGE_TEXT.encode("utf-8")).digest(),
        question_type="recall",
        model_id=get_settings().anthropic_model,
        prompt_version=PROMPT_VERSION,
        session=session,
    )
    assert cached is None
