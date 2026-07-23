"""Tests for POST /login (Supabase OTP magic-link flow).

Covers the Definition of Done for the rewritten route (SUPA-3 / #82):
  - Valid email → 202 + GENERIC_FRAGMENT, sign_in_with_otp called
    with the normalized email and an absolute callback URL
  - Malformed email → 422 (FastAPI validation via email-validator)
  - Email is lowercased + normalized before being handed to Supabase
  - The redirect_url uses X-Forwarded-* when present (Cloud Run path),
    falls back to settings.app_url otherwise (local-dev path)
  - Supabase upstream errors surface as 502 (not 500) so monitoring
    can tell server-side vs upstream failures apart
  - Supabase rate-limit errors (429 from the shared SMTP pool) are
    remapped to 429 with Retry-After (#247, from #245 postmortem)
    so HTMX + browsers can back off correctly and users see an
    actionable message instead of a generic 502

Rewritten in SUPA-5 (#84). The pre-SUPA-3 file tested Resend +
MagicLinkToken; that whole flow no longer exists.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


def test_valid_email_returns_202_and_generic_fragment(
    client: TestClient, supabase_mock: MagicMock
) -> None:
    response = client.post("/login", data={"email": "reader@example.com"})
    assert response.status_code == 202
    assert "Check your inbox" in response.text


def test_sign_in_with_otp_called_with_normalized_email(
    client: TestClient, supabase_mock: MagicMock
) -> None:
    """The route hands the email straight to Supabase. We pin the call
    args so a refactor can't accidentally drop the redirect URL or
    stop normalizing the email."""
    client.post("/login", data={"email": "Reader@Example.COM"})

    call = supabase_mock.auth.sign_in_with_otp.call_args
    assert call is not None, "sign_in_with_otp was never called"
    payload = call.args[0]
    assert payload["email"] == "reader@example.com"  # lowercased
    assert payload["options"]["email_redirect_to"].endswith("/auth/callback")


def test_malformed_email_returns_422(client: TestClient) -> None:
    """email-validator rejects "not-an-email" before we touch Supabase."""
    response = client.post("/login", data={"email": "not-an-email"})
    assert response.status_code == 422


def test_response_identical_for_known_and_unknown_email(
    client: TestClient, supabase_mock: MagicMock
) -> None:
    """No account enumeration. Both calls return the same fragment;
    Supabase handles user creation server-side."""
    response_known = client.post("/login", data={"email": "known@example.com"})
    response_unknown = client.post("/login", data={"email": "unknown@example.com"})
    assert response_known.status_code == 202
    assert response_unknown.status_code == 202
    assert response_known.text == response_unknown.text


def test_redirect_url_uses_x_forwarded_headers_when_present(
    client: TestClient, supabase_mock: MagicMock
) -> None:
    """Cloud Run / per Pattern #4. With X-Forwarded-* set, the redirect
    URL must be the public origin, not request.url."""
    client.post(
        "/login",
        data={"email": "reader@example.com"},
        headers={
            "x-forwarded-proto": "https",
            "x-forwarded-host": "pr-42---masterkey-xyz.run.app",
        },
    )
    call = supabase_mock.auth.sign_in_with_otp.call_args
    redirect = call.args[0]["options"]["email_redirect_to"]
    assert redirect == "https://pr-42---masterkey-xyz.run.app/auth/callback"


def test_supabase_rate_limit_returns_429_with_retry_after(
    client: TestClient, supabase_mock: MagicMock
) -> None:
    """When Supabase's shared SMTP pool 429s the OTP request (30/hr project-wide
    default), the app must return 429 with a Retry-After header and a user-
    facing message. Root-caused during #245 postmortem — the old catch-all
    Exception → 502 hid the rate limit for 20 minutes.

    Enumeration guard: message must NOT vary based on whether the email
    is registered — the 429 fires before any user-lookup happens.
    """
    from supabase_auth.errors import AuthApiError

    supabase_mock.auth.sign_in_with_otp.side_effect = AuthApiError(
        "email rate limit exceeded", 429, "over_email_send_rate_limit"
    )
    response = client.post("/login", data={"email": "reader@example.com"})
    assert response.status_code == 429
    assert response.headers.get("Retry-After") == "900"
    # HTML fragment, not JSON — HTMX response-targets ext (#250) swaps this
    # into #signin-form directly so the user sees the message.
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    assert "try again" in body.lower()
    # Fragment re-renders the sign-in form so the user can retry, AND carries
    # the response-targets wiring so a subsequent 429 also swaps back into
    # the form (not just the first one).
    assert 'id="signin-form"' in body
    assert 'hx-post="/login"' in body
    assert 'hx-target-4*="#signin-form"' in body


@pytest.mark.parametrize(
    "code",
    ["over_email_send_rate_limit", "over_sms_send_rate_limit", "over_request_rate_limit"],
)
def test_supabase_rate_limit_codes_return_429(
    client: TestClient, supabase_mock: MagicMock, code: str
) -> None:
    """Every rate-limit code on the RATE_LIMIT_CODES whitelist maps to 429.
    The old message-substring fallback was dropped in #252 — a hypothetical
    non-rate-limit error whose message happened to contain 'rate limit' should
    not be misclassified. This test pins the whitelist to keep future edits
    honest about what counts as rate-limited."""
    from supabase_auth.errors import AuthApiError

    supabase_mock.auth.sign_in_with_otp.side_effect = AuthApiError(
        "unrelated message text", 429, code
    )
    response = client.post("/login", data={"email": "reader@example.com"})
    assert response.status_code == 429


def test_supabase_rate_limit_message_only_no_code_returns_502(
    client: TestClient, supabase_mock: MagicMock
) -> None:
    """Regression guard for #252: an AuthApiError whose message contains
    'rate limit' but whose code is NOT on the whitelist must NOT be
    classified as 429. Before #252 this case was mapped to 429 via a
    message-substring fallback; that fallback was intentionally removed."""
    from supabase_auth.errors import AuthApiError

    supabase_mock.auth.sign_in_with_otp.side_effect = AuthApiError(
        "IP-level rate limit reached, check dashboard", 400, "unexpected_failure"
    )
    response = client.post("/login", data={"email": "reader@example.com"})
    assert response.status_code == 502


def test_supabase_non_rate_limit_authapierror_returns_502(
    client: TestClient, supabase_mock: MagicMock
) -> None:
    """Non-rate-limit Supabase errors (invalid_grant, unauthorized, etc.)
    still return 502 with the generic message — enumeration guard preserved."""
    from supabase_auth.errors import AuthApiError

    supabase_mock.auth.sign_in_with_otp.side_effect = AuthApiError(
        "invalid grant", 400, "invalid_grant"
    )
    response = client.post("/login", data={"email": "reader@example.com"})
    assert response.status_code == 502
    # #288: 502 now renders an HTML form fragment (not a JSON HTTPException) so
    # HTMX can swap a readable message in via hx-target-5*. The generic message
    # preserves the enumeration guard — Supabase's error text is never echoed.
    body = response.text
    assert '<form id="signin-form"' in body
    assert "temporarily unavailable" in body
    assert "invalid grant" not in body


def test_supabase_upstream_error_returns_502(client: TestClient, supabase_mock: MagicMock) -> None:
    """If Supabase raises (network, rate limit, etc.), surface a 502 so
    monitoring distinguishes upstream-failure from our-bug."""
    supabase_mock.auth.sign_in_with_otp.side_effect = RuntimeError("supabase down")
    response = client.post("/login", data={"email": "reader@example.com"})
    assert response.status_code == 502


# ---------------------------------------------------------------------------
# #288 — every /login error path renders a readable form fragment, not JSON
# ---------------------------------------------------------------------------


def test_malformed_email_renders_form_fragment_not_json(client: TestClient) -> None:
    """422 body is an HTML form fragment with a readable message, not a raw
    JSON HTTPException that HTMX would dump into #signin-form verbatim."""
    response = client.post("/login", data={"email": "not-an-email"})

    assert response.status_code == 422
    body = response.text
    assert '<form id="signin-form"' in body
    assert 'role="alert"' in body
    assert "valid email address" in body
    assert '{"detail"' not in body


