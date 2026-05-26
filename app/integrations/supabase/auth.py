"""Supabase-backed authentication helpers.

The `current_user` / `try_current_user` FastAPI dependencies and the
`UnauthenticatedError` exception that signals auth failure to
`app/main.py`'s handler. After SUPA-2c (#91) this is the single source
of identity — the legacy itsdangerous cookie path was deleted along
with the User SQLModel + MagicLinkToken table.

`current_user` returns an `AuthenticatedUser` dataclass — a thin
adapter over the raw Supabase user object that normalizes `.id` from
the Supabase string-UUID shape to a real `uuid.UUID` instance. Without
the normalization, SQLModel `table=True` fields with `uuid.UUID` type
silently accept strings at construction time, then SQLAlchemy's UUID
column type crashes on `.hex` access at INSERT — surfacing to the
user as a 500. See #103.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from app.integrations.supabase.client import anon_client

SUPABASE_COOKIE_NAME = "sb-access-token"


class UnauthenticatedError(Exception):
    """Raised by `current_user` when the request has no valid Supabase session.

    Caught by the app-level exception handler in `app/main.py`, which
    converts it to either:
      - 303 redirect to `/` (browser top-level navigation), or
      - 200 + `HX-Redirect: /` header (HTMX request)
    """


@dataclass(frozen=True)
class AuthenticatedUser:
    """App-facing identity object with normalized types.

    Wraps the raw `gotrue.types.User` returned by Supabase, exposing
    only the two attributes the rest of the app reads (`.id`, `.email`)
    and forcing `.id` to a `uuid.UUID` instance (Supabase returns a
    string). The route handlers' SQLModel writes depend on this — see
    module docstring for the failure mode this prevents.
    """

    id: uuid.UUID
    email: str


def current_user(request: Request) -> AuthenticatedUser:
    """FastAPI dependency that resolves the request's Supabase user.

    Reads the `sb-access-token` cookie, validates it via Supabase
    Auth, and returns an `AuthenticatedUser` with `.id` coerced to
    `uuid.UUID`. Raises `UnauthenticatedError` on any failure (no
    cookie, invalid token, Supabase unreachable).
    """
    sb_token = request.cookies.get(SUPABASE_COOKIE_NAME)
    if not sb_token:
        raise UnauthenticatedError()
    try:
        resp = anon_client().auth.get_user(sb_token)
    except Exception as exc:
        raise UnauthenticatedError() from exc
    if resp is None or resp.user is None:
        raise UnauthenticatedError()
    sb_user = resp.user
    return AuthenticatedUser(
        id=uuid.UUID(str(sb_user.id)),
        email=sb_user.email or "",
    )


def try_current_user(request: Request) -> AuthenticatedUser | None:
    """Soft-auth variant: returns `None` instead of raising on failure.

    Used by routes that render differently for signed-in vs anonymous
    visitors but shouldn't trigger the AUTH-3 redirect for anonymous
    ones (e.g. the landing page renders the sign-in form for None
    users and redirects authed visitors away).
    """
    try:
        return current_user(request)
    except UnauthenticatedError:
        return None


# Re-export Depends-annotated aliases for convenience at call sites.
CurrentUser = Annotated[AuthenticatedUser, Depends(current_user)]
OptionalUser = Annotated[AuthenticatedUser | None, Depends(try_current_user)]
