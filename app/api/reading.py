"""Reading-view route.

GET /read/{passage_id} renders the configurable reading surface for a
single passage. The user's preferences are inlined into the template's
`<style>` block as CSS variables — first paint already shows the
correctly-styled text, no client-side reflow.

Owner check: a user can only view their own passages. Other users'
passages return 404 (not 403) — same response shape as a nonexistent
UUID, so the existence of any specific passage isn't leaked.

Per ADR-005 (HTMX, no SPA), all reading-state lives in the URL + cookie
+ DB; no client-side state container.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select

from app.db import get_session
from app.models.passage import Passage
from app.models.preference import Preference
from app.models.user import User
from app.services.identity.session import current_user
from app.services.reading.defaults import with_defaults
from app.templates import templates

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(current_user)]


@router.get("/read/{passage_id}", response_class=HTMLResponse)
def read_passage(
    request: Request,
    passage_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
) -> HTMLResponse:
    """Render the reading view for one passage.

    Loads the passage (filtered by ownership), loads the user's stored
    preferences (or falls back to defaults if no row exists), renders
    the full HTML page with the CSS-variable block already populated.
    """
    passage = session.exec(
        select(Passage).where(Passage.id == passage_id, Passage.user_id == user.id)  # type: ignore[arg-type]
    ).first()
    if passage is None:
        # 404, not 403 — same response shape whether the passage doesn't
        # exist at all or belongs to someone else, so existence isn't
        # leaked.
        raise HTTPException(status_code=404, detail="Passage not found")

    stored_pref = session.get(Preference, user.id)
    prefs = with_defaults(stored_pref.values if stored_pref else None)

    return templates.TemplateResponse(
        request=request,
        name="pages/reading.html",
        context={"passage": passage, "prefs": prefs},
    )
