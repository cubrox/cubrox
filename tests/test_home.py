"""Tests for the landing page at GET /.

The route serves two audiences:
  - Anonymous visitors see the sign-in form (the on-ramp to AUTH-1/2/3).
  - Signed-in visitors are redirected to /passages/new — the actual app
    entry point. Without this branch, a returning user clicking a
    bookmarked URL would land on the sign-in form and assume the page
    was broken (BUG-2 #51).

Tests in this file that don't seed a session cookie exercise the
anonymous path; the dedicated `test_signed_in_visitor_redirects_to_passages_new`
test exercises the signed-in branch.
"""

from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.conftest import signed_in


def test_landing_page_returns_200_and_html(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_landing_page_does_not_require_auth(client: TestClient) -> None:
    """The landing page is the public URL anonymous visitors see first.
    A request with no session cookie must render the sign-in form (200),
    NOT redirect anywhere — there's nowhere safe to redirect them to
    (the sign-in form lives ON this page)."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 200
    assert response.headers.get("location") is None


def test_signed_in_visitor_redirects_to_passages_new(
    client: TestClient,
    session: Session,
) -> None:
    """Per BUG-2 (#51): a signed-in visitor should skip the landing page
    and land directly on the paste/upload entry point. Without this,
    returning users clicking bookmarked `/` see the sign-in form and
    assume the site is broken."""
    signed_in(session, email="returning@example.com")

    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/passages/new"
    # Critically, we did NOT render the sign-in form.
    assert "<form" not in response.text


def test_unauthenticated_visitor_sees_signin_form(
    client: TestClient,
) -> None:
    """An anonymous visitor (no auth) sees the sign-in form, not a 4xx.
    The soft-auth `try_current_user` dep returns None for any verify
    failure, and the landing page renders the form for None users."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 200
    # Sign-in form rendered; no redirect.
    assert response.headers.get("location") is None
    assert "<form" in response.text


def test_landing_page_renders_signin_form(client: TestClient) -> None:
    """The form is the whole point of this page — without it, a user has
    no way to get into the product."""
    response = client.get("/")
    body = response.text

    assert "<form" in body
    # Form has an email input.
    assert "<input" in body
    assert 'type="email"' in body
    assert 'name="email"' in body
    # Form submits to /login.
    assert 'hx-post="/login"' in body


def test_landing_page_signin_form_swaps_inline(client: TestClient) -> None:
    """The form uses HTMX outerHTML swap so the success message replaces
    the form in place — no full-page reload. Pin this so a future
    refactor can't accidentally drop the swap config."""
    body = client.get("/").text

    assert 'hx-target="#signin-form"' in body
    assert 'hx-swap="outerHTML"' in body
    # The form's id is the swap target.
    assert 'id="signin-form"' in body


def test_landing_page_mentions_product_name(client: TestClient) -> None:
    """Basic branding sanity check — visiting the URL should make it
    obvious you're looking at Master Key (the public product name),
    not the starter template's todo demo. 'Cubrox' remains the
    internal codebase identifier (repo name, package name) but is
    no longer surfaced to users."""
    body = client.get("/").text
    assert "Master Key" in body


def test_landing_page_includes_master_key_epigraph(client: TestClient) -> None:
    """The Bahá'u'lláh quote that gives the product its name is the
    branding anchor for the landing page — pin both the quote text
    and the attribution so a future refactor can't silently drop the
    context behind the name."""
    body = client.get("/").text
    # Quote substring (chosen to be distinctive but not so long that
    # a minor punctuation tweak would break the test).
    assert "master key for the whole world" in body
    # Attribution — visible to the visitor.
    assert "Bahá'u'lláh" in body
    # Rendered as a semantic blockquote, not inline body copy.
    assert "<blockquote" in body
    assert 'class="master-key-epigraph"' in body


def test_landing_page_does_not_mention_todos(client: TestClient) -> None:
    """The todo demo was the starter scaffolding. Make sure no leftover
    text bleeds through into the landing page."""
    body = client.get("/").text.lower()
    assert "todo" not in body


def test_landing_page_email_input_has_html5_validation(client: TestClient) -> None:
    """`required` and `type='email'` give the browser a free first pass
    at input validation before the form even submits. Pin both."""
    body = client.get("/").text
    assert "required" in body
    assert 'autocomplete="email"' in body


def test_signin_form_submission_returns_check_inbox_fragment(
    client: TestClient,
) -> None:
    """End-to-end smoke: posting the form's value to /login returns the
    success fragment. The conftest's autouse Supabase stub makes
    sign_in_with_otp a no-op so this doesn't hit the network."""
    response = client.post(
        "/login",
        data={"email": "reader@example.com"},
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )
    assert response.status_code == 202
    assert "Check your inbox" in response.text
