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

    # Anthropic LLM (ADR-001). Used by app/services/comprehension/generator.py
    # to generate reading-comprehension questions. The route layer that
    # consumes this builds the client lazily so missing config doesn't
    # fail the app boot — just the /questions feature degrades.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5"

    # Gates the `Secure` flag on the `sb-access-token` cookie that
    # `/auth/callback` sets. True in production / preview; tests and
    # local dev override to False via env.
    session_cookie_secure: bool = True

    # Supabase (SUPA-1/2/3). Required in non-dev environments so the
    # auth flow + future RLS-aware queries work. Empty defaults so the
    # test suite can run without env setup (the legacy auth path
    # services every test).
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def _force_psycopg3_driver(cls, v: str) -> str:
        # Supabase emits postgresql:// URLs, which SQLAlchemy resolves to
        # the psycopg2 driver. We ship psycopg3 only, so rewrite the scheme.
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
        # showed previews silently fell through to SQLite when the preview
        # DB was unconfigured. See #63 / #71 / #78.
        if self.environment in ("development", "test"):
            return self
        if not self.database_url:
            raise ValueError(
                f"DATABASE_URL is empty in {self.environment}. "
                "Check that DATABASE_URL is set on the Cloud Run revision "
                "(production reads from the PRODUCTION_DATABASE_URL secret; "
                "preview reads DATABASE_URL set on the revision)."
            )
        if self.database_url.startswith("sqlite"):
            raise ValueError(
                f"DATABASE_URL is SQLite in {self.environment}: {self.database_url!r}. "
                "Non-dev environments must use Postgres. Likely cause: the "
                "DATABASE_URL env var didn't override the dev default — the "
                "deploy may not have set DATABASE_URL on the preview revision."
            )
        # SUPA-3: production must have Supabase credentials wired or
        # the new auth flow can't issue magic links / validate JWTs.
        missing_sb = [
            name
            for name, value in (
                ("SUPABASE_URL", self.supabase_url),
                ("SUPABASE_ANON_KEY", self.supabase_anon_key),
                ("SUPABASE_SERVICE_KEY", self.supabase_service_key),
            )
            if not value
        ]
        if missing_sb:
            raise ValueError(
                f"{', '.join(missing_sb)} missing in {self.environment}. "
                "Set on Cloud Run via Secret Manager mounts "
                "(supabase-url, supabase-anon-key, supabase-service-key)."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor.

    Uses lru_cache so settings are loaded exactly once per process.
    Tests can override this via dependency injection.
    """
    return Settings()
