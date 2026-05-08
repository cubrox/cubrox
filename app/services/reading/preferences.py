"""Preference write helpers.

`upsert_preference` is the single write path into the `preference` table.
It enforces:
  - read-modify-write (so the user's other preferences are preserved)
  - "no write if the value is unchanged" short-circuit (avoids spurious
    UPDATEs when the user clicks the same button twice)
  - ATTRIBUTE.flag_modified so SQLAlchemy detects the in-place dict edit

Per-key + per-value validation against PREFERENCE_OPTIONS happens at the
route layer; this helper trusts its inputs.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import attributes
from sqlmodel import Session

from app.models.preference import Preference


def upsert_preference(
    *,
    user_id: UUID,
    key: str,
    value: Any,
    session: Session,
) -> bool:
    """Set `key`=`value` in the user's preferences. Returns True if a
    write actually happened, False if the value was already what was
    requested (the short-circuit case).

    The caller is responsible for committing the session.
    """
    existing = session.get(Preference, user_id)

    if existing is None:
        session.add(
            Preference(
                user_id=user_id,
                values={key: value},
                updated_at=datetime.now(UTC),
            )
        )
        return True

    if existing.values.get(key) == value:
        # No-op short-circuit. User clicked the same button twice; don't
        # waste a write. The route still re-renders the fragment so the
        # client sees the right state.
        return False

    # Merge into the existing dict. Build a NEW dict (not mutating in
    # place) — clearer for SQLAlchemy change tracking and for any
    # future caller that captured a reference to the old dict.
    new_values = {**existing.values, key: value}
    existing.values = new_values
    existing.updated_at = datetime.now(UTC)
    # Belt and braces: SQLAlchemy's JSON-column change detection is
    # finicky on in-place dict edits. Even though we did `existing.values
    # = new_values` (which is a re-assignment, not a mutation), some
    # ORM configurations require explicit notification.
    attributes.flag_modified(existing, "values")
    return True
