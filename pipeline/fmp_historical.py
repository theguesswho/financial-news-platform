"""
FMP Historical Metrics pipeline.

Fetches 20 quarters of key financial metrics per stock from Financial Modeling Prep.
This gives us clean, pre-calculated historical ratios (PE, ROIC, EV/EBITDA, etc.)
that are accurate as of each quarter-end — no reconstruction needed.

Cost: 2 API calls per symbol (key-metrics + income-statement).
With a paid FMP subscription: unlimited calls, 20+ quarters of history.
"""
import os
import time
from datetime import date, datetime

import requests
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from db.models import HistoricalMetrics

FMP_BASE = "https://financialmodelingprep.com/api/v3"
FMP_KEY = os.getenv("FMP_API_KEY", "")
QUARTERS = 20   # how many quarters to fetch per symbol


def _get(endpoint: str) -> list:
    url = f"{FMP_BASE}/{endpoint}&apikey={FMP_KEY}"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and "Error Message" in data:
        raise ValueError(data["Error Message"])
    return data if isinstance(data, list) else []


def _safe(val, cast=float):
    try:
        return cast(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def fetch_historical_metrics(session: Session, symbols: list[str]) -> dict:
    """Fetch and store FMP historical metrics for all symbols."""

    # Create table via raw SQL if needed (avoids SQLAlchemy create_all complexity)
    from sqlalchemy import text
    session.execute(text("""
        CREATE TABLE IF NOT EXISTS historical_metrics (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10) NOT NULL,
            date DATE NOT NULL,
            pe_ratio NUMERIC(12,4),
            pfcf_ratio NUMERIC(12,4),
            ev_to_ebitda NUMERIC(12,4),
            price_to_book NUMERIC(12,4),
            ev_to_fcf NUMERIC(12,4),
            roic NUMERIC(10,6),
            roe NUMERIC(10,6),
            gross_margin NUMERIC(10,6),
            operating_margin NUMERIC(10,6),
            net_margin NUMERIC(10,6),
            interest_coverage NUMERIC(10,2),
            debt_to_equity NUMERIC(10,4),
            current_ratio NUMERIC(10,4),
            revenue NUMERIC(20,0),
            net_income NUMERIC(20,0),
            gross_profit NUMERIC(20,0),
            operating_income NUMERIC(20,0),
            market_cap NUMERIC(20,0),
            CONSTRAINT _hm_symbol_date_uc UNIQUE (symbol, date)
        )
    """))
    session.execute(text("CREATE INDEX IF NOT EXISTS ix_hm_symbol ON historical_metrics (symbol)"))
    session.commit()

    stored = 0
    errors = 0

    for i, sym in enumerate(symbols, 1):
        try:
            print(f"  [{i}/{len(symbols)}] {sym}...", end=" ", flush=True)

            # Fetch key metrics and income statement in parallel
            metrics = _get(f"key-metrics/{sym}?period=quarter&limit={QUARTERS}")
            income  = _get(f"income-statement/{sym}?period=quarter&limit={QUARTERS}")

            # Build income lookup by date
            inc_by_date = {row["date"]: row for row in income}

            rows = []
            for m in metrics:
                dt = m.get("date")
                if not dt:
                    continue
                inc = inc_by_date.get(dt, {})

                # Gross margin from income statement (more reliable than key-metrics)
                rev = _safe(inc.get("revenue"), int)
                gp  = _safe(inc.get("grossProfit"), int)
                gm  = round(gp / rev, 6) if rev and gp else None
                om  = _safe(inc.get("operatingIncomeRatio"))
                nm  = _safe(inc.get("netIncomeRatio"))

                rows.append({
                    "symbol":           sym,
                    "date":             datetime.strptime(dt, "%Y-%m-%d").date(),
                    "pe_ratio":         _safe(m.get("peRatio")),
                    "pfcf_ratio":       _safe(m.get("pfcfRatio")),
                    "ev_to_ebitda":     _safe(m.get("enterpriseValueOverEBITDA")),
                    "price_to_book":    _safe(m.get("pbRatio")),
                    "ev_to_fcf":        _safe(m.get("evToFreeCashFlow")),
                    "roic":             _safe(m.get("roic")),
                    "roe":              _safe(m.get("roe")),
                    "gross_margin":     gm,
                    "operating_margin": om,
                    "net_margin":       nm,
                    "interest_coverage": _safe(m.get("interestCoverage")),
                    # FMP also returns debtToEquity as a percentage — divide by 100
                    "debt_to_equity":   round(_safe(m.get("debtToEquity")) / 100, 4) if _safe(m.get("debtToEquity")) is not None else None,
                    "current_ratio":    _safe(m.get("currentRatio")),
                    "revenue":          rev,
                    "net_income":       _safe(inc.get("netIncome"), int),
                    "gross_profit":     gp,
                    "operating_income": _safe(inc.get("operatingIncome"), int),
                    "market_cap":       _safe(m.get("marketCap"), int),
                })

            if rows:
                stmt = pg_insert(HistoricalMetrics).values(rows).on_conflict_do_nothing(
                    index_elements=["symbol", "date"]
                )
                result = session.execute(stmt)
                session.commit()
                stored += result.rowcount
                print(f"{len(rows)} quarters stored (back to {rows[-1]['date']})")
            else:
                print("no data")

            time.sleep(0.2)   # polite to FMP

        except Exception as exc:
            errors += 1
            print(f"error: {exc}")
            session.rollback()

    print(f"\nFMP historical fetch complete: {stored} rows stored, {errors} errors.")
    return {"stored": stored, "errors": errors}
