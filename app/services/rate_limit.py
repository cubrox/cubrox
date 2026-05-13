"""Token-bucket rate limiting for /login and /auth/verify.

Per ADR — Postgres-backed bucket (Redis when traffic justifies). 10
tokens per hour, linear refill. Two buckets per request, both must
have ≥1 token after refill:

  /login:        ("login:ip:<ip>",        "login:email:<email>")
  /auth/verify:  ("verify:ip:<ip>",       "verify:token-prefix:<8hex>")

The IP key blocks the easy spam-from-one-IP attack. The secondary key
blocks the distributed-IPs-targeting-one-victim attack (email bomb a
specific address; brute-force a specific token prefix).

Logging discipline: we never log raw emails. Rate-limit hits log
`route` + 16-hex-char SHA-256 prefix of the email so support can
correlate without leaking PII into Cloud Logging.

Concurrency: the SELECT uses `with_for_update()` so on Postgres, two
concurrent workers can't both read the same `tokens` value and clobber
each other's decrement. SQLite (in tests) silently ignores the lock
hint, which is fine — the test session is single-threaded. The
first-touch INSERT is handled separately in `_take_token` (catches
`IntegrityError`, recurses once into the locked-update path).
"""

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.db import get_session
from app.models.rate_bucket import RateBucket

logger = logging.getLogger(__name__)

# Bucket physics. 10 tokens max, refilled linearly at 10/hour.
BUCKET_SIZE = 10.0
SECONDS_PER_TOKEN = 3600.0 / BUCKET_SIZE  # 360 s/token


def _now_utc() -> datetime:
    """Wall clock. Indirected through a function so tests can override
    it via `monkeypatch.setattr('app.services.rate_limit._now_utc', ...)`.
    """
    return datetime.now(UTC)


def _hash_email(email: str) -> str:
    """First 16 hex chars of SHA-256(email). Enough for correlation in
    Cloud Logging without storing the raw address."""
    return hashlib.sha256(email.encode("utf-8")).hexdigest()[:16]


