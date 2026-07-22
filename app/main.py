"""FastAPI application entrypoint.

Run locally:
    uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

Production (Cloud Run) runs the same command — see Dockerfile.
"""

import os
from pathlib import Path

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from app.api import auth, health, home, passages, reading, todos
from app.config import get_settings
from app.integrations.supabase.auth import UnauthenticatedError

# OBS-1 (#167): initialise Sentry before the app is constructed so the
# Starlette/FastAPI integrations wrap the whole middleware stack.
#
# Gated on SENTRY_DSN being set: unset (local dev, CI, tests) means no
# init at all and the app behaves exactly as it did before this ticket —
# no network calls, no middleware, no behavioural difference. That is why
# the guard is on the DSN rather than on `environment`.
#
# Error capture only. `traces_sample_rate` is deliberately NOT set —
# performance tracing is a separate tuning (and cost) decision, and
# leaving it unset keeps the SDK's tracing off by default.
#
# No route/service/model file imports sentry_sdk: the integrations
# capture unhandled exceptions automatically via middleware, so manual
# instrumentation would be redundant.
_settings = get_settings()
if _settings.sentry_dsn:
    sentry_sdk.init(
        dsn=_settings.sentry_dsn,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        environment=_settings.environment,
    )

app = FastAPI(title="Master Key")


@app.exception_handler(UnauthenticatedError)
async def _handle_unauthenticated(request: Request, exc: UnauthenticatedError) -> Response:
    """Convert UnauthenticatedError into the right response shape.

    Top-level browser navigation gets a 303 to / (the landing page,
    which serves the sign-in form). HTMX requests (intercepted by
    HTMX before the browser sees them) get a 200 with an
    `HX-Redirect: /` header — HTMX reads that header and performs a
    client-side redirect. Without this branch, HTMX would swallow
    the 303 and the user's URL bar wouldn't change.

    Note: the redirect target is `/`, not `/login`. `/login` is a
    POST-only API endpoint that handles form submission, not a page.
    Sending unauthenticated visitors to a POST-only endpoint via GET
    would land them on a 405 Method Not Allowed. The landing page at
    `/` is the actual sign-in entry point — visiting it shows the
    form whose submit handler hits `/login`.
    """
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=200, headers={"HX-Redirect": "/"})
    return RedirectResponse(url="/", status_code=303)


# Mount static files (CSS, images, favicon).
# Pico.css is loaded via CDN in base.html so this directory is light.
STATIC_DIR = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Routes
app.include_router(home.router)
app.include_router(health.router)
app.include_router(todos.router)
app.include_router(auth.router)
app.include_router(passages.router)
app.include_router(reading.router)

# Test-only seed router (A11Y-2 #25, restored in #97). Only mounts when
# MASTERKEY_TEST_SEED_ENABLED=true — the CI a11y job sets this via
# playwright.config.ts > webServer.env. Production Cloud Run revisions
# never set it, so the router is unreachable in prod. The router file
# itself has a second module-level guard so a stray `import` would
# also fail loudly.
if os.environ.get("MASTERKEY_TEST_SEED_ENABLED") == "true":
    from app.api import test_seed

    app.include_router(test_seed.router)
