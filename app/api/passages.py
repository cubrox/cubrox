"""Passage ingestion routes.

Two endpoints for the paste-text path:
  GET  /passages/new — render the paste form (auth-required)
  POST /passages     — persist the pasted text, redirect to /read/{id}

Both require an authenticated user; unauthenticated requests get the
standard /login redirect via the `current_user` dependency. Per ADR
guardrails, this route writes the text byte-for-byte (no normalization)
so the SHA-256 hash matches what the comprehension cache will look up.

PDF ingestion is a separate route in INGEST-2 (#14); it lives here too
when shipped.
"""

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from app.db import get_session
from app.models.passage import Passage
from app.models.user import User
from app.services.identity.session import current_user
from app.templates import templates

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(current_user)]

# Hard ceiling on a single passage. ~100k chars is around 4k lines of
# regular prose — enough for a chapter-length excerpt, far enough below
# Cloud Run's 32 MB request body limit to stay safe.
MAX_TEXT_LEN = 100_000


@router.get("/passages/new", response_class=HTMLResponse)
def new_passage_form(request: Request, user: CurrentUser) -> HTMLResponse:
    """Render the paste-text form."""
    return templates.TemplateResponse(
        request=request,
        name="pages/passages_new.html",
        context={"user": user},
    )


@router.post("/passages")
def create_passage(
    user: CurrentUser,
    session: SessionDep,
    text: Annotated[str, Form()],
) -> RedirectResponse:
    """Persist the pasted text and redirect to the reading view.

    Validation rules (per ticket guardrails):
      - 1 <= len(text) <= MAX_TEXT_LEN
      - text_hash = SHA-256 of the EXACT submitted bytes (no strip,
        no lowercase) so cross-user cache hits work
      - source_type='paste', source_filename=None
    """
    if len(text) == 0:
        raise HTTPException(status_code=422, detail="Text is required")
    if len(text) > MAX_TEXT_LEN:
        raise HTTPException(
            status_code=422,
            detail=f"Passage exceeds {MAX_TEXT_LEN:,}-character limit",
        )

    text_hash = hashlib.sha256(text.encode("utf-8")).digest()
    passage = Passage(
        user_id=user.id,
        text=text,
        text_hash=text_hash,
        source_type="paste",
        source_filename=None,
    )
    session.add(passage)
    session.commit()
    session.refresh(passage)

    # /read/{id} ships in READ-1 (#15). Until then this redirect lands
    # on a 404 — the URL shape is what matters for downstream wiring.
    return RedirectResponse(url=f"/read/{passage.id}", status_code=303)
