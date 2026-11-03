"""US (NYSE) trading-day arithmetic for the platform health check.

The holiday table and is_trading_day live in pipeline/trading_days.py (one
table for the whole platform, 2026-11-03). This module keeps the API's own
"when is a session's data due" rule.
"""
from datetime import date, datetime, timedelta, timezone

from pipeline.trading_days import NYSE_HOLIDAYS, is_trading_day  # noqa: F401

# A session's data is DUE this many hours after 00:00 UTC of the next
# calendar day: the after-close run (22:00 UTC) has finished by ~00:30.
DUE_AFTER_UTC_HOUR = 1


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
