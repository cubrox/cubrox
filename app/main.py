"""FastAPI application entrypoint.

Run locally:
    uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

Production (Cloud Run) runs the same command — see Dockerfile.
"""

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api import auth, health, home, passages, reading, todos
from app.services.identity.session import UnauthenticatedError

app = FastAPI(title="Agile Flow GCP")


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

# Test-only seed router (A11Y-2 #25). Loaded ONLY when explicitly
# enabled via env var — production Cloud Run revisions never set this.
# See app/api/test_seed.py for the module-level guardrail.
if os.environ.get("CUBROX_TEST_SEED_ENABLED") == "true":
    from app.api import test_seed  # noqa: PLC0415  intentional conditional import
    from app.db import create_db_and_tables  # noqa: PLC0415  test-only path

    # Ensure tables exist before the seed router writes to them. The
    # a11y harness points at a throwaway SQLite file with no migrations
    # applied; in production, this branch is never reached.
    create_db_and_tables()

    app.include_router(test_seed.router)
