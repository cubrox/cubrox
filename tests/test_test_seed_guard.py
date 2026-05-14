"""Guard-rail test for the test-only seed router (A11Y-2 #25).

`app/api/test_seed.py` must NEVER load in a non-test environment.
The module's import-time guard raises RuntimeError unless one of:
  - CUBROX_TEST_SEED_ENABLED=true (set explicitly by the a11y harness)
  - ENVIRONMENT=test (set by the conftest in unit-test runs)

This test simulates a production-like env (neither var set to a test
value) and confirms the import fails.
"""

import importlib
import sys

import pytest


def test_test_seed_refuses_to_load_in_non_test_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Belt-and-braces: even if someone bypasses the conditional import
    in app/main.py and tries to import the module directly, the
    module-level guard fires."""
    monkeypatch.delenv("CUBROX_TEST_SEED_ENABLED", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")

    # Drop any previously cached import so we re-execute the module body
    # and re-run the guard.
    sys.modules.pop("app.api.test_seed", None)

    with pytest.raises(RuntimeError, match="non-test environment"):
        importlib.import_module("app.api.test_seed")


def test_test_seed_loads_when_explicitly_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sanity check: with the harness env var set, the import succeeds
    and the router object is exposed. Mirrors what app/main.py does at
    boot when CUBROX_TEST_SEED_ENABLED=true."""
    monkeypatch.setenv("CUBROX_TEST_SEED_ENABLED", "true")
    monkeypatch.setenv("ENVIRONMENT", "production")  # still allowed by the guard
    sys.modules.pop("app.api.test_seed", None)

    module = importlib.import_module("app.api.test_seed")
    assert hasattr(module, "router")


def test_test_seed_loads_in_test_environment_without_enable_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pytest conftest may not set CUBROX_TEST_SEED_ENABLED, but
    setting ENVIRONMENT=test is sufficient. This is the "running under
    pytest with explicit env=test" path."""
    monkeypatch.delenv("CUBROX_TEST_SEED_ENABLED", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "test")
    sys.modules.pop("app.api.test_seed", None)

    module = importlib.import_module("app.api.test_seed")
    assert hasattr(module, "router")
