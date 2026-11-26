"""US equity session helpers (NYSE regular hours, 09:30-16:00 America/New_York).

Exchange holidays are not modelled; see docs/TRADEOFFS.md.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
OPEN_T, CLOSE_T = time(9, 30), time(16, 0)
SESSION_MINUTES = 390


def session_state(now: datetime) -> str:
    local = now.astimezone(NY)
    if local.weekday() >= 5:
        return "CLOSED"
    t = local.time()
    if t < time(4, 0) or t >= time(20, 0):
        return "CLOSED"
    if t < OPEN_T:
        return "PRE_MARKET"
    if t < CLOSE_T:
        return "OPEN"
    return "AFTER_HOURS"


def session_fraction(ts: datetime) -> float:
    """Fraction of the regular session elapsed at `ts` (1.0 outside hours).

    Used to compare cumulative intraday volume with a full-day average.
    Floored at 0.1 so the first minutes of trading don't explode the ratio.
    """
    local = ts.astimezone(NY)
    if local.weekday() >= 5:
        return 1.0
    open_dt = local.replace(hour=9, minute=30, second=0, microsecond=0)
    close_dt = local.replace(hour=16, minute=0, second=0, microsecond=0)
    if local <= open_dt or local >= close_dt:
        return 1.0
    return max(0.1, (local - open_dt).total_seconds() / 60 / SESSION_MINUTES)


def last_close(now: datetime) -> datetime:
    local = now.astimezone(NY)
    candidate = local.replace(hour=16, minute=0, second=0, microsecond=0)
    if local < candidate:
        candidate -= timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate.astimezone(UTC)


def trading_days_between(start: datetime, end: datetime) -> float:
    """Approximate trading days elapsed (weekdays), at least 0."""
    if end <= start:
        return 0.0
    days = 0.0
    cur = start
    while cur < end:
        step = min(end, cur + timedelta(days=1))
        if cur.astimezone(NY).weekday() < 5:
            days += (step - cur).total_seconds() / 86400
        cur = step
    return days
