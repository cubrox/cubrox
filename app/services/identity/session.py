"""Session cookie sign + verify helpers.

Per ADR-002 in docs/TECHNICAL-ARCHITECTURE.md, sessions are stored as
signed cookies — no server-side session table. The cookie payload is
deliberately minimal: just `user_id` and `issued_at`. The current user's
email and any other PII is loaded from the DB on every request via the
AUTH-3 dependency (next ticket).

`itsdangerous.URLSafeTimedSerializer` does the signing. The serializer
is salted with a stable, version-tagged string so future cookie kinds
(CSRF, remember-me, etc.) can share the same SESSION_SECRET without
their tokens being interchangeable.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SESSION_COOKIE_NAME = "session"
SESSION_SALT = "cubrox-session-cookie-v1"


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
