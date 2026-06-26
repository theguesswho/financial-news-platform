"""
Fundamentals pipeline — fetches financial ratios and quarterly trends via yfinance.

Calculates:
  Valuation  : P/E, forward P/E, PEG, P/Book, P/FCF, EV/EBITDA, EV/FCF
  Quality    : ROE, ROIC (approx), gross/operating/net/FCF margins
  Balance    : Debt/Equity, current ratio, interest coverage
  Growth     : Revenue, earnings, FCF growth YoY
  Trends     : Last 8 quarters of revenue, margins, FCF (for trajectory analysis)

Free via Yahoo Finance. ~8-12 min for 500 symbols.
"""
import json
import time
from datetime import datetime
from typing import Optional

import numpy as np
import yfinance as yf
from sqlalchemy.orm import Session

from db.models import Fundamentals


def _safe(val) -> Optional[float]:
    """Return float or None, handling NaN/inf."""
    try:
        f = float(val)
        return None if (f != f or abs(f) > 1e15) else f  # NaN or absurd
    except Exception:
        return None


def _pct(val) -> Optional[float]:
    v = _safe(val)
    return round(v, 6) if v is not None else None


def _quarterly_trends(ticker: yf.Ticker) -> dict:
    """
    Extract last 8 quarters of key financials for trend analysis.
    Returns dict of lists (oldest → newest).
    """
    try:
        fin = ticker.quarterly_income_stmt
        cf  = ticker.quarterly_cashflow
    except Exception:
        return {}

    if fin is None or fin.empty:
        return {}

    # Columns are dates newest-first; reverse so oldest-first
    fin = fin.iloc[:, :8].iloc[:, ::-1]

    def row(df, *names):
        for n in names:
            matches = [c for c in df.index if n.lower() in c.lower()]
            if matches:
                vals = df.loc[matches[0]]
                return [_safe(v) for v in vals]
        return []

    revenue   = row(fin, "Total Revenue", "Revenue")
    gross_p   = row(fin, "Gross Profit")
    op_inc    = row(fin, "Operating Income", "EBIT")
    net_inc   = row(fin, "Net Income")
    dates     = [str(c)[:10] for c in fin.columns]

    # FCF = Operating CF - CapEx
    fcf_list = []
    if cf is not None and not cf.empty:
        cf_aligned = cf.iloc[:, :8].iloc[:, ::-1]
        op_cf  = row(cf_aligned, "Operating Cash Flow", "Cash From Operations")
        capex  = row(cf_aligned, "Capital Expenditure", "Purchase Of PPE")
        if op_cf and capex:
            fcf_list = [
                (_safe(o) - abs(_safe(c) or 0)) if _safe(o) is not None else None
                for o, c in zip(op_cf, capex)
            ]

    # Gross margin trend
    gm_list = []
    if revenue and gross_p:
        for r, g in zip(revenue, gross_p):
            gm_list.append(round(g / r, 4) if r and g else None)

    # Operating margin trend
    om_list = []
    if revenue and op_inc:
        for r, o in zip(revenue, op_inc):
            om_list.append(round(o / r, 4) if r and o else None)

    return {
        "dates":            dates,
        "revenue":          revenue,
        "gross_margin":     gm_list,
        "operating_margin": om_list,
        "net_income":       net_inc,
        "fcf":              fcf_list,
    }


def _ttm_margins(ticker: yf.Ticker) -> dict:
    """
    Calculate TTM (Trailing Twelve Months) margins from last 4 quarters.
    More current than FY figures since it includes latest Q data.
    Returns dict with: gross_margin, operating_margin, net_margin
    """
    try:
        fin = ticker.quarterly_income_stmt
        if fin is None or fin.empty:
            return {}

        # Get last 4 quarters (newest first, so slice [:4] and reverse)
        fin_ttm = fin.iloc[:, :4].iloc[:, ::-1]

        def sum_row(df, *names):
            """Find and sum a row by name"""
            for n in names:
                matches = [c for c in df.index if n.lower() in c.lower()]
                if matches:
                    vals = [_safe(v) for v in df.loc[matches[0]]]
                    return sum([v for v in vals if v is not None])
            return None

        # Sum last 4 quarters
        revenue_ttm = sum_row(fin_ttm, "Total Revenue", "Revenue")
        gross_profit_ttm = sum_row(fin_ttm, "Gross Profit")
        op_inc_ttm = sum_row(fin_ttm, "Operating Income", "EBIT")
        net_inc_ttm = sum_row(fin_ttm, "Net Income")

        # Calculate TTM margins
        result = {}
        if revenue_ttm and revenue_ttm > 0:
            if gross_profit_ttm:
                result["gross_margin"] = round(gross_profit_ttm / revenue_ttm, 4)
            if op_inc_ttm is not None:
                result["operating_margin"] = round(op_inc_ttm / revenue_ttm, 4)
            if net_inc_ttm:
                result["net_margin"] = round(net_inc_ttm / revenue_ttm, 4)

        return result
    except Exception:
        return {}


