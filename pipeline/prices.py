"""
Price data pipeline using yfinance (Yahoo Finance).

Free, no API key, batches all tickers in one network round-trip.
498 tickers × 90 days ≈ 30 seconds.
"""
from datetime import date, timedelta

import yfinance as yf
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models import EodPrice


def fetch_prices(session: Session, symbols: list[str], days: int = 90) -> dict:
    """
    Download EOD prices for all symbols in one batched yfinance call.
    Upserts into eod_prices table. Skips existing records.
    """
    if not symbols:
        return {"added": 0, "symbols": 0}

    end = date.today()
    start = end - timedelta(days=days)

    print(f"Downloading {days}-day prices for {len(symbols)} symbols via yfinance...")

    # Single batched download — yfinance handles chunking internally
    raw = yf.download(
        tickers=symbols,
        start=start.isoformat(),
        end=end.isoformat(),
        auto_adjust=True,
        progress=False,
        threads=True,
    )

    if raw.empty:
        print("No price data returned.")
        return {"added": 0, "symbols": 0}

    # yfinance returns MultiIndex columns: (OHLCV, symbol) when >1 ticker
    added = 0
    symbols_with_data = 0

    # Normalise to a per-symbol dict of DataFrames
    if isinstance(raw.columns, type(raw.columns)) and hasattr(raw.columns, "levels"):
        # MultiIndex: columns are (field, symbol)
        available = raw["Close"].columns.tolist()
    else:
        # Single ticker returned flat columns
        available = symbols[:1]

    for sym in available:
        try:
            if len(available) == 1 and sym == available[0]:
                close_col = raw["Close"] if "Close" in raw.columns else raw.iloc[:, 3]
                open_col  = raw["Open"]  if "Open"  in raw.columns else None
                high_col  = raw["High"]  if "High"  in raw.columns else None
                low_col   = raw["Low"]   if "Low"   in raw.columns else None
                vol_col   = raw["Volume"] if "Volume" in raw.columns else None
                dates = raw.index
            else:
                close_col = raw["Close"][sym]
                open_col  = raw["Open"][sym]  if "Open"  in raw.columns.get_level_values(0) else None
                high_col  = raw["High"][sym]  if "High"  in raw.columns.get_level_values(0) else None
                low_col   = raw["Low"][sym]   if "Low"   in raw.columns.get_level_values(0) else None
                vol_col   = raw["Volume"][sym] if "Volume" in raw.columns.get_level_values(0) else None
                dates = raw.index

            sym_added = 0
            for dt in dates:
                close_val = close_col.get(dt) if hasattr(close_col, "get") else close_col[dt]
                if close_val is None or (hasattr(close_val, "__float__") and close_val != close_val):
                    continue  # NaN
                try:
                    price_date = dt.date() if hasattr(dt, "date") else dt
                    record = EodPrice(
                        symbol=sym,
                        date=price_date,
                        close=round(float(close_val), 4),
                        open=round(float(open_col[dt]), 4) if open_col is not None else None,
                        high=round(float(high_col[dt]), 4) if high_col is not None else None,
                        low=round(float(low_col[dt]),  4) if low_col  is not None else None,
                        volume=int(vol_col[dt]) if vol_col is not None and vol_col[dt] == vol_col[dt] else None,
                    )
                    session.add(record)
                    session.flush()
                    sym_added += 1
                except IntegrityError:
                    session.rollback()  # already exists
                except Exception:
                    session.rollback()

            if sym_added:
                session.commit()
                added += sym_added
                symbols_with_data += 1

        except Exception as exc:
            session.rollback()
            print(f"  {sym}: {exc}")

    print(f"Done. {added:,} price records added across {symbols_with_data} symbols.")
    return {"added": added, "symbols": symbols_with_data}
