"""Tests for AUTH-4 rate limiting on /login and /auth/verify.

Covers the Definition of Done from issue #12:
  - 10 requests succeed from the same IP, 11th returns 429
  - Different IPs are independently bucketed
  - Same email from different IPs is bucketed by email (10 total)
  - Retry-After header value is between 1 and 3600
  - Bucket refills linearly over time
  - 429 response carries Retry-After and does NOT echo the email
  - Rate-limit log line hashes the email rather than logging it raw
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.services import rate_limit
from app.services.identity import magic_link


@pytest.fixture(autouse=True)
def stub_email_sender(monkeypatch: pytest.MonkeyPatch) -> None:
    """/login dispatches an email on the happy path; mute that side effect."""
    monkeypatch.setattr(magic_link, "send_magic_link_email", lambda **_: None)


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> dict[str, datetime]:
    """Replace `rate_limit._now_utc` with a controllable wall clock.

    Tests advance the clock by mutating `fake_clock["now"]`. The
    rate-limit service reads the latest value on every call.
    """
    state = {"now": datetime(2026, 5, 12, 12, 0, 0, tzinfo=UTC)}
    monkeypatch.setattr(rate_limit, "_now_utc", lambda: state["now"])
    return state


def _post_login(client: TestClient, email: str, ip: str) -> int:
    """Helper: POST /login with a fake client IP via X-Forwarded-For.

    Returns the HTTP status code so the caller can drive a quick loop.
    Cloud Run appends the real client IP as the LAST entry; we mimic
    that here.
    """
    response = client.post(
        "/login",
        data={"email": email},
        headers={"X-Forwarded-For": f"10.0.0.1, {ip}"},
    )
    return response.status_code


# ---------------------------------------------------------------------------
# IP bucket
# ---------------------------------------------------------------------------


def test_ten_requests_from_same_ip_then_429_on_eleventh(
    client: TestClient, fake_clock: dict[str, datetime]
) -> None:
    """The IP bucket exhausts at 10. The 11th request must 429 even
    though each request uses a different email (so the email buckets
    are all untouched)."""
    for i in range(10):
        code = _post_login(client, f"user{i}@example.com", "203.0.113.7")
        assert code == 202, f"request {i + 1} should succeed; got {code}"

    code = _post_login(client, "user99@example.com", "203.0.113.7")
    assert code == 429


def test_different_ips_are_independently_bucketed(
    client: TestClient, fake_clock: dict[str, datetime]
) -> None:
    """An attacker exhausting one IP must not lock out other IPs."""
    # First IP burns its 10.
    for i in range(10):
        assert _post_login(client, f"a{i}@example.com", "203.0.113.7") == 202
    assert _post_login(client, "a99@example.com", "203.0.113.7") == 429

    # Second IP starts fresh.
    assert _post_login(client, "b0@example.com", "203.0.113.8") == 202


# ---------------------------------------------------------------------------
# Email bucket (cross-IP defense — the email-bomb scenario)
# ---------------------------------------------------------------------------


def test_same_email_across_different_ips_is_bucketed_by_email(
    client: TestClient, fake_clock: dict[str, datetime]
) -> None:
    """Spammer rotates IPs to target one address. The email bucket
    catches them at 10 total across all IPs."""
    victim = "victim@example.com"
    for i in range(10):
        # Each request a new IP — IP buckets all stay fresh.
        ip = f"198.51.100.{i + 1}"
        assert _post_login(client, victim, ip) == 202, f"request {i + 1} should succeed"

    # 11th from yet another IP should be email-rate-limited.
    assert _post_login(client, victim, "198.51.100.99") == 429


# ---------------------------------------------------------------------------
# Retry-After + response shape
# ---------------------------------------------------------------------------


def test_429_includes_retry_after_within_plausible_range(
    client: TestClient, fake_clock: dict[str, datetime]
) -> None:
    """`Retry-After` is in seconds and must be between 1 and 3600
    (one hour is the full-bucket refill window)."""
    for _ in range(10):
        _post_login(client, "x@example.com", "203.0.113.7")
    response = client.post(
        "/login",
        data={"email": "x@example.com"},
        headers={"X-Forwarded-For": "10.0.0.1, 203.0.113.7"},
    )
    assert response.status_code == 429
    retry_after = int(response.headers["retry-after"])
    assert 1 <= retry_after <= 3600


def test_429_body_does_not_leak_the_email(
    client: TestClient, fake_clock: dict[str, datetime]
) -> None:
    """The 429 response body must not echo the rate-limited email — a
    response that bounces the address back can be used to confirm an
    address is being hammered."""
    sensitive = "person.confidential@example.com"
    for _ in range(10):
        _post_login(client, sensitive, "203.0.113.7")
    response = client.post(
        "/login",
        data={"email": sensitive},
        headers={"X-Forwarded-For": "10.0.0.1, 203.0.113.7"},
    )
    assert response.status_code == 429
    assert sensitive not in response.text
    assert "confidential" not in response.text.lower()


# ---------------------------------------------------------------------------
# Linear refill
# ---------------------------------------------------------------------------


def test_bucket_refills_one_token_after_six_minutes(
    client: TestClient, fake_clock: dict[str, datetime]
) -> None:
    """Linear refill: 10 tokens/hour = 1 token per 360 seconds.
    Burn the bucket, advance 6 minutes and 1 second, one more request
    should land."""
    for _ in range(10):
        _post_login(client, "z@example.com", "203.0.113.7")
    assert _post_login(client, "z@example.com", "203.0.113.7") == 429

    # Advance just over 6 minutes — enough for one full token.
    fake_clock["now"] = fake_clock["now"] + timedelta(seconds=361)
    assert _post_login(client, "z@example.com", "203.0.113.7") == 202

    # Immediately again: bucket is back to <1, expect 429.
    assert _post_login(client, "z@example.com", "203.0.113.7") == 429


# ---------------------------------------------------------------------------
# PII discipline
# ---------------------------------------------------------------------------


def test_rate_limit_log_hashes_the_email(
    client: TestClient,
    fake_clock: dict[str, datetime],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The WARN log line on a 429 must NEVER contain the raw email — it
    should carry a short SHA-256 prefix instead. We capture the WARN
    calls by patching the bound `logger.warning` method directly,
    which is robust against caplog's full-suite quirks (see the
    2026-05-11 session journal for the rationale)."""
    sensitive = "secret-user@example.com"
    warn_calls: list[tuple[str, tuple]] = []

    def fake_warning(msg: str, *args: object) -> None:
        warn_calls.append((msg, args))

    monkeypatch.setattr(rate_limit.logger, "warning", fake_warning)

    # Drive a 429.
    for _ in range(10):
        _post_login(client, sensitive, "203.0.113.7")
    _post_login(client, sensitive, "203.0.113.7")

    assert warn_calls, "expected at least one rate-limit warning log"
    for msg, args in warn_calls:
        rendered = (msg % args) if args else msg
        assert sensitive not in rendered
        assert "secret-user" not in rendered

    # The hash prefix must appear so support can correlate.
    import hashlib

    expected_prefix = hashlib.sha256(sensitive.encode("utf-8")).hexdigest()[:16]
    assert any(expected_prefix in ((msg % args) if args else msg) for msg, args in warn_calls)


# ---------------------------------------------------------------------------
# /auth/verify — bucketed by IP and token-prefix
# ---------------------------------------------------------------------------


def test_verify_route_rate_limits_by_ip(
    client: TestClient, fake_clock: dict[str, datetime]
) -> None:
    """Hammering /auth/verify with different tokens from one IP still
    burns the IP bucket. The 11th request 429s even though every token
    so far has been distinct (so the per-token-prefix buckets are
    fresh)."""
    for i in range(10):
        response = client.get(
            "/auth/verify",
            params={"token": f"token-{i:02d}-abcdef"},
            headers={"X-Forwarded-For": "10.0.0.1, 203.0.113.9"},
            follow_redirects=False,
        )
        # Token is fake → expect 410, NOT 429. The point is the bucket
        # decremented.
        assert response.status_code == 410, f"request {i + 1}: got {response.status_code}"

    response = client.get(
        "/auth/verify",
        params={"token": "token-99-abcdef"},
        headers={"X-Forwarded-For": "10.0.0.1, 203.0.113.9"},
        follow_redirects=False,
    )
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) >= 1
