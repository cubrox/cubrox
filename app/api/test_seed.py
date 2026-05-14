"""Test-only seed router for the WCAG harness (A11Y-2 #25).

Provides POST /test/seed-passage-and-login, which provisions a fresh
User + Passage (+ optional Preference row) and returns a signed
session cookie + the new passage id. Playwright specs hit this once
per test to set up an authenticated, parameterized reading surface
without needing email + magic-link plumbing.

## Two-layer guard

This router must never load in production:

1. **Module-level guard** (this file): the import itself raises
   `RuntimeError` unless `CUBROX_TEST_SEED_ENABLED=true` OR
   `ENVIRONMENT=test`. Belt-and-braces — even a stray `import` from
   anywhere in the codebase fails loudly.

2. **Registration-level guard** (app/main.py): the import + router
   registration is wrapped in `if os.environ.get(...) == "true": ...`.
   So unless the env var is explicitly set, the module is never
   imported in the first place.

The CI a11y job sets `CUBROX_TEST_SEED_ENABLED=true` on the FastAPI
process via `playwright.config.ts > webServer.env`. Production Cloud
Run revisions do not set this var; the seed router cannot be reached.
"""

import os
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlmodel import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.models.passage import Passage
from app.models.preference import Preference
from app.models.user import User
from app.services.identity.session import SESSION_COOKIE_NAME, sign_session

_SEED_ENABLED = os.environ.get("CUBROX_TEST_SEED_ENABLED") == "true"
_TEST_ENV = os.environ.get("ENVIRONMENT") == "test"
if not (_SEED_ENABLED or _TEST_ENV):
    raise RuntimeError(
        "app.api.test_seed loaded in non-test environment. "
        "Set CUBROX_TEST_SEED_ENABLED=true (test envs only) or "
        "ENVIRONMENT=test to enable."
    )


router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

Variant = Literal["default", "high-contrast", "large-text", "bionic"]

# A representative passage with multiple paragraphs so axe-core has a
# real surface to analyze — headings, paragraph spacing, line wrap, and
# color contrast over substantive content.
SEED_PASSAGE_TEXT = (
    "O Son of Spirit!\n\n"
    "My first counsel is this: Possess a pure, kindly and radiant heart, "
    "that thine may be a sovereignty ancient, imperishable and everlasting.\n\n"
    "O Son of Spirit!\n\n"
    "The best beloved of all things in My sight is Justice. Turn not away "
    "therefrom if thou desirest Me, and neglect it not that I may confide in thee."
)


# Per-variant overrides to the stored Preference values. `default` is
# empty (no row created — the reading view falls back to
# DEFAULT_PREFERENCES). The other three exercise one axis each so any
# a11y regression points clearly at which preference broke.
_PREFS_FOR_VARIANT: dict[str, dict[str, Any]] = {
    "default": {},
    "high-contrast": {"bg": "#1a1a1a", "fg": "#e8e8e8"},
    "large-text": {"size": "28px"},
    "bionic": {"bionic_enabled": True},
}


@router.post("/test/seed-passage-and-login")
def seed_passage_and_login(
    variant: Variant,
    session: SessionDep,
    settings: SettingsDep,
) -> JSONResponse:
    """Seed a fresh user + passage + (optional) preference; return the
    session cookie + passage id.

    Each invocation creates an independent user (UUID-suffixed email),
    so concurrent tests don't collide on the email unique constraint.
    The cookie is set with `secure=False` because the harness runs over
    http://localhost — production Cloud Run cookies remain secure-only.
    """
    user = User(email=f"a11y-{uuid.uuid4()}@example.test")
    session.add(user)
    session.commit()
    session.refresh(user)

    passage = Passage(
        user_id=user.id,
        # Placeholder hash — the read path doesn't validate it; only
        # the comprehension-cache uses text_hash, which the a11y tests
        # don't exercise (the questions panel makes a network call we
        # don't care about for visual a11y).
        text_hash=b"\x00" * 32,
        text=SEED_PASSAGE_TEXT,
        source_type="paste",
        source_filename=None,
    )
    session.add(passage)

    prefs_overrides = _PREFS_FOR_VARIANT[variant]
    if prefs_overrides:
        session.add(
            Preference(
                user_id=user.id,
                values=prefs_overrides,
                updated_at=datetime.now(UTC),
            )
        )

    session.commit()
    session.refresh(passage)

    response = JSONResponse({"passage_id": str(passage.id), "variant": variant})
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=sign_session(user_id=user.id, secret=settings.session_secret),
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        # Test harness runs over plain HTTP on localhost. Production
        # cookies stay `secure=True` via the normal /auth/verify path.
        secure=False,
        samesite="lax",
    )
    return response
