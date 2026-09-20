"""US (NYSE) trading-day arithmetic for the platform health check.

Static holiday table — the API must not call a vendor to know what day
it is. Extend the table each December; a missing year degrades to
"weekdays only", which over-expects on holidays (a false 503 on a
holiday morning), never under-expects.
"""
from datetime import date, datetime, timedelta, timezone

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

# A session's data is DUE this many hours after 00:00 UTC of the next
# calendar day: the after-close run (22:00 UTC) has finished by ~00:30.
DUE_AFTER_UTC_HOUR = 1


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in NYSE_HOLIDAYS


def last_trading_day(now: datetime | None = None) -> date:
    """The most recent NYSE session whose after-close data is due."""
    now = now or datetime.now(timezone.utc)
    d = now.date()
    if now.hour < DUE_AFTER_UTC_HOUR:
        d -= timedelta(days=1)
    # Today's session is due only from tomorrow 01:00 UTC.
    d -= timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d
