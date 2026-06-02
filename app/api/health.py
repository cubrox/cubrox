"""Health check endpoints.

`/api/health` — fast probe used by Cloud Run readiness checks. Does NOT
touch the database (a DB cold-wake on every probe is expensive).

`/api/health/db` — DB-backed probe used by the preview-deploy smoke test
to verify the deploy actually has a working database connection. Added
in #78 because preview deploys without a database configured were passing
the no-DB `/api/health` probe and shipping a broken URL.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlmodel import Session

from app.db import get_session

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/api/health")
async def health() -> JSONResponse:
    """Return 200 with a small JSON body.

    Deliberately does NOT touch the database — health checks must be
    fast and not wake up the database on every probe.
    """
    return JSONResponse({"status": "ok"})


@router.get("/api/health/db")
def health_db(session: SessionDep) -> JSONResponse:
    """Single-query DB probe — `SELECT 1`.

    Used by preview-deploy.yml to validate that the deployed revision
    can reach the database. Cheap (single round-trip, no schema), but
    distinct from `/api/health`: a revision with `DATABASE_URL=""` or
    a misconfigured database connection fails this and passes `/api/health`.
    Uses SQLAlchemy's `session.execute(text(...))` because SQLModel's
    typed `session.exec()` only accepts SQLModel statements.
    """
    session.execute(text("SELECT 1"))
    return JSONResponse({"status": "ok"})
