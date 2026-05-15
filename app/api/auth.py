"""Sign-in routes.

POST /login mints a magic-link token and emails it. The response is a
short HTML fragment confirming the action; the same fragment is
returned whether the email is known or unknown so the route can't be
used for account enumeration. Per ADR-002 in
docs/TECHNICAL-ARCHITECTURE.md.

GET /auth/verify consumes the magic-link token and issues the signed
session cookie. Single-use; the same UPDATE that marks the token
consumed also tells us the owning user, so the consumption is one
atomic round-trip.
"""

import hashlib
from datetime import UTC, datetime
from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import update
from sqlmodel import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.models.magic_link_token import MagicLinkToken
from app.models.user import User
from app.services.identity import magic_link
from app.services.identity.session import (
    SESSION_COOKIE_NAME,
    current_user,
    sign_session,
)
from app.services.rate_limit import (
    enforce_login_rate_limit,
    enforce_verify_rate_limit,
)

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
CurrentUser = Annotated[User, Depends(current_user)]

GENERIC_FRAGMENT = "<p>Check your inbox for a sign-in link.</p>"

# Core-style table handle for the atomic consume-and-return UPDATE.
# Same pattern as app/services/identity/magic_link.py — sidesteps mypy
# friction with SQLModel attribute typing.
_TOKEN_TABLE = MagicLinkToken.metadata.tables["magic_link_token"]


@router.post(
    "/login",
    response_class=HTMLResponse,
    status_code=202,
    dependencies=[Depends(enforce_login_rate_limit)],
)
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


@router.get("/auth/verify", dependencies=[Depends(enforce_verify_rate_limit)])
def verify(
    token: str,
    session: SessionDep,
    settings: SettingsDep,
) -> RedirectResponse:
    """Consume a magic-link token and mint a signed session cookie.

    Atomic semantics: the UPDATE marks the token consumed AND returns
    the owning user_id in a single round-trip — no race window between
    "look up token" and "mark consumed."

    Failure modes (expired, already consumed, forged) all return the
    same 410 Gone response so an attacker can't probe to distinguish
    "this token was real but expired" from "this token was never valid."
    """
    token_hash = hashlib.sha256(token.encode("utf-8")).digest()
    now = datetime.now(UTC)

    stmt = (
        update(_TOKEN_TABLE)
        .where(
            _TOKEN_TABLE.c.token_hash == token_hash,
            _TOKEN_TABLE.c.consumed_at.is_(None),
            _TOKEN_TABLE.c.expires_at > now,
        )
        .values(consumed_at=now)
        .returning(_TOKEN_TABLE.c.user_id)
    )
    user_id = session.execute(stmt).scalar_one_or_none()

    if user_id is None:
        session.rollback()
        raise HTTPException(status_code=410, detail="Sign-in link expired or already used")

    session.commit()

    cookie_value = sign_session(user_id=user_id, secret=settings.session_secret)
    # Drop the freshly-signed-in user on the paste/upload page (the
    # actual app entry point), NOT the landing page. The landing page
    # also redirects authed visitors here, but going via `/` would
    # cause a needless second hop. See BUG-2 (#51).
    response = RedirectResponse(url="/passages/new", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=cookie_value,
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    return response


@router.get("/api/me")
def me(user: CurrentUser) -> dict[str, str]:
    """Return the signed-in user's id + email.

    The simplest possible auth-required endpoint. Useful for client-side
    "are we signed in?" checks and as the canonical test target for the
    `current_user` dependency.
    """
    return {"id": str(user.id), "email": user.email}
