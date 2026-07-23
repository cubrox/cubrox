"""Test-only seed router for the WCAG harness (A11Y-2 #25, restored for SUPA-2c follow-up #97).

Provides POST /test/seed-passage-and-login: provisions a fresh Supabase
Auth user + Passage row (+ optional Preference row) and returns the
Supabase session JWT as the `sb-access-token` cookie + the new passage
id. Playwright hits this once per test to set up an authenticated,
parameterized reading surface without going through the magic-link
email flow.

## Difference from the pre-SUPA-2c version

Identity now lives in Supabase `auth.users`, not a local `User` SQLModel
(deleted in SUPA-2c #91). To mint a session JWT we:

  1. `service_client().auth.admin.create_user(...)` — privileged admin
     call that creates a confirmed user without an email round-trip.
  2. `anon_client().auth.sign_in_with_password(...)` — exchange the
     known password for an access token. We do this instead of
     `admin.generate_link` because the password-grant path returns a
     ready-to-use JWT directly; `generate_link` returns a URL that
     still requires the hash-fragment callback dance to exchange.

The Passage and Preference rows still go in our local DB and reference
the Supabase user UUID via `owner_id` (renamed from `user_id` in
SUPA-2c).

## Two-layer guard

This router must never load in production:

1. **Module-level guard** (this file): the import itself raises
   `RuntimeError` unless `MASTERKEY_TEST_SEED_ENABLED=true` OR
   `ENVIRONMENT=test`. Belt-and-braces — even a stray `import` from
   anywhere in the codebase fails loudly.

2. **Registration-level guard** (app/main.py): the import + router
   registration is wrapped in `if os.environ.get(...) == "true": ...`.
   So unless the env var is explicitly set, the module is never
   imported in the first place.

The CI a11y job sets `MASTERKEY_TEST_SEED_ENABLED=true` on the FastAPI
process via `playwright.config.ts > webServer.env`. Production Cloud
Run revisions do not set this var; the seed router cannot be reached.
"""

import hashlib
import os
import secrets
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlmodel import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.integrations.supabase.auth import SUPABASE_COOKIE_NAME
from app.integrations.supabase.client import anon_client, service_client
from app.models.passage import Passage
from app.models.preference import Preference
from app.services.comprehension import cache as comprehension_cache
from app.services.comprehension.prompts import PROMPT_VERSION

_SEED_ENABLED = os.environ.get("MASTERKEY_TEST_SEED_ENABLED") == "true"
_TEST_ENV = os.environ.get("ENVIRONMENT") == "test"
if not (_SEED_ENABLED or _TEST_ENV):
    raise RuntimeError(
        "app.api.test_seed loaded in non-test environment. "
        "Set MASTERKEY_TEST_SEED_ENABLED=true (test envs only) or "
        "ENVIRONMENT=test to enable."
    )


router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

Variant = Literal["default", "high-contrast", "large-text", "bionic", "focus-mode"]

# Representative passage with multiple paragraphs so axe-core has a
# real surface to analyze — headings, paragraph spacing, line wrap,
# and color contrast over substantive content.
SEED_PASSAGE_TEXT = (
    "O Son of Spirit!\n\n"
    "My first counsel is this: Possess a pure, kindly and radiant heart, "
    "that thine may be a sovereignty ancient, imperishable and everlasting.\n\n"
    "O Son of Spirit!\n\n"
    "The best beloved of all things in My sight is Justice. Turn not away "
    "therefrom if thou desirest Me, and neglect it not that I may confide in thee."
)


# Pre-baked comprehension questions for the `with_questions` path (A11Y-5
# #126). Seeding these into the cache makes the questions panel a cache
# HIT, so the reading view renders the real answer UI (labeled textareas +
# <details> reveals) WITHOUT an Anthropic call — letting axe scan it in CI.
# The shape matches PROMPT_VERSION 2: type + text + a source-grounded answer.
SEED_QUESTIONS: list[dict[str, str]] = [
    {
        "type": "recall",
        "text": "What does the first counsel tell the reader to possess?",
        "answer": "A pure, kindly and radiant heart.",
    },
    {
        "type": "recall",
        "text": "What does the speaker call the best beloved of all things?",
        "answer": "Justice.",
    },
    {
        "type": "summary",
        "text": "What two qualities does the passage urge the reader to value?",
        "answer": "A pure heart and justice.",
    },
]


