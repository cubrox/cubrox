"""FastAPI application entrypoint.

Run locally:
    uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

Production (Cloud Run) runs the same command — see Dockerfile.
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api import auth, health, todos
from app.services.identity.session import UnauthenticatedError

app = FastAPI(title="Agile Flow GCP")


@app.exception_handler(UnauthenticatedError)
async def _handle_unauthenticated(request: Request, exc: UnauthenticatedError) -> Response:
    """Convert UnauthenticatedError into the right response shape.

    Top-level browser navigation gets a 303 to /login. HTMX requests
    (intercepted by HTMX before the browser sees them) get a 200 with
    an `HX-Redirect: /login` header — HTMX reads that header and
    performs a client-side redirect. Without this branch, HTMX would
    swallow the 303 and the user's URL bar wouldn't change.
    """
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=200, headers={"HX-Redirect": "/login"})
    return RedirectResponse(url="/login", status_code=303)


# Mount static files (CSS, images, favicon).
# Pico.css is loaded via CDN in base.html so this directory is light.
STATIC_DIR = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Routes
app.include_router(health.router)
app.include_router(todos.router)
app.include_router(auth.router)
