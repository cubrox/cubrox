"""Runtime configuration.

All env vars are read at runtime — FastAPI has no build-time env var baking
like Next.js, so this just works with `gcloud run deploy --set-env-vars`
or Cloud Run Secret Manager mounts.
"""

from functools import lru_cache
from typing import Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings loaded from environment variables."""

    database_url: str = "sqlite:///./dev.db"
    app_url: str = "http://localhost:8080"
    environment: str = "development"

    # Magic-link sign-in (ADR-002). RESEND_API_KEY is required in any
    # environment where /login is exercised; the Settings validator below
    # gates non-dev environments. The base URL and from-email default to
    # values safe for local dev so the test suite needs no env setup.
    resend_api_key: str = ""
    magic_link_base_url: str = "http://localhost:8080"
    magic_link_from_email: str = "onboarding@resend.dev"

    # Anthropic LLM (ADR-001). Used by app/services/comprehension/generator.py
    # to generate reading-comprehension questions. The route layer that
    # consumes this builds the client lazily so missing config doesn't
    # fail the app boot — just the /questions feature degrades.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5"

    # Session cookie signing (AUTH-2). 32+ random bytes, set per environment
    # via Secret Manager. The dev default is the literal string "dev-only"
    # so tests can run with no env setup; the validator below refuses this
    # default in non-dev environments.
    session_secret: str = "dev-only"
    session_ttl_days: int = 30
    session_cookie_secure: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def _force_psycopg3_driver(cls, v: str) -> str:
        # Neon emits postgresql:// URLs, which SQLAlchemy resolves to the
        # psycopg2 driver. We ship psycopg3 only, so rewrite the scheme.
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+psycopg://", 1)
        return v

    @model_validator(mode="after")
    def _refuse_sqlite_outside_dev(self) -> Self:
        # Defense-in-depth: the dev-default sqlite URL must never reach
        # any non-dev runtime (production, preview, staging). If
        # DATABASE_URL is missing or doesn't override the default, fail
        # at startup with a clear message rather than 500ing on the
        # first DB query with `no such table: todo`. Originally only
        # gated `production`; #78 generalized after a 2026-04-30 dry-run
        # showed previews silently fell through to SQLite when Neon was
        # unconfigured. See #63 / #71 / #78.
        if self.environment in ("development", "test"):
            return self
        if not self.database_url:
            raise ValueError(
                f"DATABASE_URL is empty in {self.environment}. "
                "Check that DATABASE_URL is set on the Cloud Run revision "
                "(production reads from PRODUCTION_DATABASE_URL secret; "
                "preview reads from the Neon branch action output)."
            )
        if self.database_url.startswith("sqlite"):
            raise ValueError(
                f"DATABASE_URL is SQLite in {self.environment}: {self.database_url!r}. "
                "Non-dev environments must use Postgres. Likely cause: the "
                "DATABASE_URL env var didn't override the dev default — for "
                "previews, NEON_API_KEY may be unconfigured so the Neon branch "
                "step was skipped."
            )
        if self.session_secret in ("", "dev-only"):
            raise ValueError(
                f"SESSION_SECRET is the dev default or empty in {self.environment}. "
                "Generate 32+ random bytes (e.g. `python -c 'import secrets; "
                "print(secrets.token_urlsafe(32))'`) and set as a Cloud Run env "
                "var (production reads from the SESSION_SECRET secret in Secret "
                "Manager). Without this, every session cookie is forgeable."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor.

    Uses lru_cache so settings are loaded exactly once per process.
    Tests can override this via dependency injection.
    """
    return Settings()
