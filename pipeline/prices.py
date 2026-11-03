"""
Price data pipeline using yfinance (Yahoo Finance).

Free, no API key, batches all tickers in one network round-trip.

Session cut-off (DESK incident 2026-11-03): Yahoo's `end` is EXCLUSIVE.
This module used `end=date.today()`, which at the 22:00 UTC after-close is
the session that had just closed, so the evening board scored on the
PREVIOUS session's closes from 21 Sep (when Yahoo became the only price
writer) to 3 Nov 2026. `end` now comes from pipeline.trading_days: the day
after the last session that has closed in New York, and no row dated after
that session is ever stored (no partial "today" bar from an early run).

Writes are set-based upserts on (symbol, date):
  * every row in the window is inserted when missing — holes inside the
    window are filled (the old per-row flush + rollback discarded a
    symbol's earlier new rows whenever a later row already existed);
  * rows of the latest `refresh_sessions` sessions in the download are
    OVERWRITTEN when Yahoo's values differ. The 06:00 run passes 2, so a
    close stored at 22:00 (late prints, auction corrections, dividend
    re-basing) is corrected the next morning. The evening run passes 0.
"""
from datetime import datetime, timedelta

import yfinance as yf
from sqlalchemy import literal_column
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from db.models import EodPrice
from pipeline.trading_days import last_closed_session

_CHUNK = 1000


def _num(v, dp=4):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else round(f, dp)   # NaN -> None


def _rows_from_download(raw, symbols: list[str], last_session) -> list[dict]:
    """Flatten yfinance's frame into eod_prices rows; skip NaN closes and any
    date after the last closed session."""
    if raw is None or raw.empty:
        return []
    multi = hasattr(raw.columns, "levels")
    available = raw["Close"].columns.tolist() if multi else symbols[:1]
    out = []
    for sym in available:
        try:
            col = (lambda f: raw[f][sym]) if multi else (lambda f: raw[f])
            close, open_, high, low, vol = (col("Close"), col("Open"), col("High"),
                                            col("Low"), col("Volume"))
            for dt in raw.index:
                d = dt.date() if hasattr(dt, "date") else dt
                if d > last_session:
                    continue
                c = _num(close.get(dt))
                if c is None:
                    continue
                v = vol.get(dt)
                out.append({"symbol": sym, "date": d, "close": c,
                            "open": _num(open_.get(dt)), "high": _num(high.get(dt)),
                            "low": _num(low.get(dt)),
                            "volume": int(v) if v is not None and v == v else None})
        except Exception as exc:  # one bad symbol never sinks the batch
            print(f"  {sym}: {exc}")
    return out


def store_price_rows(session: Session, rows: list[dict], refresh_dates=frozenset()) -> dict:
    """Upsert rows. Missing (symbol, date) -> insert. Existing -> kept, unless
    the date is in refresh_dates and Yahoo's values differ -> overwritten.
    Returns {"added", "corrected"}."""
    t = EodPrice.__table__
    added = corrected = 0
    keep = [r for r in rows if r["date"] not in refresh_dates]
    fresh = [r for r in rows if r["date"] in refresh_dates]
    for i in range(0, len(keep), _CHUNK):
        stmt = (pg_insert(t).values(keep[i:i + _CHUNK])
                .on_conflict_do_nothing(index_elements=["symbol", "date"])
                .returning(t.c.id))
        added += len(session.execute(stmt).fetchall())
        session.commit()
    for i in range(0, len(fresh), _CHUNK):
        ins = pg_insert(t).values(fresh[i:i + _CHUNK])
        ex = ins.excluded
        stmt = (ins.on_conflict_do_update(
                    index_elements=["symbol", "date"],
                    set_={"open": ex.open, "high": ex.high, "low": ex.low,
                          "close": ex.close, "volume": ex.volume},
                    where=(t.c.open.is_distinct_from(ex.open) | t.c.high.is_distinct_from(ex.high)
                           | t.c.low.is_distinct_from(ex.low) | t.c.close.is_distinct_from(ex.close)
                           | t.c.volume.is_distinct_from(ex.volume)))
                .returning(literal_column("(xmax = 0)").label("inserted")))
        for (inserted,) in session.execute(stmt).fetchall():
            if inserted:
                added += 1
            else:
                corrected += 1
        session.commit()
    return {"added": added, "corrected": corrected}


def fetch_prices(session: Session, symbols: list[str], days: int = 90,
                 refresh_sessions: int = 0, now: datetime | None = None) -> dict:
    """
    Download EOD prices for `symbols` in one batched yfinance call, up to and
    including the last NYSE session that has closed, and upsert them into
    eod_prices. `refresh_sessions` > 0 overwrites the latest N sessions of
    the download when Yahoo's values changed (the 06:00 run uses 2).
    """
    if not symbols:
        return {"added": 0, "corrected": 0, "symbols": 0}

    last = last_closed_session(now)
    end = last + timedelta(days=1)          # Yahoo `end` is exclusive
    start = end - timedelta(days=days)

    print(f"Downloading prices for {len(symbols)} symbols via yfinance, "
          f"{start} .. {last} (end={end}, exclusive)...")
    raw = yf.download(
        tickers=symbols,
        start=start.isoformat(),
        end=end.isoformat(),
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    rows = _rows_from_download(raw, symbols, last)
    if not rows:
        print("No price data returned.")
        return {"added": 0, "corrected": 0, "symbols": 0, "last_session": last.isoformat(),
                "session_names": 0}

    refresh = set(sorted({r["date"] for r in rows})[-refresh_sessions:]) if refresh_sessions else set()
    res = store_price_rows(session, rows, frozenset(refresh))
    out = {**res,
           "symbols": len({r["symbol"] for r in rows}),
           "last_session": last.isoformat(),
           "session_names": sum(1 for r in rows if r["date"] == last),
           "refreshed": sorted(d.isoformat() for d in refresh)}
    print(f"Done. {res['added']:,} added, {res['corrected']:,} corrected; "
          f"{out['session_names']} names have the {last} close.")
    return out