def _client_ip(request: Request) -> str:
    """Real client IP, accounting for Cloud Run's proxy hop.

    Cloud Run strips any upstream `X-Forwarded-For` entries the client
    set, then appends the true client IP as the LAST entry. So we read
    the last comma-separated value, not the first. Falls back to
    `request.client.host` for local-dev / test environments where no
    proxy header is present.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        # Last entry is the one Cloud Run set; entries before it may be
        # client-supplied lies.
        return xff.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


@dataclass(frozen=True)
class BucketResult:
    """Outcome of a single bucket check after refill."""

    allowed: bool
    tokens_remaining: float
    seconds_until_next_token: float


def _take_token(session: Session, key: str, now: datetime) -> BucketResult:
    """Atomically refill + decrement one bucket.

    On Postgres, the SELECT uses `FOR UPDATE` so two concurrent workers
    can't both read the same `tokens` value, decrement, and clobber each
    other's write. SQLite (in tests) silently drops the lock hint — the
    test session is single-threaded so this is fine.

    First-touch INSERT is a separate race: two concurrent first-ever
    requests for the same key both miss the SELECT, both attempt INSERT,
    one wins, the other hits `IntegrityError`. We catch and recurse
    once — by then the row exists and the FOR-UPDATE path is taken.

    Returns the outcome. Caller is responsible for committing the
    session if all buckets in the request succeed, or rolling back if
    any fails.
    """
    stmt = select(RateBucket).where(RateBucket.key == key).with_for_update()
    bucket = session.exec(stmt).first()

    if bucket is None:
        # First touch: start with a full bucket, immediately decrement one.
        # If another request races us to INSERT, the unique-PK constraint
        # fires; we retry once, and the second pass takes the locked-update
        # path.
        bucket = RateBucket(key=key, tokens=BUCKET_SIZE - 1.0, refilled_at=now)
        session.add(bucket)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            return _take_token(session, key, now)
        return BucketResult(
            allowed=True,
            tokens_remaining=BUCKET_SIZE - 1.0,
            seconds_until_next_token=SECONDS_PER_TOKEN,
        )

    # Refill: tokens accrued since refilled_at, capped at BUCKET_SIZE.
    last_refill = bucket.refilled_at
    if last_refill.tzinfo is None:
        # SQLite drops tzinfo on round-trip; treat naive timestamps as UTC.
        last_refill = last_refill.replace(tzinfo=UTC)
    elapsed = max(0.0, (now - last_refill).total_seconds())
    accrued = elapsed / SECONDS_PER_TOKEN
    tokens_after_refill = min(BUCKET_SIZE, bucket.tokens + accrued)

    if tokens_after_refill < 1.0:
        # Not enough; persist the refill but DON'T decrement.
        bucket.tokens = tokens_after_refill
        bucket.refilled_at = now
        seconds_until_one = (1.0 - tokens_after_refill) * SECONDS_PER_TOKEN
        return BucketResult(
            allowed=False,
            tokens_remaining=tokens_after_refill,
            seconds_until_next_token=seconds_until_one,
        )

    bucket.tokens = tokens_after_refill - 1.0
    bucket.refilled_at = now
    return BucketResult(
        allowed=True,
        tokens_remaining=bucket.tokens,
        seconds_until_next_token=SECONDS_PER_TOKEN,
    )


def _enforce(
    session: Session,
    keys: tuple[str, ...],
    *,
    route: str,
    email_hash: str | None,
) -> None:
    """Run `_take_token` over every key. If any bucket fails, raise 429
    with the longest `Retry-After` across the failed buckets.

    On any failure we roll back so the partial decrements don't take
    effect — otherwise a request that fails the second check would
    cost a token on the first key.
    """
    now = _now_utc()
    results = [(k, _take_token(session, k, now)) for k in keys]

    if all(r.allowed for _, r in results):
        session.commit()
        return

    session.rollback()
    retry_after = int(max(r.seconds_until_next_token for _, r in results if not r.allowed))
    # Clamp to at least 1 so clients don't loop instantly.
    retry_after = max(1, retry_after)
    logger.warning(
        "rate_limit.hit route=%s email_hash=%s retry_after_s=%s",
        route,
        email_hash or "-",
        retry_after,
    )
    raise HTTPException(
        status_code=429,
        detail="Too many requests. Try again later.",
        headers={"Retry-After": str(retry_after)},
    )


SessionDep = Annotated[Session, Depends(get_session)]


async def enforce_login_rate_limit(
    request: Request,
    session: SessionDep,
) -> None:
    """FastAPI dependency for POST /login.

    Extracts the IP and the form-submitted `email` field. Both buckets
    must have ≥1 token; otherwise the request is rejected with 429.
    """
    ip = _client_ip(request)
    # Read the email out of the form body. FastAPI's form parsing has
    # already cached the body by the time this dependency runs, so the
    # downstream route reading `email: Form()` doesn't re-read.
    form = await request.form()
    raw_email = form.get("email")
    if not isinstance(raw_email, str) or not raw_email:
        # No email supplied — the route's own Form validation will 422
        # this. Don't burn a token on malformed input.
        return
    email_norm = raw_email.strip().lower()

    _enforce(
        session,
        keys=(f"login:ip:{ip}", f"login:email:{email_norm}"),
        route="login",
        email_hash=_hash_email(email_norm),
    )


def enforce_verify_rate_limit(
    request: Request,
    session: SessionDep,
    token: str = "",
) -> None:
    """FastAPI dependency for GET /auth/verify.

    Secondary key uses the SHA-256 prefix of the token rather than the
    raw token so the rate_bucket table never stores token material.
    """
    ip = _client_ip(request)
    if not token:
        # No token in the URL — the verify route will 410. Don't burn
        # a bucket entry on a malformed request.
        return
    token_prefix = hashlib.sha256(token.encode("utf-8")).hexdigest()[:8]

    _enforce(
        session,
        keys=(f"verify:ip:{ip}", f"verify:token-prefix:{token_prefix}"),
        route="verify",
        email_hash=None,
    )


# Convenience type aliases — useful only for tests / introspection.
TimeSource = Callable[[], datetime]
