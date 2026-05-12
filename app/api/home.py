"""Landing-page route.

GET / renders the Cubrox landing page with a sign-in form. The form
posts to /login (AUTH-1) via HTMX, so a successful submit swaps the
form for the "check your inbox" fragment without a page reload.

Public route — no authentication required. This is the only URL on
the site a person can find without already being signed in.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.templates import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def landing(request: Request) -> HTMLResponse:
    """Render the landing page with the sign-in form."""
    return templates.TemplateResponse(request=request, name="home.html")