def test_error_fragments_carry_both_4xx_and_5xx_targets(client: TestClient) -> None:
    """The re-rendered form must declare hx-target-5* as well as hx-target-4*,
    so a follow-up 5xx (502) also swaps back in rather than vanishing — the
    root cause of the '502 shows nothing' symptom."""
    body = client.post("/login", data={"email": "not-an-email"}).text

    assert 'hx-target-4*="#signin-form"' in body
    assert 'hx-target-5*="#signin-form"' in body


def test_local_rate_limit_renders_fragment_with_retry_after(client: TestClient) -> None:
    """Exhaust the local 10/hour bucket from one IP, then confirm the 429 is a
    readable fragment (not JSON) that keeps Retry-After and does not echo the
    email (leak guard)."""
    ip = "203.0.113.55"
    email = "loop@example.com"
    last = None
    for _ in range(11):
        last = client.post(
            "/login",
            data={"email": email},
            headers={"X-Forwarded-For": ip},
        )

    assert last is not None
    assert last.status_code == 429
    body = last.text
    assert '<form id="signin-form"' in body
    assert 'role="alert"' in body
    assert "wait a few minutes" in body
    assert '{"detail"' not in body
    assert "Retry-After" in last.headers
    # Enumeration / leak guard: the rate-limited email must not appear.
    assert email not in body
