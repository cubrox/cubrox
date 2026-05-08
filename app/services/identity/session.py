"""Session cookie sign + verify helpers + current_user dependency.

Per ADR-002 in docs/TECHNICAL-ARCHITECTURE.md, sessions are stored as
signed cookies — no server-side session table. The cookie payload is
deliberately minimal: just `user_id` and `issued_at`. The user's email
and any other PII is loaded from the DB on every request via the
`current_user` dependency below.

`itsdangerous.URLSafeTimedSerializer` does the signing. The serializer
is salted with a stable, version-tagged string so future cookie kinds
(CSRF, remember-me, etc.) can share the same SESSION_SECRET without
their tokens being interchangeable.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import Depends, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlmodel import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.models.user import User

SESSION_COOKIE_NAME = "session"
SESSION_SALT = "cubrox-session-cookie-v1"

# A cookie older than this gets re-issued with a fresh issued_at on the
# next authenticated request. The cookie's max_age stays at the full
# SESSION_TTL_DAYS — re-issue extends the user's effective session as
# long as they keep using Cubrox.
SESSION_REISSUE_AFTER_DAYS = 7


class UnauthenticatedError(Exception):
    """Raised by `current_user` when the request has no valid session.

    Caught by the app-level exception handler (in app/main.py), which
    converts it to either:
      - 303 redirect to /login (browser top-level navigation), or
      - 200 + HX-Redirect: /login (HTMX request — won't follow a normal
        303 because it intercepts the response before the browser does).
    """


def _serializer(secret: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key=secret, salt=SESSION_SALT)


def sign_session(*, user_id: uuid.UUID, secret: str) -> str:
    """Produce the signed cookie value for a user just signed in.

    Payload contains only `user_id` and `issued_at` — no email or other
    PII. The signature pins both values; tampering with either yields
    BadSignature on verification.
    """
    payload: dict[str, Any] = {
        "user_id": str(user_id),
        "issued_at": datetime.now(UTC).isoformat(),
    }
    return _serializer(secret).dumps(payload)


def verify_session(*, value: str, secret: str, max_age_seconds: int) -> dict[str, Any] | None:
    """Decode + verify a session cookie value.

    Returns the payload dict on success, or None on ANY failure
    (bad signature, expired, malformed). Callers should treat `None` as
    "unauthenticated" — same outcome as if no cookie was sent.
    """
    try:
        payload = _serializer(secret).loads(value, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def current_user(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    """FastAPI dependency that resolves the request's signed-in user.

    Reads the `session` cookie, verifies it, loads the User row, and
    returns the User. On ANY failure (no cookie, bad signature, expired
    cookie, user_id no longer exists in DB), raises
    `UnauthenticatedError` — which the app-level exception handler
    converts to the right redirect for browser vs. HTMX requests.

    Side effect: if the cookie is older than `SESSION_REISSUE_AFTER_DAYS`,
    schedules a fresh `Set-Cookie` on the response. The user's effective
    session extends as long as they keep using the app.

    Usage:
        from app.services.identity.session import current_user
        CurrentUser = Annotated[User, Depends(current_user)]

        @router.get("/protected")
        def view(user: CurrentUser): ...
    """
    cookie_value = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_value is None:
        raise UnauthenticatedError()

    max_age = settings.session_ttl_days * 86400
    payload = verify_session(
        value=cookie_value, secret=settings.session_secret, max_age_seconds=max_age
    )
    if payload is None:
        raise UnauthenticatedError()

    raw_user_id = payload.get("user_id")
    if not isinstance(raw_user_id, str):
        raise UnauthenticatedError()
    try:
        user_id = uuid.UUID(raw_user_id)
    except ValueError as exc:
        raise UnauthenticatedError() from exc

    user = session.get(User, user_id)
    if user is None:
        # The user_id in the cookie no longer exists in the DB (deleted
        # via psql admin, or the cookie was forged with a plausible
        # UUID). Treat as unauthenticated.
        raise UnauthenticatedError()

    # Rolling re-issue. Cheap to do every time we cross the 7-day mark.
    issued_at_str = payload.get("issued_at")
    if isinstance(issued_at_str, str):
        try:
            issued_at = datetime.fromisoformat(issued_at_str)
        except ValueError:
            issued_at = None
        if issued_at is not None:
            age = datetime.now(UTC) - issued_at
            if age > timedelta(days=SESSION_REISSUE_AFTER_DAYS):
                response.set_cookie(
                    key=SESSION_COOKIE_NAME,
                    value=sign_session(user_id=user.id, secret=settings.session_secret),
                    max_age=max_age,
                    httponly=True,
                    secure=settings.session_cookie_secure,
                    samesite="lax",
                )

    return user
