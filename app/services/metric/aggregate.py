"""Aggregate queries for the reading-event metric (METRIC-3 #23).

Backs the CLI in `app/scripts/metric.py`. Two queries, both push the
aggregation to the database — never iterate rows in Python:

  - `total_lines_since(date)`     → SUM(lines_processed)
  - `lines_per_day_since(date)`   → SUM(...) GROUP BY date(occurred_at)

The date truncation uses `sa.func.date(...)` rather than Postgres-only
`date_trunc('day', ...)`: both Postgres and SQLite ship a `date()`
function that extracts the date portion of a timestamp, so the same
SQL runs under the test SQLite engine. Return types differ (Postgres:
`date`; SQLite: ISO-8601 string) — `_to_date` normalizes.

No per-user breakdown by design (ticket guardrail B): the metric is
product-level. A Phase-2 dashboard can add per-user views if needed.
"""

from datetime import date

import sqlalchemy as sa
from sqlmodel import Session, select

from app.models.reading_event import ReadingEvent


def total_lines_since(session: Session, since: date) -> int:
    """Return the sum of `lines_processed` over all events on or after `since`.

    Single round-trip; returns 0 when no events match.
    """
    result = session.exec(
        select(sa.func.coalesce(sa.func.sum(ReadingEvent.lines_processed), 0)).where(  # type: ignore[arg-type]
            sa.func.date(ReadingEvent.occurred_at) >= since.isoformat()
        )
    ).one()
    return int(result)


def lines_per_day_since(session: Session, since: date) -> list[tuple[date, int]]:
    """Return one `(date, line_sum)` tuple per day with at least one event,
    ascending by date. Days with zero events are NOT padded — the caller
    formats sparse output as it sees fit.
    """
    day = sa.func.date(ReadingEvent.occurred_at).label("day")
    stmt = (
        select(day, sa.func.sum(ReadingEvent.lines_processed).label("total"))  # type: ignore[arg-type]
        .where(day >= since.isoformat())
        .group_by(day)
        .order_by(day.asc())
    )
    rows = session.exec(stmt).all()
    return [(_to_date(row[0]), int(row[1])) for row in rows]


def _to_date(value: date | str) -> date:
    """Postgres returns `date`; SQLite returns the ISO-8601 string form
    because `date()` there is a text function. Normalize both to `date`."""
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)
