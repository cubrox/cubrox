"""Tests for the Sentry initialisation guard (OBS-1 #167).

Covers the Definition of Done from issue #167:
  - `SENTRY_DSN` unset -> `sentry_sdk.init()` is NOT called; the app
    imports and serves requests exactly as before
  - `SENTRY_DSN` set -> init IS called, with the configured environment
    and WITHOUT performance tracing
  - No route/service/model file imports sentry_sdk (the integrations
    capture unhandled exceptions via middleware; manual instrumentation
    would be redundant)

The init runs at module import time in app/main.py, so these tests
reload the module under a patched environment rather than calling a
function. `get_settings` is lru_cached, so its cache is cleared too —
otherwise the reload would reuse settings built from the real env.
"""

import importlib
import re
from pathlib import Path
from unittest.mock import patch

import pytest
import sentry_sdk
from fastapi.testclient import TestClient

import app.main
from app.config import get_settings


@pytest.fixture(autouse=True)
def _restore_main_module():
    """Reload app.main after each test so the patched-import state
    doesn't leak into the rest of the suite.

    The teardown reload MUST run with `sentry_sdk.init` patched AND
    `SENTRY_DSN` blanked. Without both, it re-executes app.main's init
    branch against the REAL environment (and `.env`, since Settings sets
    `env_file=".env"`): a developer with a real `SENTRY_DSN` exported
    would be left with a LIVE Sentry client active for every test module
    that collects after this one, shipping their test failures to the
    real Sentry project as fake production errors. That violates the
    ticket's "no `sentry_sdk.init()` in test runs" guardrail, and it is
    invisible in CI because CI has no DSN. Caught in review of PR #283.
    """
    yield
    get_settings.cache_clear()
    with patch.dict("os.environ", {"SENTRY_DSN": ""}, clear=False):
        with patch("sentry_sdk.init"):
            importlib.reload(app.main)
    # Self-guard: if the patching above is ever removed, fail loudly here
    # rather than silently leaking a live client into the rest of the run.
    assert not sentry_sdk.get_client().is_active(), (
        "teardown left a live Sentry client active — see this fixture's docstring"
    )


def _reload_main_with_env(env: dict[str, str]):
    """Reload app.main with a patched environment, returning the mock
    that stands in for sentry_sdk.init during the reload."""
    get_settings.cache_clear()
    with patch.dict("os.environ", env, clear=False):
        with patch("sentry_sdk.init") as mock_init:
            importlib.reload(app.main)
            return mock_init


def test_sentry_not_initialised_when_dsn_absent() -> None:
    """The default state for local dev, CI, and tests: no DSN, no init.
    The app must behave identically to before this ticket."""
    mock_init = _reload_main_with_env({"SENTRY_DSN": ""})
    mock_init.assert_not_called()


def test_app_serves_requests_when_dsn_absent() -> None:
    """Guardrail: the app MUST start and serve normally with no DSN."""
    mock_init = _reload_main_with_env({"SENTRY_DSN": ""})
    mock_init.assert_not_called()

    with TestClient(app.main.app) as client:
        assert client.get("/api/health").status_code == 200


def test_sentry_initialised_when_dsn_present() -> None:
    """With a DSN set, init is called with that DSN and the configured
    environment.

    Note `ENVIRONMENT=test` rather than `production`: Settings has a
    defense-in-depth validator (`_refuse_sqlite_outside_dev`) that
    rejects the default SQLite DATABASE_URL outside dev/test, so
    claiming production here would fail on config, not on Sentry.
    """
    mock_init = _reload_main_with_env(
        {"SENTRY_DSN": "https://test@o0.ingest.sentry.io/0", "ENVIRONMENT": "test"}
    )

    mock_init.assert_called_once()
    kwargs = mock_init.call_args.kwargs
    assert kwargs["dsn"] == "https://test@o0.ingest.sentry.io/0"
    assert kwargs["environment"] == "test"


def test_sentry_init_does_not_enable_performance_tracing() -> None:
    """Guardrail: error capture only. `traces_sample_rate` must not be
    set in this ticket — tracing is a separate tuning/cost decision."""
    mock_init = _reload_main_with_env({"SENTRY_DSN": "https://test@o0.ingest.sentry.io/0"})

    kwargs = mock_init.call_args.kwargs
    assert "traces_sample_rate" not in kwargs
    assert "profiles_sample_rate" not in kwargs


def test_no_sentry_imports_in_routes_services_or_models() -> None:
    """Guardrail: the SDK's integrations capture unhandled exceptions
    automatically. A stray `import sentry_sdk` in a route/service/model
    means someone added manual instrumentation this ticket forbids.

    app/main.py is the ONE allowed location.
    """
    app_dir = Path(__file__).parent.parent / "app"
    # Match real import statements only — a prose mention of
    # `sentry_sdk.init()` in a comment (app/config.py has one) is not an
    # import and must not trip this guard.
    import_re = re.compile(r"^\s*(?:import\s+sentry_sdk|from\s+sentry_sdk)", re.MULTILINE)
    offenders = [
        path.relative_to(app_dir.parent).as_posix()
        for path in app_dir.rglob("*.py")
        if path.name != "main.py" and import_re.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"sentry_sdk imported outside app/main.py: {offenders}"
