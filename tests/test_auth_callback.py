"""Tests for GET /auth/callback (Supabase JWT exchange).

Replaces the old /auth/verify tests. The two-stage flow:

  Stage 1: GET /auth/callback (no query params) → tiny HTML page with
    JS that reads the URL hash fragment (Supabase puts the JWT there
    where the browser doesn't send it to the server) and redirects to
    stage 2 with the tokens as query params.

  Stage 2: GET /auth/callback?access_token=… → validate via Supabase
    auth.get_user(token), set the sb-access-token HttpOnly cookie,
    303 to /passages/new.

Rewritten in SUPA-5 (#84) from the pre-SUPA-3 test_auth_verify.py
which tested the deleted itsdangerous flow.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient


def test_stage1_no_params_renders_hash_extractor_html(
    client: TestClient,
) -> None:
    """First hit lands on /auth/callback with #access_token=… in the
    URL hash. The browser doesn't send the hash to the server, so we
    serve a tiny JS page that reads window.location.hash and redirects
    to stage 2 with the token as a query param."""
    response = client.get("/auth/callback", follow_redirects=False)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    # The JS bridge that converts hash → query params is the whole point.
    assert "window.location.hash" in body
    assert "/auth/callback" in body
    # A11Y-4 (#121): the bridge is hand-built HTML (not via base.html),
    # so it must declare its language itself — axe flags a missing
    # `lang` as a serious WCAG 2.0 A (html-has-lang) violation.
    assert '<html lang="en">' in body


def test_stage2_valid_token_sets_cookie_and_redirects(
    client: TestClient, supabase_mock: MagicMock
) -> None:
    """A valid Supabase JWT in the query param → 303 to /passages/new
    with sb-access-token cookie set."""
    fake_user = SimpleNamespace(id="00000000-0000-0000-0000-000000000001", email="r@example.com")
    supabase_mock.auth.get_user.return_value = SimpleNamespace(user=fake_user)

    response = client.get("/auth/callback?access_token=valid-jwt-token", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/passages/new"
    assert response.cookies.get("sb-access-token") == "valid-jwt-token"


def test_stage2_invalid_token_returns_410(client: TestClient, supabase_mock: MagicMock) -> None:
    """Supabase says no user → 410 Gone. Same shape as the old
    /auth/verify failure mode so existing 4xx monitoring stays
    consistent."""
    supabase_mock.auth.get_user.return_value = SimpleNamespace(user=None)
    response = client.get("/auth/callback?access_token=expired-or-forged", follow_redirects=False)
    assert response.status_code == 410


def test_stage2_supabase_raise_returns_410(client: TestClient, supabase_mock: MagicMock) -> None:
    """If supabase-py raises (network, malformed JWT) we treat it the
    same as 'no user' — the user can't sign in either way."""
    supabase_mock.auth.get_user.side_effect = RuntimeError("network")
    response = client.get("/auth/callback?access_token=garbage", follow_redirects=False)
    assert response.status_code == 410


def test_cookie_is_httponly_and_samesite_lax(client: TestClient, supabase_mock: MagicMock) -> None:
    """Cookie attributes that actually matter for the security model.
    Secure-flag depends on settings.session_cookie_secure which is
    True by default (production) — TestClient may strip Secure on
    plain-HTTP requests, so we check it from the raw Set-Cookie
    header instead of the parsed cookies jar."""
    fake_user = SimpleNamespace(id="00000000-0000-0000-0000-000000000002", email="r@example.com")
    supabase_mock.auth.get_user.return_value = SimpleNamespace(user=fake_user)

    response = client.get("/auth/callback?access_token=valid", follow_redirects=False)
    set_cookie = response.headers.get("set-cookie", "")
    assert "sb-access-token=valid" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie.replace(" ", "")


def test_cookie_max_age_is_seven_days(client: TestClient, supabase_mock: MagicMock) -> None:
    """7 days = 604800 seconds. Pinned because changing this without
    thought has UX consequences (sudden re-login wave)."""
    fake_user = SimpleNamespace(id="00000000-0000-0000-0000-000000000003", email="r@example.com")
    supabase_mock.auth.get_user.return_value = SimpleNamespace(user=fake_user)

    response = client.get("/auth/callback?access_token=valid", follow_redirects=False)
    set_cookie = response.headers.get("set-cookie", "")
    assert "Max-Age=604800" in set_cookie
