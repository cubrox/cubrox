"""Sign-in routes via Supabase Auth (GoTrue magic-link).

POST /login: hands the email to Supabase, which mints a magic-link
token and emails it. Returns a generic 202 fragment — the same fragment
regardless of whether the email exists, so the route can't be used for
account enumeration (Supabase's `should_create_user=True` default does
the same on the auth side).

GET /auth/callback: two-stage handler.

  1. First hit (no query params): Supabase puts the JWT in the URL
     hash fragment (`#access_token=...&refresh_token=...`), which the
     browser does NOT send to the server. We render a tiny JS page
     that reads `window.location.hash`, converts to query params, and
     redirects to the same path with those tokens visible to the
     server.
  2. Second hit (query params present): validate the access_token via
     Supabase, set it as an HttpOnly cookie, redirect to the app.

GET /logout: clears both cookies (sb-access-token AND the legacy
session cookie) and signs out of Supabase.

The legacy `User` SQLModel is still alive — see the transitional
shim in `app/services/identity/session.py`. SUPA-2b (#87) removes it.
"""

from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from supabase_auth.errors import AuthApiError

from app.config import Settings, get_settings
from app.integrations.supabase.auth import SUPABASE_COOKIE_NAME, current_user
from app.integrations.supabase.client import anon_client
from app.services.rate_limit import enforce_login_rate_limit

router = APIRouter()

SettingsDep = Annotated[Settings, Depends(get_settings)]
CurrentUser = Annotated[object, Depends(current_user)]  # User; loose typing for transition

GENERIC_FRAGMENT = "<p>Check your inbox for a sign-in link.</p>"

# Cookie max-age. Supabase access tokens default to 1 hour but the
# client refreshes them automatically; the cookie's max-age is the
# upper bound on how long the user stays signed in across reloads.
SB_COOKIE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60  # 7 days


def _external_origin(request: Request, fallback: str) -> str:
    """Resolve the public origin for redirect URLs.

    Cloud Run sits behind a Google proxy; `request.url` reports the
    internal origin, which would break the magic-link callback (per
    Pattern #4 in PATTERN-LIBRARY.md). Read `X-Forwarded-*` headers
    first; fall back to the configured `app_url` for local dev.
    """
    proto = request.headers.get("x-forwarded-proto")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if proto and host:
        return f"{proto}://{host}"
    return fallback.rstrip("/")


@router.post(
    "/login",
    response_class=HTMLResponse,
    status_code=202,
    dependencies=[Depends(enforce_login_rate_limit)],
)
def login(
    request: Request,
    settings: SettingsDep,
    email: Annotated[str, Form()],
) -> str:
    """Issue a Supabase magic-link to the supplied email.

    Returns the same 202 + fragment for any well-formed email
    regardless of whether the address exists in `auth.users` —
    Supabase will create the user on first verify, and we deliberately
    don't surface "unknown email" so this route can't enumerate.

    Failures visible to the client:
      - 422 for malformed email format.
      - 429 with Retry-After when Supabase's shared SMTP pool rate-
        limits us (#247, from #245 postmortem) — the app maps this to
        a user-facing "try again in a few minutes" message so HTMX/
        browsers back off gracefully. Custom SMTP via Resend (#246)
        moves rate limits off Supabase's shared pool structurally.
      - 502 for anything else (network, config bug, non-rate-limit
        Supabase error). Enumeration guard: generic message.
    """
    try:
        result = validate_email(email, check_deliverability=False)
    except EmailNotValidError as exc:
        raise HTTPException(status_code=422, detail="Invalid email format") from exc

    normalized_email = result.normalized.lower()
    origin = _external_origin(request, settings.app_url)
    redirect_url = f"{origin}/auth/callback"

    try:
        anon_client().auth.sign_in_with_otp(
            {
                "email": normalized_email,
                "options": {"email_redirect_to": redirect_url},
            }
        )
    except AuthApiError as exc:
        # Supabase-side error. Distinguish rate limits from everything
        # else so users get an actionable message and operators get a
        # meaningful status code (429 is the standard signal that
        # HTMX/browsers already know how to back off from). Enumeration
        # guard: we don't echo Supabase's message verbatim for non-rate-
        # limit errors (which can leak whether an email is known).
        if exc.code == "over_email_send_rate_limit" or "rate limit" in exc.message.lower():
            raise HTTPException(
                status_code=429,
                detail="Too many sign-in emails just now. Please try again in a few minutes.",
                headers={"Retry-After": "300"},
            ) from exc
        raise HTTPException(status_code=502, detail="Sign-in unavailable") from exc
    except Exception as exc:
        # Non-Supabase failure (network, config, code bug). Same 502 as
        # before so operators can spot the class from Cloud Logging.
        raise HTTPException(status_code=502, detail="Sign-in unavailable") from exc

    return GENERIC_FRAGMENT


