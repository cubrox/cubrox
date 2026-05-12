"""Tests for the public landing page at GET /.

This is the ONLY public page on Cubrox — it must work without
authentication and serve as the on-ramp to the magic-link sign-in
flow (AUTH-1/2/3).
"""

import pytest
from fastapi.testclient import TestClient

from app.services.identity import magic_link


@pytest.fixture(autouse=True)
def stub_email_sender(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the real Resend dispatch with a no-op.

    The signin-form-submits-to-/login test exercises the real /login
    route, which would otherwise call Resend with the (unset) test
    API key. Stub it out the same way test_auth_login.py does.
    """
    monkeypatch.setattr(
        magic_link,
        "send_magic_link_email",
        lambda **_: None,
    )


def test_landing_page_returns_200_and_html(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_landing_page_does_not_require_auth(client: TestClient) -> None:
    """The landing page is the only public URL. Unauthenticated requests
    must NOT redirect to /login (that would be a redirect loop, since
    /login is where someone gets the form to sign in from)."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 200
    assert response.headers.get("location") is None


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


def test_landing_page_mentions_cubrox(client: TestClient) -> None:
    """Basic branding sanity check — visiting the URL should make it
    obvious you're looking at Cubrox, not the starter template's todo
    demo."""
    body = client.get("/").text
    assert "Cubrox" in body


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
    success fragment from AUTH-1. This pins the template-route contract
    (the form's action target must match the route's expected method
    and field name)."""
    response = client.post(
        "/login",
        data={"email": "reader@example.com"},
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )
    assert response.status_code == 202
    assert "Check your inbox" in response.text
