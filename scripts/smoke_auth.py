"""Synthetic auth monitor — end-to-end smoke test for the Supabase sign-in path.

Drives the *deployed* app through the full authenticated happy path and exits
non-zero if any step misbehaves. Built for #79 (Supabase replatform epic): its
Definition of Done requires demonstrating "magic-link login via Supabase →
session persists across reloads → logout clears session." This script is that
demonstration, runnable on a schedule so the guarantee keeps holding.

It also guards the specific regression that bit us once: after the Neon→Supabase
cutover, production silently kept serving the old Neon-backed revision for ~24h.
Unit tests (which mock Supabase) could never have caught that — only something
that hits the *real* deployed URL with a *real* Supabase session can.

## What it does

1. Mint a throwaway, email-confirmed Supabase user via the admin API and
   exchange its password for a real session JWT. This is the same mechanism the
   a11y test-seed route uses (`app/api/test_seed.py`) — proven against the local
   Supabase stack in CI — so the token is byte-for-byte what `/auth/callback`
   produces for a genuine magic-link sign-in.
2. Hit the live app over HTTP:
   - `GET /auth/callback?access_token=…&refresh_token=…` → expect a 303 to
     `/passages/new` with an `sb-access-token` cookie set.
   - `GET /passages/new` (cookie attached) → expect 200 + the authed page.
   - `GET /passages/new` again → still 200, proving the session persists across
     reloads.
   - `GET /logout` → expect a 303 to `/` that clears the cookie.
   - `GET /passages/new` (cookie now gone) → expect a 303 back to `/`, proving
     the session is actually gone.
3. Delete the throwaway user, always (even if an assertion fails).

## What it deliberately does NOT cover

- **Supabase's own email-link generation.** We mint the session server-side
  rather than clicking a real emailed link. POST /login → `sign_in_with_otp`
  is unit-tested separately; this monitor is about our token-validation,
  session, and logout contract against the live deploy.
- **The browser-side JS hash extractor** (`/auth/callback` stage 1). That moves
  the token from the URL fragment into query params *in a real browser*; a
  headless HTTP client has the token already, so it calls stage 2 directly. The
  Playwright a11y suite exercises real browser rendering.

## Configuration (all via environment)

- `SMOKE_BASE_URL`        — base URL of the app to probe, e.g.
                            `https://cubrox-xxxxx-uc.a.run.app` (no trailing /).
- `SUPABASE_URL`          — Supabase project URL (to mint the session).
- `SUPABASE_ANON_KEY`     — anon key (password sign-in).
- `SUPABASE_SERVICE_KEY`  — service-role key (admin create/delete user).

## Exit codes

- 0 — every step passed.
- 1 — a step failed, or configuration was missing. A clear `FAIL:` line names
      the first thing that broke.

## Local run

Point it at a local app + local Supabase stack (needs Docker):

    supabase start   # exports the local URL + keys
    SMOKE_BASE_URL=http://127.0.0.1:8080 \
    SUPABASE_URL=… SUPABASE_ANON_KEY=… SUPABASE_SERVICE_KEY=… \
    uv run python scripts/smoke_auth.py
"""

from __future__ import annotations

import os
import secrets
import sys
import uuid

import httpx

from supabase import Client, create_client

# Marks the throwaway accounts this monitor creates, so any that leak (e.g. a
# crash between create and delete) are obvious in the Supabase user list.
SMOKE_EMAIL_DOMAIN = "smoke.cubrox.test"

EXPECTED_COOKIE = "sb-access-token"
AUTHED_ENTRY_PATH = "/passages/new"
# Stable marker from templates/pages/passages_new.html — the authed entry page.
AUTHED_PAGE_MARKER = "Add a passage"

HTTP_TIMEOUT_SECONDS = 30.0


class SmokeFailure(Exception):
    """Raised when a step's observed behavior doesn't match expectations."""


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SmokeFailure(f"missing required environment variable: {name}")
    return value


def _step(message: str) -> None:
    print(f"-> {message}", flush=True)


def _cookie_header_clears(set_cookie_values: list[str]) -> bool:
    """True if any Set-Cookie line expires/empties the session cookie.

    `Response.delete_cookie` emits a Set-Cookie with an empty value plus a past
    `expires`/`Max-Age=0`. We accept any of those signals rather than matching
    Starlette's exact formatting, which has drifted across versions.
    """
    for raw in set_cookie_values:
        if not raw.startswith(f"{EXPECTED_COOKIE}="):
            continue
        value_part = raw.split(";", 1)[0]
        token = value_part.split("=", 1)[1].strip().strip('"')
        lowered = raw.lower()
        if token == "" or "max-age=0" in lowered or "expires=thu, 01 jan 1970" in lowered:
            return True
    return False


def create_throwaway_user(service: Client) -> tuple[str, str, str]:
    """Create a confirmed throwaway user; return (user_id, email, password).

    Split from sign-in deliberately: the caller must learn `user_id` the
    instant the user exists, so its `finally` can always delete it — even if
    the subsequent sign-in step raises. Folding create + sign-in into one
    function hid the user_id until success and leaked the user on a sign-in
    error.

    Mirrors app/api/test_seed.py: admin.create_user(email_confirm=True).
    """
    email = f"smoke-{uuid.uuid4()}@{SMOKE_EMAIL_DOMAIN}"
    password = secrets.token_urlsafe(32)

    created = service.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    if created is None or created.user is None:
        raise SmokeFailure("Supabase admin.create_user did not return a user")
    return str(created.user.id), email, password


