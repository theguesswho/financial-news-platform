"""NYSE trading-day arithmetic shared by the pipeline and the API.

One holiday table for the whole platform (moved here from api/trading_days.py
on 2026-11-03, the evening-closes incident, so the price fetch, the freshness
sentinel and GET /health/platform agree on what "the last session" is).
Static table: nothing may call a vendor to know what day it is. Extend it
each December; a missing year degrades to "weekdays only", which
over-expects on a holiday (a false alarm), never under-expects.
"""
from datetime import date, datetime, time, timedelta, timezone

NYSE_HOLIDAYS = {
    # 2026
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
    date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
    date(2026, 11, 26), date(2026, 12, 25),
    # 2027
    date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26),
    date(2027, 5, 31), date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6),
    date(2027, 11, 25), date(2027, 12, 24),
}

# The 16:00 ET close plus a margin for the closing auction print to settle.
CLOSE_SETTLED_ET = time(16, 15)


def _nth_sunday(year: int, month: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(6 - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _ny_rule(now_utc: datetime) -> datetime:
    """US Eastern by rule (EDT from the 2nd Sunday of March 02:00 local to the
    1st Sunday of November 02:00 local), used if the tz database is missing."""
    y = now_utc.year
    start = datetime.combine(_nth_sunday(y, 3, 2), time(7), timezone.utc)    # 02:00 EST
    end = datetime.combine(_nth_sunday(y, 11, 1), time(6), timezone.utc)     # 02:00 EDT
    off = -4 if start <= now_utc < end else -5
    return now_utc.astimezone(timezone(timedelta(hours=off)))


try:  # the tz database ships with pandas (tzdata); the rule is the fallback, never a crash
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover - only on an image without tz data
    NY = None


def ny_time(now_utc: datetime) -> datetime:
    return now_utc.astimezone(NY) if NY is not None else _ny_rule(now_utc)


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in NYSE_HOLIDAYS


def previous_trading_day(d: date) -> date:
    d -= timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def last_closed_session(now: datetime | None = None) -> date:
    """The latest NYSE session whose close has happened, in New York time.
    22:00 UTC on a trading day -> that day; 06:00 UTC -> the session before."""
    now = (now or datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    ny = ny_time(now)
    d = ny.date()
    if not (is_trading_day(d) and ny.time() >= CLOSE_SETTLED_ET):
        d = previous_trading_day(d)
    return d


def yahoo_end(now: datetime | None = None) -> date:
    """Yahoo's `end` is EXCLUSIVE. Passing date.today() at 22:00 UTC cut off
    the session that had just closed: the evening board scored on the
    previous session's closes from 21 Sep to 3 Nov 2026 (DESK incident
    2026-11-03). Pass the day after the last closed session instead."""
    return last_closed_session(now) + timedelta(days=1)
