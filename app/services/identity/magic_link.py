"""Magic-link request flow.

Mints a one-time sign-in token, persists its SHA-256 hash, and schedules
the actual email send off-thread (so /login returns under 100 ms even when
Resend is slow). Per ADR-002 in docs/TECHNICAL-ARCHITECTURE.md.

The raw token is sent ONLY to the user's email and never persisted. The
hash is what we look up against on /auth/verify (next ticket, AUTH-2).
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import resend
from fastapi import BackgroundTasks
from sqlalchemy import delete
from sqlmodel import Session, select

from app.config import Settings
from app.models.magic_link_token import MagicLinkToken
from app.models.user import User

TOKEN_TTL_MINUTES = 15
TOKEN_BYTES = 32

# Table handle for Core-level delete: avoids mypy friction on the ORM-style
# `MagicLinkToken.user_id == ...` comparators (same pattern used in
# app/services/comprehension/cache.py).
_TOKEN_TABLE = MagicLinkToken.metadata.tables["magic_link_token"]


def request_magic_link(
    *,
    email: str,
    session: Session,
    settings: Settings,
    background_tasks: BackgroundTasks,
) -> None:
    """Mint a magic-link token for `email` and queue its email send.

    Always succeeds from the caller's perspective — even for unknown
    emails, we silently no-op past account creation. This keeps the
    /login response identical for known vs. unknown emails so an
    attacker can't enumerate registered users.
    """
    user = _find_or_create_user(email=email, session=session)

    raw_token = secrets.token_urlsafe(TOKEN_BYTES)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).digest()
    expires_at = datetime.now(UTC) + timedelta(minutes=TOKEN_TTL_MINUTES)

    # Single-active-token rule: any prior unconsumed token for this user
    # is invalidated by this request. Either the user lost the email and
    # is requesting again (replace) or they never wanted the prior one.
    session.execute(
        delete(_TOKEN_TABLE).where(
            _TOKEN_TABLE.c.user_id == user.id,
            _TOKEN_TABLE.c.consumed_at.is_(None),
        )
    )
    session.add(
        MagicLinkToken(
            token_hash=token_hash,
            user_id=user.id,
            expires_at=expires_at,
        )
    )
    session.commit()

    link = f"{settings.magic_link_base_url}/auth/verify?token={raw_token}"
    background_tasks.add_task(
        send_magic_link_email,
        email=email,
        link=link,
        from_email=settings.magic_link_from_email,
        api_key=settings.resend_api_key,
    )


def _find_or_create_user(*, email: str, session: Session) -> User:
    existing = session.exec(select(User).where(User.email == email)).first()
    if existing is not None:
        return existing
    user = User(email=email)
    session.add(user)
    session.flush()  # ensure user.id is populated for the FK below
    return user


def send_magic_link_email(
    *,
    email: str,
    link: str,
    from_email: str,
    api_key: str,
) -> None:
    """Production email sender via Resend. Tests monkey-patch this symbol.

    Module-level so tests can swap with `monkeypatch.setattr(magic_link,
    'send_magic_link_email', fake)` without touching the request_magic_link
    flow itself. This keeps the call site readable.
    """
    resend.api_key = api_key
    resend.Emails.send(
        {
            "from": from_email,
            "to": [email],
            "subject": "Sign in to Cubrox",
            "html": _build_html(link),
            "text": _build_text(link),
        }
    )


def _build_html(link: str) -> str:
    # Inline styles only — most email clients strip <style> blocks.
    return (
        '<div style="font-family: system-ui, sans-serif; line-height: 1.5;">'
        "<p>Click below to sign in to Cubrox.</p>"
        f'<p><a href="{link}" '
        'style="display:inline-block;padding:12px 20px;background:#1a73e8;'
        'color:#fff;text-decoration:none;border-radius:4px;">'
        "Sign in to Cubrox</a></p>"
        "<p>This link expires in 15 minutes. "
        "If you didn't request it, you can safely ignore this email.</p>"
        "</div>"
    )


def _build_text(link: str) -> str:
    return (
        "Sign in to Cubrox\n\n"
        f"{link}\n\n"
        "This link expires in 15 minutes. "
        "If you didn't request it, you can safely ignore this email."
    )