@router.get("/auth/callback", response_model=None)
def auth_callback(
    request: Request,
    settings: SettingsDep,
    access_token: str = "",
    refresh_token: str = "",
) -> Response:
    """Two-stage callback for the Supabase magic-link click.

    Stage 1 (no `access_token` query param): render the JS bridge
    page. The browser is now sitting on a URL like
    `<app>/auth/callback#access_token=...&refresh_token=...`; the JS
    in the rendered page reads the hash, builds query params, and
    redirects to stage 2.

    Stage 2 (`access_token` present): validate via Supabase, set the
    HttpOnly cookie, redirect to the reading-app entry point.
    """
    if not access_token:
        # Stage 1: hash-extractor page. Inline HTML rather than a
        # template — this is ~20 lines and tightly coupled to the
        # specific URL path, not the kind of thing worth a template
        # round-trip for.
        return HTMLResponse(
            content=(
                "<!doctype html>"
                '<html lang="en"><head><meta charset="utf-8"><title>Signing in…</title></head>'
                "<body>"
                "<p>Signing in…</p>"
                "<script>"
                "(function(){"
                "var hash = window.location.hash.substring(1);"
                "if (!hash) {"
                "  document.body.innerHTML = '<p>Sign-in link is invalid or has expired. "
                '<a href=\\"/\\">Try again</a>.</p>\';'
                "  return;"
                "}"
                "var params = new URLSearchParams(hash);"
                "var at = params.get('access_token');"
                "var rt = params.get('refresh_token') || '';"
                "if (!at) {"
                "  document.body.innerHTML = '<p>Sign-in link is invalid or has expired. "
                '<a href=\\"/\\">Try again</a>.</p>\';'
                "  return;"
                "}"
                "var qs = new URLSearchParams({access_token: at, refresh_token: rt});"
                "window.location.replace('/auth/callback?' + qs.toString());"
                "})();"
                "</script>"
                "</body></html>"
            )
        )

    # Stage 2: validate the token by asking Supabase who it belongs to.
    # A failed lookup → 410 (matches the old /auth/verify failure
    # shape so existing 4xx-monitoring stays consistent).
    try:
        resp = anon_client().auth.get_user(access_token)
    except Exception:
        resp = None
    if resp is None or resp.user is None:
        raise HTTPException(status_code=410, detail="Sign-in link expired or invalid")

    # Drop the freshly-signed-in user on the paste/upload page, same
    # as the old /auth/verify route — see BUG-2 / #51 for rationale.
    response = RedirectResponse(url="/passages/new", status_code=303)
    response.set_cookie(
        key=SUPABASE_COOKIE_NAME,
        value=access_token,
        max_age=SB_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    return response


@router.get("/logout")
def logout(settings: SettingsDep) -> RedirectResponse:
    """Sign out: revoke the Supabase session and clear the cookie."""
    try:
        anon_client().auth.sign_out()
    except Exception:
        # Non-fatal: even if Supabase didn't acknowledge the sign-out,
        # we still want to clear the local cookie and redirect.
        pass

    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(
        key=SUPABASE_COOKIE_NAME,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    return response


@router.get("/api/me")
def me(user: CurrentUser) -> dict[str, str]:
    """Return the signed-in user's id + email.

    Works through the dual-path `current_user` dependency, so either a
    Supabase JWT cookie or (transitionally) a legacy itsdangerous
    cookie can authenticate.
    """
    return {"id": str(user.id), "email": user.email}  # type: ignore[attr-defined]