# Per-variant overrides to the stored Preference values. `default` is
# empty (no row created — the reading view falls back to the
# DEFAULT_PREFERENCES path). The other three exercise one axis each so
# any a11y regression points clearly at which preference broke.
_PREFS_FOR_VARIANT: dict[str, dict[str, Any]] = {
    "default": {},
    "high-contrast": {"bg": "#1a1a1a", "fg": "#e8e8e8"},
    "large-text": {"size": "28px"},
    "bionic": {"bionic_enabled": True},
    # READ-P2-2 (#168): dimmed sections are the a11y-relevant part of
    # focus mode — this variant lets axe scan the surface with dimming on.
    "focus-mode": {"focus_mode_enabled": True},
}


@router.post("/test/seed-passage-and-login")
def seed_passage_and_login(
    variant: Variant,
    session: SessionDep,
    settings: SettingsDep,
    with_questions: bool = False,
) -> JSONResponse:
    """Seed a fresh Supabase user + passage + (optional) preference;
    return the Supabase access token as the `sb-access-token` cookie +
    passage id in JSON.

    Each invocation creates an independent throwaway user (UUID-suffixed
    email) so concurrent Playwright tests don't collide on the email
    unique constraint in Supabase Auth.

    When `with_questions=true` (A11Y-5 #126), also seed the comprehension
    cache for this passage so the questions panel renders its real answer
    UI from a cache hit — no Anthropic call — and axe can scan it.
    """
    email = f"a11y-{uuid.uuid4()}@example.test"
    # Supabase requires a password on admin.create_user (even with
    # email_confirm=True). We mint a random one — it's never persisted
    # outside this function; the test only needs the JWT it unlocks.
    password = secrets.token_urlsafe(32)

    admin = service_client().auth.admin
    admin.create_user(
        {
            "email": email,
            "password": password,
            "email_confirm": True,
        }
    )

    # Exchange the password for a real Supabase session JWT — same
    # shape `/auth/callback` produces, so `current_user` (which calls
    # `anon_client().auth.get_user(token)`) accepts it identically.
    auth_resp = anon_client().auth.sign_in_with_password({"email": email, "password": password})
    if auth_resp is None or auth_resp.session is None or auth_resp.user is None:
        raise HTTPException(
            status_code=500,
            detail="Supabase sign-in did not return a session for seeded user.",
        )
    access_token: str = auth_resp.session.access_token
    user_id = uuid.UUID(str(auth_resp.user.id))

    passage = Passage(
        owner_id=user_id,
        # Placeholder hash — the read path doesn't validate it. Note the
        # comprehension route keys its cache on SHA-256(passage.text), not
        # this column, so the `with_questions` seed below hashes the text
        # directly rather than reusing this value.
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
                owner_id=user_id,
                values=prefs_overrides,
                updated_at=datetime.now(UTC),
            )
        )

    if with_questions:
        # Seed the comprehension cache with the EXACT key the questions
        # route looks up (GET /passages/{id}/questions): hash of the
        # passage text, question_type="recall", the configured model, and
        # the current PROMPT_VERSION. The route then cache-hits instead of
        # calling Anthropic.
        comprehension_cache.put_cache(
            passage_hash=hashlib.sha256(SEED_PASSAGE_TEXT.encode("utf-8")).digest(),
            question_type="recall",
            model_id=settings.anthropic_model,
            prompt_version=PROMPT_VERSION,
            questions=SEED_QUESTIONS,
            session=session,
        )

    session.commit()
    session.refresh(passage)

    response = JSONResponse({"passage_id": str(passage.id), "variant": variant})
    response.set_cookie(
        key=SUPABASE_COOKIE_NAME,
        value=access_token,
        # Match the /auth/callback cookie's max-age so the test session
        # behaves the same as a real sign-in.
        max_age=7 * 24 * 60 * 60,
        httponly=True,
        # Test harness runs over plain HTTP on localhost. Production
        # cookies stay `secure=True` via the normal /auth/callback path.
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    return response