def _yoy_growth(trends: dict, key: str) -> Optional[float]:
    """YoY growth from quarterly trends (Q vs Q-4)."""
    series = [v for v in trends.get(key, []) if v is not None]
    if len(series) >= 5:
        curr, prior = series[-1], series[-5]
        if prior and prior != 0:
            return round((curr - prior) / abs(prior), 4)
    return None


def fetch_fundamentals(session: Session, symbols: list[str]) -> dict:
    """
    Fetch and store fundamentals for all symbols.
    Skips symbols updated within the last 7 days unless forced.
    """
    from sqlalchemy import text
    # Create table if needed
    session.execute(text("""
        CREATE TABLE IF NOT EXISTS fundamentals (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10) UNIQUE NOT NULL,
            fetched_at TIMESTAMP,
            pe_trailing NUMERIC(12,2), pe_forward NUMERIC(12,2),
            peg_ratio NUMERIC(12,2), price_to_book NUMERIC(12,2),
            price_to_fcf NUMERIC(12,2), ev_to_ebitda NUMERIC(12,2),
            ev_to_fcf NUMERIC(12,2),
            roe NUMERIC(10,4), roic NUMERIC(10,4),
            gross_margin NUMERIC(10,4), operating_margin NUMERIC(10,4),
            net_margin NUMERIC(10,4), fcf_margin NUMERIC(10,4),
            debt_to_equity NUMERIC(10,4), current_ratio NUMERIC(10,4),
            interest_coverage NUMERIC(10,2),
            revenue_growth_yoy NUMERIC(10,4), earnings_growth_yoy NUMERIC(10,4),
            fcf_growth_yoy NUMERIC(10,4),
            quarterly_trends TEXT,
            market_cap NUMERIC(20,0), enterprise_value NUMERIC(20,0),
            fifty_two_week_low NUMERIC(12,2), fifty_two_week_high NUMERIC(12,2),
            price_vs_52w_high NUMERIC(10,4)
        )
    """))
    session.commit()

    done = 0
    errors = 0

    for i, sym in enumerate(symbols, 1):
        try:
            print(f"  [{i}/{len(symbols)}] {sym}...", end=" ", flush=True)
            ticker = yf.Ticker(sym)
            info   = ticker.info or {}

            if not info.get("regularMarketPrice") and not info.get("currentPrice"):
                print("no data")
                continue

            # ── Quarterly trends ──────────────────────────────────────
            trends = _quarterly_trends(ticker)

            # ── TTM Margins (calculated from last 4 quarters) ──────────
            ttm_margins = _ttm_margins(ticker)

            # ── FCF (TTM) from info or calculated ─────────────────────
            fcf_ttm     = _safe(info.get("freeCashflow"))
            revenue_ttm = _safe(info.get("totalRevenue"))
            mkt_cap     = _safe(info.get("marketCap"))
            ev          = _safe(info.get("enterpriseValue"))

            # P/FCF
            price_to_fcf = round(mkt_cap / fcf_ttm, 2) if mkt_cap and fcf_ttm and fcf_ttm > 0 else None
            # EV/FCF
            ev_to_fcf    = round(ev / fcf_ttm, 2) if ev and fcf_ttm and fcf_ttm > 0 else None
            # FCF margin
            fcf_margin   = round(fcf_ttm / revenue_ttm, 4) if fcf_ttm and revenue_ttm else None

            # ROIC approx = NOPAT / (equity + debt)
            # NOPAT ≈ operating income × (1 - tax rate), use net income as proxy here
            net_inc   = _safe(info.get("netIncomeToCommon"))
            total_eq  = _safe(info.get("bookValue"))      # per share
            shares    = _safe(info.get("sharesOutstanding"))
            total_dbt = _safe(info.get("totalDebt"))
            equity_abs = (total_eq * shares) if total_eq and shares else None
            roic = round(net_inc / (equity_abs + total_dbt), 4) \
                if net_inc and equity_abs and total_dbt and (equity_abs + total_dbt) > 0 \
                else None

            # Price vs 52-week high
            price  = _safe(info.get("currentPrice") or info.get("regularMarketPrice"))
            hi52   = _safe(info.get("fiftyTwoWeekHigh"))
            p_vs_hi = round(price / hi52, 4) if price and hi52 else None

            # YoY growth from quarterly trends (more reliable than info)
            rev_growth = _yoy_growth(trends, "revenue") or _pct(info.get("revenueGrowth"))
            earn_growth = _yoy_growth(trends, "net_income") or _pct(info.get("earningsGrowth"))
            fcf_growth  = _yoy_growth(trends, "fcf")

            # Interest coverage = EBIT / interest expense
            ebit     = _safe(info.get("ebit"))
            int_exp  = _safe(info.get("interestExpense"))
            int_cov  = round(ebit / abs(int_exp), 2) \
                if ebit and int_exp and int_exp != 0 else None

            # Upsert
            row = session.query(Fundamentals).filter_by(symbol=sym).first()
            if not row:
                row = Fundamentals(symbol=sym)
                session.add(row)

            row.fetched_at          = datetime.utcnow()
            row.pe_trailing         = _safe(info.get("trailingPE"))
            row.pe_forward          = _safe(info.get("forwardPE"))
            row.peg_ratio           = _safe(info.get("pegRatio"))
            row.price_to_book       = _safe(info.get("priceToBook"))
            row.price_to_fcf        = price_to_fcf
            row.ev_to_ebitda        = _safe(info.get("enterpriseToEbitda"))
            row.ev_to_fcf           = ev_to_fcf
            row.roe                 = _pct(info.get("returnOnEquity"))
            row.roic                = roic
            # Use TTM margins (last 4 quarters) instead of yfinance.info FY figures
            # This avoids stale data and the 100% gross margin bug for financial services
            row.gross_margin        = ttm_margins.get("gross_margin") or _pct(info.get("grossMargins"))
            row.operating_margin    = ttm_margins.get("operating_margin") or _pct(info.get("operatingMargins"))
            row.net_margin          = ttm_margins.get("net_margin") or _pct(info.get("profitMargins"))
            row.fcf_margin          = fcf_margin
            # yfinance returns debtToEquity as a percentage (e.g. 35.78 = 0.3578x ratio)
            _raw_de = _safe(info.get("debtToEquity"))
            row.debt_to_equity      = round(_raw_de / 100, 4) if _raw_de is not None else None
            row.current_ratio       = _safe(info.get("currentRatio"))
            row.interest_coverage   = int_cov
            row.revenue_growth_yoy  = rev_growth
            row.earnings_growth_yoy = earn_growth
            row.fcf_growth_yoy      = fcf_growth
            row.quarterly_trends    = json.dumps(trends) if trends else None
            row.market_cap          = int(mkt_cap) if mkt_cap else None
            row.enterprise_value    = int(ev) if ev else None
            row.fifty_two_week_low  = _safe(info.get("fiftyTwoWeekLow"))
            row.fifty_two_week_high = hi52
            row.price_vs_52w_high   = p_vs_hi
            row.sector              = info.get("sector") or None
            row.industry            = info.get("industry") or None
            row.analyst_rating      = info.get("recommendationKey") or None
            row.analyst_target_price = _safe(info.get("targetMeanPrice"))
            row.analysts_count      = info.get("numberOfAnalystOpinions") or None

            session.commit()
            done += 1
            print(f"P/E={row.pe_trailing or '—'}  PEG={row.peg_ratio or '—'}  ROE={round(row.roe*100,1) if row.roe else '—'}%  sector={row.sector or '—'}")
            time.sleep(0.3)  # polite to Yahoo

        except Exception as exc:
            errors += 1
            print(f"error: {exc}")
            session.rollback()

    print(f"\nFundamentals complete: {done} stored, {errors} errors.")
    return {"done": done, "errors": errors}
