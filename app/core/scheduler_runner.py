from __future__ import annotations

from datetime import UTC, datetime


def get_scheduler_intervals(now: datetime | None = None) -> list[str]:
    """Return intervals to load for the current scheduler tick."""
    current = now or datetime.now(UTC)
    intervals: list[str] = ["15"]
    if current.minute == 0:
        intervals.append("60")
    if current.minute == 0 and current.hour % 4 == 0:
        intervals.append("240")
    if current.minute == 0 and current.hour == 0:
        intervals.append("D")
    return intervals
