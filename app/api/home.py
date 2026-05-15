"""Landing-page route.

GET / serves two audiences in one URL:

  - **Anonymous visitors** see the Cubrox landing page with the
    sign-in form. The form posts to /login (AUTH-1) via HTMX, so a
    successful submit swaps the form for the "check your inbox"
    fragment without a page reload.

  - **Already-signed-in visitors** are redirected straight to
    /passages/new (the paste/upload entry point). Without this branch,
    a returning user clicking a bookmarked URL would land on the
    sign-in form and assume the page was broken — see BUG-2 (#51).

Public route in the sense that it doesn't REQUIRE authentication; the
soft-auth `try_current_user` dependency returns `None` rather than
raising when no valid session is present.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response

from app.models.user import User
from app.services.identity.session import try_current_user
from app.templates import templates

router = APIRouter()

OptionalUser = Annotated[User | None, Depends(try_current_user)]


@router.get("/")
def landing(request: Request, user: OptionalUser) -> Response:
    """Render the landing page for anonymous visitors; redirect
    signed-in visitors to the paste/upload page."""
    if user is not None:
        # Already signed in: skip the sign-in form, drop them on the
        # actual app entry point. 303 matches the post-verify redirect.
        return RedirectResponse(url="/passages/new", status_code=303)
    return templates.TemplateResponse(request=request, name="home.html")
