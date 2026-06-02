"""CLI: print reading-event totals (METRIC-3 #23).

Run with:
    uv run python -m app.scripts.metric
    uv run python -m app.scripts.metric --since 2026-08-01

Default `--since` is 90 days ago. Output is plain text: a single-line
running total followed by a date-sorted per-day table. No UI, no HTTP
endpoint, no per-user breakdown — this is the release-decision tool,
not a dashboard.

The script reads from the same `DATABASE_URL` the FastAPI app uses;
running it against a Supabase branch needs the branch's URL exported.
"""

import argparse
import sys
from datetime import UTC, date, datetime, timedelta

from sqlmodel import Session

from app.db import engine
from app.services.metric.aggregate import lines_per_day_since, total_lines_since

DEFAULT_LOOKBACK_DAYS = 90


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="cubrox-metric",
        description="Print reading-event totals since a given date.",
    )
    parser.add_argument(
        "--since",
        default=None,
        help=(
            "Earliest event date to include, in YYYY-MM-DD format. "
            f"Defaults to {DEFAULT_LOOKBACK_DAYS} days ago."
        ),
    )
    return parser.parse_args(argv)


def _resolve_since(raw: str | None) -> date:
    if raw is None:
        return (datetime.now(UTC) - timedelta(days=DEFAULT_LOOKBACK_DAYS)).date()
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        # Re-raise with a friendlier message; the CLI wrapper turns this
        # into a non-zero exit + stderr line.
        raise SystemExit(f"error: --since must be YYYY-MM-DD (got {raw!r}): {exc}") from exc


def _format_report(since: date, total: int, per_day: list[tuple[date, int]]) -> str:
    header = f"Lines processed since {since.isoformat()}: {total:,}"
    underline = " " * (len(header) - len(f"{total:,}")) + "─" * len(f"{total:,}")

    lines = [header, underline, "", "Date         Lines"]
    for day, count in per_day:
        lines.append(f"{day.isoformat()}   {count:,}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    since = _resolve_since(args.since)

    with Session(engine) as session:
        total = total_lines_since(session, since)
        per_day = lines_per_day_since(session, since)

    print(_format_report(since, total, per_day))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
