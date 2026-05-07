"""Tests for app.config.Settings.

Pins two contracts:
  1. database_url is normalized to use the psycopg3 driver scheme.
     SQLAlchemy resolves the bare `postgresql://` scheme to psycopg2
     (not installed in this project), so without normalization every
     Neon-backed deploy would ImportError on first DB use.
  2. In production, an empty or sqlite-shaped DATABASE_URL fails fast
     at Settings construction (model validator) — turns the silent
     "first request 500s with no such table: todo" failure mode into
     a loud ValueError at startup. See #63.
"""

import pytest


def _make_settings(database_url: str | None = None):
    # Import inside the helper so each call sees the patched env. The
    # @lru_cache on get_settings is process-level; we instantiate
    # Settings() directly to bypass it.
    from app.config import Settings

    if database_url is None:
        return Settings()
    return Settings(database_url=database_url)


@pytest.mark.parametrize(
    "input_url,expected",
    [
        # The live-bug case: Neon emits postgresql://, must become postgresql+psycopg://
        (
            "postgresql://u:p@h/db",
            "postgresql+psycopg://u:p@h/db",
        ),
        # Already-normalized URLs pass through unchanged
        (
            "postgresql+psycopg://u:p@h/db",
            "postgresql+psycopg://u:p@h/db",
        ),
        # Non-postgres schemes are untouched
        ("sqlite:///./dev.db", "sqlite:///./dev.db"),
        ("sqlite://", "sqlite://"),
        # Only the scheme is rewritten; query string + path preserved
        (
            "postgresql://user:pa%40ss@host:5432/db?sslmode=require",
            "postgresql+psycopg://user:pa%40ss@host:5432/db?sslmode=require",
        ),
    ],
)
def test_database_url_scheme_normalization(input_url: str, expected: str) -> None:
    assert _make_settings(input_url).database_url == expected


def test_production_empty_database_url_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    # Reading the empty-string case requires going through env vars: a
    # bare Settings(database_url="") would still trigger this, but the
    # realistic failure mode is the secret mount producing an empty env
    # var, so we exercise that path explicitly.
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "")
    from app.config import Settings

    with pytest.raises(ValueError, match="DATABASE_URL is empty in production"):
        Settings()


def test_production_sqlite_database_url_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./dev.db")
    from app.config import Settings

    with pytest.raises(ValueError, match="DATABASE_URL is SQLite in production"):
        Settings()


def test_development_empty_database_url_uses_sqlite_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Development is the local-dev path: missing DATABASE_URL must NOT
    # raise — pydantic's default ("sqlite:///./dev.db") applies and the
    # app boots against the local SQLite file.
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from app.config import Settings

    settings = Settings()
    assert settings.database_url == "sqlite:///./dev.db"


def test_production_postgres_url_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    # The happy path: real Neon URL in production. Field validator
    # normalizes it to psycopg3; model validator sees a non-sqlite,
    # non-empty URL and returns clean.
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h.neon.tech/db")
    monkeypatch.setenv("SESSION_SECRET", "test-only-not-the-real-secret")
    from app.config import Settings

    settings = Settings()
    assert settings.database_url == "postgresql+psycopg://u:p@h.neon.tech/db"


def test_preview_sqlite_database_url_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    # The 2026-04-30 dry-run failure mode: Neon unconfigured, preview
    # falls through to the dev-default `sqlite:///./dev.db`, app boots
    # and 500s on the first DB query. The validator must catch this
    # before the container starts, with the same loudness as production.
    monkeypatch.setenv("ENVIRONMENT", "preview")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./dev.db")
    from app.config import Settings

    with pytest.raises(ValueError, match="DATABASE_URL is SQLite in preview"):
        Settings()


def test_preview_postgres_url_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    # Happy path for preview: Neon branch URL flows through field
    # validator psycopg3 normalization and is accepted by the model
    # validator. Confirms #78 didn't accidentally break the preview
    # happy path while widening the gate.
    monkeypatch.setenv("ENVIRONMENT", "preview")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h.neon.tech/preview-pr-1")
    monkeypatch.setenv("SESSION_SECRET", "test-only-not-the-real-secret")
    from app.config import Settings

    settings = Settings()
    assert settings.database_url == "postgresql+psycopg://u:p@h.neon.tech/preview-pr-1"


def test_unfamiliar_environment_treated_as_non_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    # Future-proofing: any environment name that isn't "development" or
    # "test" is treated as a non-dev runtime. A staging deploy with
    # ENVIRONMENT=staging gets the same SQLite refusal as production.
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    from app.config import Settings

    with pytest.raises(ValueError, match="DATABASE_URL is SQLite in staging"):
        Settings()


def test_test_environment_allows_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    # The test fixtures explicitly use sqlite:// (in-memory) — so
    # ENVIRONMENT=test must be in the allow list alongside development.
    # Without this, every pytest run that sets ENVIRONMENT=test would
    # fail at Settings() construction.
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    from app.config import Settings

    settings = Settings()
    assert settings.database_url == "sqlite://"
