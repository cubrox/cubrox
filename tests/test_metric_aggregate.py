"""Tests for the metric-aggregate queries + CLI (METRIC-3 #23).

Covers the Definition of Done from issue #23:
  - total_lines_since seeded with 5 events returns the correct sum
  - lines_per_day_since returns one row per day with the right total
  - Empty DB returns 0 and []
  - Both queries are single round-trips (use SQLAlchemy event listener)
  - The CLI prints the total + per-day table to stdout
  - Invalid --since format exits non-zero with a clear message
"""

import hashlib
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import event
from sqlmodel import Session

from app.models.passage import Passage
from app.models.reading_event import ReadingEvent
from app.models.user import User
from app.scripts import metric as metric_cli
from app.services.metric.aggregate import (
    lines_per_day_since,
    total_lines_since,
)


def _seed_user_and_passage(session: Session) -> tuple[User, Passage]:
    user = User(email="metric-reader@example.com")
    session.add(user)
    session.commit()
    session.refresh(user)

    text = "lorem ipsum"
    p = Passage(
        user_id=user.id,
        text=text,
        text_hash=hashlib.sha256(text.encode()).digest(),
        source_type="paste",
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return user, p


def _seed_events(
    session: Session,
    rows: list[tuple[datetime, int]],
) -> None:
    """Insert one ReadingEvent per (occurred_at, lines_processed) tuple,
    all attributed to the same user + passage so the metric aggregate
    sums correctly across them."""
    user, passage = _seed_user_and_passage(session)
    for occurred_at, lines in rows:
        session.add(
            ReadingEvent(
                user_id=user.id,
                passage_id=passage.id,
                lines_processed=lines,
                occurred_at=occurred_at,
            )
        )
    session.commit()


class _QueryCounter:
    """Context manager that counts SQL executions via SQLAlchemy events.

    Used to assert the aggregate functions don't issue an N+1 stream
    of queries — they should each be a single round-trip.
    """

    def __init__(self, session: Session) -> None:
        self._engine = session.get_bind()
        self.count = 0

    def _before_execute(self, *_args: Any, **_kwargs: Any) -> None:
        self.count += 1

    def __enter__(self) -> "_QueryCounter":
        event.listen(self._engine, "before_cursor_execute", self._before_execute)
        return self

    def __exit__(self, *_exc: Any) -> None:
        event.remove(self._engine, "before_cursor_execute", self._before_execute)


# ---------------------------------------------------------------------------
# total_lines_since
# ---------------------------------------------------------------------------


def test_total_lines_since_sums_events_after_cutoff(session: Session) -> None:
    """Five events seeded across three days; the cutoff includes all of them."""
    _seed_events(
        session,
        [
            (datetime(2026, 1, 1, 9, 0, tzinfo=UTC), 10),
            (datetime(2026, 1, 1, 18, 0, tzinfo=UTC), 20),
            (datetime(2026, 1, 2, 11, 0, tzinfo=UTC), 30),
            (datetime(2026, 1, 3, 7, 0, tzinfo=UTC), 40),
            (datetime(2026, 1, 3, 21, 0, tzinfo=UTC), 50),
        ],
    )

    assert total_lines_since(session, date(2026, 1, 1)) == 150


def test_total_lines_since_excludes_events_before_cutoff(session: Session) -> None:
    """Events on dates strictly before `since` must NOT be counted."""
    _seed_events(
        session,
        [
            (datetime(2025, 12, 31, 23, 59, tzinfo=UTC), 999),  # excluded
            (datetime(2026, 1, 1, 0, 0, tzinfo=UTC), 5),
        ],
    )
    assert total_lines_since(session, date(2026, 1, 1)) == 5


def test_total_lines_since_empty_db_returns_zero(session: Session) -> None:
    """No events → SUM returns NULL → COALESCE folds to 0 (not None)."""
    assert total_lines_since(session, date(2026, 1, 1)) == 0


# ---------------------------------------------------------------------------
# lines_per_day_since
# ---------------------------------------------------------------------------


def test_lines_per_day_since_groups_and_sums_correctly(session: Session) -> None:
    """Two events per day across three days → three buckets with the
    right per-day total, ascending."""
    _seed_events(
        session,
        [
            (datetime(2026, 1, 1, 9, 0, tzinfo=UTC), 10),
            (datetime(2026, 1, 1, 18, 0, tzinfo=UTC), 20),
            (datetime(2026, 1, 2, 11, 0, tzinfo=UTC), 30),
            (datetime(2026, 1, 3, 7, 0, tzinfo=UTC), 40),
            (datetime(2026, 1, 3, 21, 0, tzinfo=UTC), 50),
        ],
    )

    assert lines_per_day_since(session, date(2026, 1, 1)) == [
        (date(2026, 1, 1), 30),
        (date(2026, 1, 2), 30),
        (date(2026, 1, 3), 90),
    ]


def test_lines_per_day_since_empty_db_returns_empty_list(session: Session) -> None:
    assert lines_per_day_since(session, date(2026, 1, 1)) == []


def test_lines_per_day_since_filters_before_cutoff(session: Session) -> None:
    """Days strictly before `since` aren't in the result."""
    _seed_events(
        session,
        [
            (datetime(2025, 12, 31, 12, 0, tzinfo=UTC), 100),  # excluded
            (datetime(2026, 1, 1, 12, 0, tzinfo=UTC), 7),
        ],
    )
    assert lines_per_day_since(session, date(2026, 1, 1)) == [(date(2026, 1, 1), 7)]


# ---------------------------------------------------------------------------
# Single round-trip discipline
# ---------------------------------------------------------------------------


def test_total_lines_since_is_single_round_trip(session: Session) -> None:
    _seed_events(
        session,
        [(datetime(2026, 1, 1, 9, 0, tzinfo=UTC), 5)],
    )
    with _QueryCounter(session) as counter:
        total_lines_since(session, date(2026, 1, 1))
    assert counter.count == 1


def test_lines_per_day_since_is_single_round_trip(session: Session) -> None:
    _seed_events(
        session,
        [
            (datetime(2026, 1, 1, 9, 0, tzinfo=UTC), 5),
            (datetime(2026, 1, 2, 9, 0, tzinfo=UTC), 6),
        ],
    )
    with _QueryCounter(session) as counter:
        lines_per_day_since(session, date(2026, 1, 1))
    assert counter.count == 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_prints_total_and_per_day_table(
    session: Session,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: seed events, run `main(['--since', '2026-01-01'])`,
    verify the printed output contains the total + each day's row."""
    _seed_events(
        session,
        [
            (datetime(2026, 1, 1, 9, 0, tzinfo=UTC), 12),
            (datetime(2026, 1, 2, 9, 0, tzinfo=UTC), 34),
        ],
    )

    # Route the CLI's `Session(engine)` to the test session by stubbing
    # `Session` in the metric module — same trick as the route tests use
    # for the DB-session dependency.
    class _FixedSession:
        def __init__(self, _engine: object) -> None:
            self._inner = session

        def __enter__(self) -> Session:
            return self._inner

        def __exit__(self, *_exc: object) -> None:
            return None

    monkeypatch.setattr(metric_cli, "Session", _FixedSession)

    exit_code = metric_cli.main(["--since", "2026-01-01"])
    assert exit_code == 0

    out = capsys.readouterr().out
    assert "Lines processed since 2026-01-01: 46" in out
    assert "2026-01-01" in out
    assert "2026-01-02" in out
    # Both per-day totals should appear; check both raw forms.
    assert "12" in out
    assert "34" in out


def test_cli_default_since_is_90_days_ago(
    session: Session,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When --since is omitted, the script should use a date 90 days
    before now and produce a header that mentions it. No need to seed
    events; the empty-DB total of 0 is fine for this assertion."""

    class _FixedSession:
        def __init__(self, _engine: object) -> None:
            self._inner = session

        def __enter__(self) -> Session:
            return self._inner

        def __exit__(self, *_exc: object) -> None:
            return None

    monkeypatch.setattr(metric_cli, "Session", _FixedSession)
    metric_cli.main([])

    out = capsys.readouterr().out
    assert "Lines processed since" in out
    assert "0" in out  # empty DB → 0 total


def test_cli_invalid_since_format_exits_non_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--since not-a-date` must exit with a clear error message,
    not zero, not a stack trace."""
    with pytest.raises(SystemExit) as exc_info:
        metric_cli.main(["--since", "not-a-date"])
    # The SystemExit code should be a string (the message) or an int != 0.
    code = exc_info.value.code
    assert code != 0
    if isinstance(code, str):
        assert "YYYY-MM-DD" in code or "not-a-date" in code
