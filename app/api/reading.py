"""Reading-view + preference-toggle + comprehension-question routes.

GET  /read/{passage_id}             — render the configurable reading surface
POST /preferences/{key}             — set one preference, return the
                                       swappable <style> fragment
GET  /passages/{passage_id}/questions — HTMX-lazy-loaded comprehension
                                        question fragment
POST /passages/{passage_id}/close   — unload-time beacon recording one
                                        reading_event row (METRIC-2)

Owner check on the GET: a user can only view their own passages. Other
users' passages return 404 (not 403) — same response shape as a
nonexistent UUID, so the existence of any specific passage isn't leaked.

Per ADR-005 (HTMX, no SPA), all reading-state lives in the URL + cookie
+ DB; no client-side state container. The preference POST and questions
GET return ONLY fragments so HTMX can swap them in place without
touching anything else on the page.
"""

import logging
import uuid
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select

from app.config import Settings, get_settings
from app.db import get_session
from app.integrations.supabase.auth import current_user
from app.models.passage import Passage
from app.models.preference import Preference
from app.models.reading_event import ReadingEvent
from app.services.comprehension.client import get_anthropic_client
from app.services.comprehension.generator import (
    GeneratorError,
    PassageTooLongError,
    generate_questions,
)
from app.services.reading.defaults import with_defaults
from app.services.reading.options import (
    PREFERENCE_OPTIONS,
    coerce_value,
    label_for,
    label_for_key,
    value_for_form,
)
from app.services.reading.preferences import upsert_preference
from app.templates import templates

if TYPE_CHECKING:
    import anthropic

logger = logging.getLogger(__name__)

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
CurrentUser = Annotated[Any, Depends(current_user)]
AnthropicClientDep = Annotated["anthropic.Anthropic", Depends(get_anthropic_client)]


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
        select(Passage).where(Passage.id == passage_id, Passage.owner_id == user.id)  # type: ignore[arg-type]
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
            "label_for_key": label_for_key,
            "value_for_form": value_for_form,
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

    upsert_preference(owner_id=user.id, key=key, value=coerced, session=session)
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


@router.get("/passages/{passage_id}/questions", response_class=HTMLResponse)
def passage_questions(
    request: Request,
    passage_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    anthropic_client: AnthropicClientDep,
) -> HTMLResponse:
    """Return the comprehension-question fragment for one passage.

    HTMX-lazy-loaded from the reading view: the `<div id="questions-
    panel" hx-trigger="load delay:200ms">` placeholder fires this
    route ~200ms after the page first paints, so the reading surface
    feels instant even when a cache-miss + LLM call adds latency.

    Three response shapes (all 200, all HTML fragments):
      - Success → questions list inside <section aria-label="...">
      - PassageTooLongError → friendly "split it" message
      - GeneratorError → "temporarily unavailable" message (logged WARN)

    Owner check mirrors GET /read: cross-user passage and nonexistent
    passage both return 404 with identical body to avoid leaking
    existence.
    """
    passage = session.exec(
        select(Passage).where(Passage.id == passage_id, Passage.owner_id == user.id)  # type: ignore[arg-type]
    ).first()
    if passage is None:
        raise HTTPException(status_code=404, detail="Passage not found")

    questions: list[dict] | None = None
    error: str | None = None

    try:
        questions = generate_questions(
            passage_text=passage.text,
            question_type="recall",
            client=anthropic_client,
            model_id=settings.anthropic_model,
            session=session,
        )
    except PassageTooLongError:
        # User-recoverable: tell them to split. NOT logged at WARN
        # because it's expected behaviour on long passages.
        error = "too_long"
    except GeneratorError:
        # System-side: log so we can investigate, surface a friendly
        # message to the user. NEVER 500 because comprehension is a
        # feature, not a hard dependency.
        logger.warning(
            "comprehension generator failed",
            extra={"passage_id": str(passage_id), "owner_id": str(user.id)},
        )
        error = "unavailable"

    return templates.TemplateResponse(
        request=request,
        name="fragments/questions_panel.html",
        context={"questions": questions, "error": error},
    )


# Inclusive bounds for client-supplied line counts. 1 is the natural
# floor (zero lines processed is meaningless noise). 100_000 mirrors
# INGEST-1's text-length cap — any value above that means the client
# is lying or the column count broke.
_MIN_LINES = 1
_MAX_LINES = 100_000


@router.post("/passages/{passage_id}/close")
def passage_close(
    passage_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    lines: Annotated[int, Form()],
) -> Response:
    """Record one `reading_event` row when the user closes a passage.

    Fired by HTMX `hx-trigger="unload from:body"` on the reading view's
    hidden beacon div. Returns 204 No Content — the response body is
    irrelevant because the browser is already tearing down the page.

    Ownership check is identical to GET /read: a user closing someone
    else's passage gets a 404 (same body as a nonexistent UUID) so
    we don't leak which IDs exist.

    Validation is permissive: out-of-range `lines` values get a 204
    with NO row inserted (logged but otherwise silent). The unload
    path can't surface errors anyway, so a noisy 4xx would be wasted —
    better to drop the bad data and move on.

    Idempotency: this route does NOT deduplicate. Browser quirks
    (back/forward cache, refresh, bfcache restore) will occasionally
    double-fire. The PRD metric tolerates a small over-count; revisit
    only if dogfooding shows material divergence from manual counts.
    """
    passage = session.exec(
        select(Passage).where(Passage.id == passage_id, Passage.owner_id == user.id)  # type: ignore[arg-type]
    ).first()
    if passage is None:
        # Same 404 as cross-user/nonexistent on GET /read; preserves the
        # "existence isn't leaked" invariant.
        raise HTTPException(status_code=404, detail="Passage not found")

    if not (_MIN_LINES <= lines <= _MAX_LINES):
        logger.warning(
            "passage_close.invalid_lines owner_id=%s passage_id=%s lines=%s",
            user.id,
            passage_id,
            lines,
        )
        return Response(status_code=204)

    session.add(
        ReadingEvent(
            owner_id=user.id,
            passage_id=passage_id,
            lines_processed=lines,
        )
    )
    session.commit()

    return Response(status_code=204)