def sign_in(anon: Client, email: str, password: str) -> tuple[str, str]:
    """Exchange the throwaway user's password for a session; return (access, refresh).

    The resulting JWT is identical in shape to what a real magic-link sign-in
    yields, so `/auth/callback` and `current_user` accept it identically.
    """
    auth_resp = anon.auth.sign_in_with_password({"email": email, "password": password})
    if auth_resp is None or auth_resp.session is None:
        raise SmokeFailure("Supabase sign-in did not return a session for the seeded user")
    return auth_resp.session.access_token, auth_resp.session.refresh_token or ""


def run_flow(base_url: str, access_token: str, refresh_token: str) -> None:
    """Drive the live app through callback → authed page → reload → logout.

    Raises SmokeFailure on the first deviation from the expected contract.
    """
    base = base_url.rstrip("/")
    with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS, follow_redirects=False) as client:
        _step("GET /auth/callback (stage 2) — expect 303 to /passages/new + session cookie")
        callback = client.get(
            f"{base}/auth/callback",
            params={"access_token": access_token, "refresh_token": refresh_token},
        )
        if callback.status_code != 303:
            raise SmokeFailure(f"/auth/callback returned {callback.status_code}, expected 303")
        location = callback.headers.get("location", "")
        if location != AUTHED_ENTRY_PATH:
            raise SmokeFailure(
                f"/auth/callback redirected to {location!r}, expected {AUTHED_ENTRY_PATH!r}"
            )
        if not any(
            v.startswith(f"{EXPECTED_COOKIE}=") for v in callback.headers.get_list("set-cookie")
        ):
            raise SmokeFailure(f"/auth/callback did not set the {EXPECTED_COOKIE} cookie")
        if EXPECTED_COOKIE not in client.cookies:
            raise SmokeFailure(f"{EXPECTED_COOKIE} cookie was not stored after callback")

        _step("GET /passages/new — expect 200 authed page")
        authed = client.get(f"{base}{AUTHED_ENTRY_PATH}")
        if authed.status_code != 200:
            raise SmokeFailure(
                f"{AUTHED_ENTRY_PATH} returned {authed.status_code} while authed, expected 200"
            )
        if AUTHED_PAGE_MARKER not in authed.text:
            raise SmokeFailure(
                f"{AUTHED_ENTRY_PATH} body missing expected marker {AUTHED_PAGE_MARKER!r}"
            )

        _step("GET /passages/new again — expect 200, session persists across reloads")
        reload_resp = client.get(f"{base}{AUTHED_ENTRY_PATH}")
        if reload_resp.status_code != 200:
            raise SmokeFailure(
                f"session did not persist across reload: {AUTHED_ENTRY_PATH} returned "
                f"{reload_resp.status_code}, expected 200"
            )

        _step("GET /logout — expect 303 to / and a cleared session cookie")
        logout = client.get(f"{base}/logout")
        if logout.status_code != 303:
            raise SmokeFailure(f"/logout returned {logout.status_code}, expected 303")
        if logout.headers.get("location", "") != "/":
            raise SmokeFailure(
                f"/logout redirected to {logout.headers.get('location')!r}, expected '/'"
            )
        if not _cookie_header_clears(logout.headers.get_list("set-cookie")):
            raise SmokeFailure("/logout did not clear the session cookie")

        _step("GET /passages/new after logout — expect 303 to /, session is gone")
        after_logout = client.get(f"{base}{AUTHED_ENTRY_PATH}")
        if after_logout.status_code != 303:
            raise SmokeFailure(
                f"{AUTHED_ENTRY_PATH} returned {after_logout.status_code} after logout, "
                "expected 303 (session should be gone)"
            )
        if after_logout.headers.get("location", "") != "/":
            raise SmokeFailure(
                f"post-logout redirect went to {after_logout.headers.get('location')!r}, "
                "expected '/'"
            )


def main() -> int:
    try:
        base_url = _require_env("SMOKE_BASE_URL")
        supabase_url = _require_env("SUPABASE_URL")
        anon_key = _require_env("SUPABASE_ANON_KEY")
        service_key = _require_env("SUPABASE_SERVICE_KEY")
    except SmokeFailure as exc:
        print(f"FAIL: {exc}", flush=True)
        return 1

    print(f"Synthetic auth monitor → {base_url}", flush=True)

    service_client = create_client(supabase_url, service_key)
    anon = create_client(supabase_url, anon_key)

    # Learn user_id BEFORE sign-in so the finally below always cleans up,
    # even if sign-in raises (a transient Supabase error). Initialized None
    # so a create-user failure leaves nothing to delete.
    user_id: str | None = None
    try:
        user_id, email, password = create_throwaway_user(service_client)
        _step(f"created throwaway user {user_id}")
        access_token, refresh_token = sign_in(anon, email, password)
        _step("minted session via password grant")
        run_flow(base_url, access_token, refresh_token)
    except SmokeFailure as exc:
        print(f"FAIL: {exc}", flush=True)
        return 1
    except httpx.HTTPError as exc:
        print(f"FAIL: HTTP error reaching {base_url}: {exc}", flush=True)
        return 1
    except Exception as exc:  # noqa: BLE001 — Supabase client errors (AuthApiError, etc.)
        # A monitor's own crash should read as a clean FAIL, not a traceback —
        # otherwise an upstream Supabase hiccup looks like a code bug.
        print(f"FAIL: unexpected error: {type(exc).__name__}: {exc}", flush=True)
        return 1
    finally:
        if user_id is not None:
            try:
                service_client.auth.admin.delete_user(user_id)
                _step(f"cleaned up throwaway user {user_id}")
            except Exception as exc:  # noqa: BLE001 — cleanup must never mask the real result
                print(f"WARN: failed to delete throwaway user {user_id}: {exc}", flush=True)

    print("PASS: magic-link session → authed page → reload → logout all verified", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
