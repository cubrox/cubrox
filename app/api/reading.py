"""Reading-view + preference-toggle routes.

GET  /read/{passage_id}     — render the configurable reading surface
POST /preferences/{key}     — set one preference, return the swappable
                              <style> fragment for HTMX outerHTML

Owner check on the GET: a user can only view their own passages. Other
users' passages return 404 (not 403) — same response shape as a
nonexistent UUID, so the existence of any specific passage isn't leaked.

Per ADR-005 (HTMX, no SPA), all reading-state lives in the URL + cookie
+ DB; no client-side state container. The POST returns ONLY the
`<style id="reading-surface-style">` fragment so HTMX can swap it
in place without touching anything else on the page.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select

from app.db import get_session
from app.models.passage import Passage
from app.models.preference import Preference
from app.models.user import User
from app.services.identity.session import current_user
from app.services.reading.defaults import with_defaults
from app.services.reading.options import (
    PREFERENCE_OPTIONS,
    coerce_value,
    label_for,
)
from app.services.reading.preferences import upsert_preference
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
    the full HTML page with the CSS-variable block already populated
    AND the preference-toggle sidebar wired up.
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
        context={
            "passage": passage,
            "prefs": prefs,
            "preference_options": PREFERENCE_OPTIONS,
            "label_for": label_for,
        },
    )


@router.post("/preferences/{key}", response_class=HTMLResponse)
def update_preference(
    request: Request,
    key: str,
    user: CurrentUser,
    session: SessionDep,
    value: Annotated[str, Form()],
) -> HTMLResponse:
    """Set ONE preference and return the swappable <style> fragment.

    Returns a fragment, not a full page — HTMX `outerHTML` swaps it
    into `#reading-surface-style` without touching anything else.

    Validation gates user input against PREFERENCE_OPTIONS in
    app/services/reading/options.py — both the key and the value must
    be allow-listed. This is the dependent invariant the READ-1
    reviewer flagged: without it, the `| safe` filter in the template
    would let a user inject arbitrary CSS.
    """
    if key not in PREFERENCE_OPTIONS:
        raise HTTPException(status_code=422, detail=f"Unknown preference key: {key!r}")

    coerced = coerce_value(key, value)
    if coerced is None or coerced not in PREFERENCE_OPTIONS[key]:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid value for {key!r}",
        )

    upsert_preference(user_id=user.id, key=key, value=coerced, session=session)
    session.commit()

    # Re-read for the freshest merged view (handles both the new-row
    # case and the existing-row case uniformly).
    stored_pref = session.get(Preference, user.id)
    prefs = with_defaults(stored_pref.values if stored_pref else None)

    return templates.TemplateResponse(
        request=request,
        name="fragments/reader_style.html",
        context={"prefs": prefs},
    )
