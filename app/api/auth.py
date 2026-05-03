"""Sign-in routes.

POST /login mints a magic-link token and emails it. The response is a
short HTML fragment confirming the action; the same fragment is
returned whether the email is known or unknown so the route can't be
used for account enumeration. Per ADR-002 in
docs/TECHNICAL-ARCHITECTURE.md.

GET /auth/verify (token consumption) ships in AUTH-2.
"""

from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.services.identity import magic_link

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

GENERIC_FRAGMENT = "<p>Check your inbox for a sign-in link.</p>"


@router.post("/login", response_class=HTMLResponse, status_code=202)
def login(
    background_tasks: BackgroundTasks,
    session: SessionDep,
    settings: SettingsDep,
    email: Annotated[str, Form()],
) -> str:
    """Issue a magic link to the supplied email.

    Returns the same 202 + fragment for known, unknown, and unrouteable
    addresses (after format validation). The only failure visible to the
    client is a 422 for malformed-format input.
    """
    try:
        result = validate_email(email, check_deliverability=False)
    except EmailNotValidError as exc:
        raise HTTPException(status_code=422, detail="Invalid email format") from exc

    normalized_email = result.normalized.lower()

    magic_link.request_magic_link(
        email=normalized_email,
        session=session,
        settings=settings,
        background_tasks=background_tasks,
    )

    return GENERIC_FRAGMENT
