"""FastAPI application entrypoint.

Run locally:
    uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

Production (Cloud Run) runs the same command — see Dockerfile.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import auth, health, todos

app = FastAPI(title="Agile Flow GCP")

# Mount static files (CSS, images, favicon).
# Pico.css is loaded via CDN in base.html so this directory is light.
STATIC_DIR = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Routes
app.include_router(health.router)
app.include_router(todos.router)
app.include_router(auth.router)
