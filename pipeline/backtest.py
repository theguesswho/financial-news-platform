"""
Historical backtest using clean FMP quarterly metrics.

For each stock at each quarter-end we have:
  - Pre-calculated PE, P/FCF, EV/EBITDA, ROIC, margins (from FMP)
  - Historical price (from EodPrice DB)
  - Revenue growth (calculated from sequential FMP quarters)

Measures 3-month and 6-month forward returns.
Tests whether the mismatch score has predictive value.
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import asc
from sqlalchemy.orm import Session

from db.models import EodPrice, HistoricalMetrics
from pipeline.score import (
    _clamp, _percentile_score, _score_price_vs_52w,
    _score_roic, _score_margin, _score_debt, _score_peg,
)


# Quarter-ends to evaluate — limited to where we have forward price data
QUARTER_ENDS = [
    date(2022, 3, 31),
    date(2022, 6, 30),
    date(2022, 9, 30),
    date(2022, 12, 31),
    date(2023, 3, 31),
    date(2023, 6, 30),
    date(2023, 9, 30),
    date(2023, 12, 31),
    date(2024, 3, 31),
    date(2024, 6, 28),
    date(2024, 9, 30),
    date(2024, 12, 31),
    date(2025, 3, 31),
    date(2025, 6, 30),
    date(2025, 9, 30),
    date(2025, 12, 31),
]


def _nearest_price(price_map: dict, target: date, window: int = 7) -> float | None:
    for offset in range(window + 1):
        for d in [target - timedelta(days=offset), target + timedelta(days=offset)]:
            if d in price_map:
                return price_map[d]
    return None


def _revenue_growth_yoy(sym_metrics: list[HistoricalMetrics], as_of: date) -> float | None:
    """YoY revenue growth: most recent quarter vs same quarter one year prior."""
    past = [m for m in sym_metrics if m.date <= as_of and m.revenue]
    past.sort(key=lambda m: m.date, reverse=True)
    if len(past) < 5:
        return None
    curr  = float(past[0].revenue)
    prior = float(past[4].revenue)   # ~1 year ago
    if prior == 0:
        return None
    return (curr - prior) / abs(prior)


def _classify(gross_margin: float | None) -> str:
    """Classify business type from gross margin — no look-ahead, uses historical value."""
    if gross_margin is None:     return "mid"
    if gross_margin > 0.40:      return "high"   # software, pharma, financials
    if gross_margin < 0.25:      return "low"    # hardware, industrial, commodity, retail
    return "mid"                                  # blend zone


def _quality_score(m: HistoricalMetrics, biz: str) -> float:
    roic = float(m.roic)           if m.roic           else None
    gm   = float(m.gross_margin)   if m.gross_margin   else None
    om   = float(m.operating_margin) if m.operating_margin else None
    de   = float(m.debt_to_equity) if m.debt_to_equity else None

    q_roic = _score_roic(roic)
    q_gm   = _score_margin(gm, 0.30, 0.60)
    q_om   = _score_margin(om, 0.10, 0.30)
    q_debt = _score_debt(de)

    if biz == "high":
        # ROIC is meaningful — reward it heavily
        return q_roic*0.40 + q_gm*0.20 + q_om*0.20 + q_debt*0.20
    elif biz == "low":
        # ROIC structurally low for hardware/industrial — de-emphasise
        # Operating margin and debt safety matter more
        return q_roic*0.08 + q_gm*0.12 + q_om*0.45 + q_debt*0.35
    else:
        return q_roic*0.25 + q_gm*0.17 + q_om*0.33 + q_debt*0.25


def _value_score(m: HistoricalMetrics, all_pes: list[float],
                 price_vs_high: float | None, biz: str) -> float:
    pe  = float(m.pe_ratio)   if m.pe_ratio   and float(m.pe_ratio)   > 0 else None
    pfcf = float(m.pfcf_ratio) if m.pfcf_ratio and float(m.pfcf_ratio) > 0 else None
    pb   = float(m.price_to_book) if m.price_to_book else 1.0
    pb_penalty = 0.85 if pb < 0 else 1.0

    pe_score   = _percentile_score(pe, all_pes, lower_is_better=True) if pe else 0.40
    high_score = _score_price_vs_52w(price_vs_high)
    pfcf_score = _percentile_score(
        pfcf, [p for p in all_pes if p], lower_is_better=True
    ) if pfcf else 0.40

    if biz == "low":
        # FCF yield matters more than PE for asset-heavy businesses
        raw = pe_score*0.30 + pfcf_score*0.40 + high_score*0.30
    elif biz == "high":
        # PE and price vs high are the key signals
        raw = pe_score*0.50 + high_score*0.30 + pfcf_score*0.20
    else:
        raw = pe_score*0.40 + high_score*0.35 + pfcf_score*0.25

    return raw * pb_penalty


def _traj_score(rev_growth: float | None, biz: str) -> float:
    if rev_growth is None:
        return 0.50
    if biz == "low":
        # Revenue growth is THE signal for low-margin cyclicals — weight it heavily
        if rev_growth > 0.40: return 1.00
        if rev_growth > 0.20: return 0.85
        if rev_growth > 0.08: return 0.70
        if rev_growth > 0.00: return 0.55
        if rev_growth > -0.08: return 0.38
        return 0.20
    else:
        if rev_growth > 0.50: return 1.00
        if rev_growth > 0.30: return 0.90
        if rev_growth > 0.15: return 0.75
        if rev_growth > 0.05: return 0.60
        if rev_growth > 0.00: return 0.50
        if rev_growth > -0.10: return 0.35
        return 0.20


# ── Three scoring variants ────────────────────────────────────────────────────

def _hist_score(m: HistoricalMetrics, all_pes: list[float],
                rev_growth: float | None, price_vs_high: float | None) -> float:
    """V1 — Original uniform weights (baseline)."""
    q_roic = _score_roic(float(m.roic) if m.roic else None)
    q_gm   = _score_margin(float(m.gross_margin) if m.gross_margin else None, 0.30, 0.60)
    q_om   = _score_margin(float(m.operating_margin) if m.operating_margin else None, 0.10, 0.30)
    q_debt = _score_debt(float(m.debt_to_equity) if m.debt_to_equity else None)
    quality = q_roic*0.40 + q_gm*0.20 + q_om*0.25 + q_debt*0.15

    pe = float(m.pe_ratio) if m.pe_ratio and float(m.pe_ratio) > 0 else None
    pe_score   = _percentile_score(pe, all_pes, lower_is_better=True) if pe else 0.40
    high_score = _score_price_vs_52w(price_vs_high)
    pb = float(m.price_to_book) if m.price_to_book else 1.0
    value = (pe_score*0.50 + high_score*0.50) * (0.85 if pb < 0 else 1.0)

    if rev_growth is None:           traj = 0.50
    elif rev_growth > 0.50:          traj = 1.00
    elif rev_growth > 0.30:          traj = 0.90
    elif rev_growth > 0.15:          traj = 0.75
    elif rev_growth > 0.05:          traj = 0.60
    elif rev_growth > 0.00:          traj = 0.50
    elif rev_growth > -0.10:         traj = 0.35
    else:                            traj = 0.20

    return _clamp((quality * value * traj) ** (1/3))


def _hist_score_v2(m: HistoricalMetrics, all_pes: list[float],
                   rev_growth: float | None, price_vs_high: float | None) -> float:
    """V2 — Sector-aware weights based on gross margin classification."""
    biz = _classify(float(m.gross_margin) if m.gross_margin else None)
    quality = _quality_score(m, biz)
    value   = _value_score(m, all_pes, price_vs_high, biz)
    traj    = _traj_score(rev_growth, biz)
    return _clamp((quality * value * traj) ** (1/3))


def _hist_score_simple(m: HistoricalMetrics, all_pes: list[float],
                       rev_growth: float | None, price_vs_high: float | None) -> float:
    """V3 — Ultra-simple: just PE percentile × revenue growth direction."""
    pe = float(m.pe_ratio) if m.pe_ratio and float(m.pe_ratio) > 0 else None
    pe_score = _percentile_score(pe, all_pes, lower_is_better=True) if pe else 0.40

    if rev_growth is None:      traj = 0.50
    elif rev_growth > 0.30:     traj = 1.00
    elif rev_growth > 0.15:     traj = 0.80
    elif rev_growth > 0.05:     traj = 0.65
    elif rev_growth > 0.00:     traj = 0.50
    else:                       traj = 0.25

    return _clamp((pe_score * traj) ** 0.5)


def run_backtest(session: Session, symbols: list[str]) -> pd.DataFrame:

    print(f"Building historical snapshots for {len(symbols)} stocks "
          f"across {len(QUARTER_ENDS)} quarters...")

    # Load all historical metrics and prices into memory
    all_metrics: dict[str, list[HistoricalMetrics]] = {}
    for m in (session.query(HistoricalMetrics)
              .filter(HistoricalMetrics.symbol.in_(symbols))
              .order_by(asc(HistoricalMetrics.date))
              .all()):
        all_metrics.setdefault(m.symbol, []).append(m)

    price_maps: dict[str, dict[date, float]] = {}
    for rec in (session.query(EodPrice)
                .filter(EodPrice.symbol.in_(symbols))
                .all()):
        price_maps.setdefault(rec.symbol, {})[rec.date] = float(rec.close)

    rows = []

    for qend in QUARTER_ENDS:
        # Collect PE values across the universe at this quarter-end (for percentile scoring)
        all_pes = []
        for sym, mlist in all_metrics.items():
            snap = next((m for m in reversed(mlist) if m.date <= qend), None)
            if snap and snap.pe_ratio and float(snap.pe_ratio) > 0:
                all_pes.append(float(snap.pe_ratio))

        for sym in symbols:
            mlist = all_metrics.get(sym, [])
            pmap  = price_maps.get(sym, {})

            # Most recent metrics as of this quarter-end
            snap = next((m for m in reversed(mlist) if m.date <= qend), None)
            if not snap:
                continue

            price = _nearest_price(pmap, qend)
            if not price:
                continue

            # 52-week trailing high
            lookback = qend - timedelta(days=365)
            window_prices = [v for d, v in pmap.items() if lookback <= d <= qend]
            high_52w = max(window_prices) if window_prices else None
            pvh = price / high_52w if high_52w else None

            # Revenue growth YoY
            rev_growth = _revenue_growth_yoy(mlist, qend)

            # All three score variants
            s_v1     = _hist_score(snap, all_pes, rev_growth, pvh)
            s_v2     = _hist_score_v2(snap, all_pes, rev_growth, pvh)
            s_simple = _hist_score_simple(snap, all_pes, rev_growth, pvh)
            gm = float(snap.gross_margin) if snap.gross_margin else None

            # Forward returns
            p3 = _nearest_price(pmap, qend + timedelta(days=91))
            p6 = _nearest_price(pmap, qend + timedelta(days=182))
            ret_3m = (p3 - price) / price if p3 else None
            ret_6m = (p6 - price) / price if p6 else None

            rows.append({
                "symbol":       sym,
                "date":         qend,
                "price":        round(price, 2),
                "biz_type":     _classify(gm),
                "hist_pe":      round(float(snap.pe_ratio), 1) if snap.pe_ratio else None,
                "pfcf":         round(float(snap.pfcf_ratio), 1) if snap.pfcf_ratio else None,
                "roic":         round(float(snap.roic) * 100, 1) if snap.roic else None,
                "gross_margin": round(gm * 100, 1) if gm else None,
                "rev_growth":   round(rev_growth * 100, 1) if rev_growth is not None else None,
                "price_vs_52w": round(pvh, 3) if pvh else None,
                # Three variants
                "v1_score":     round(s_v1, 3),
                "v2_score":     round(s_v2, 3),
                "simple_score": round(s_simple, 3),
                # Keep hist_score as v1 for backwards compat
                "hist_score":   round(s_v1, 3),
                "ret_3m":       round(ret_3m, 4) if ret_3m is not None else None,
                "ret_6m":       round(ret_6m, 4) if ret_6m is not None else None,
            })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["tier"] = pd.cut(
        df["hist_score"],
        bins=[0, 0.40, 0.60, 1.01],
        labels=["Low (<0.40)", "Medium (0.40-0.60)", "High (>0.60)"],
    )
    return df


def _tier_summary(df: pd.DataFrame, score_col: str, return_col: str, label: str):
    valid = df.dropna(subset=[score_col, return_col]).copy()
    if valid.empty:
        return
    valid["_tier"] = pd.cut(
        valid[score_col],
        bins=[0, 0.40, 0.60, 1.01],
        labels=["Low (<0.40)", "Medium (0.40-0.60)", "High (>0.60)"],
    )
    tier = (valid.groupby("_tier", observed=False)[return_col]
            .agg(mean="mean", median="median", count="count"))
    corr = valid[score_col].corr(valid[return_col])
    spread = (tier.loc["High (>0.60)", "mean"] - tier.loc["Low (<0.40)", "mean"]
              if "High (>0.60)" in tier.index and "Low (<0.40)" in tier.index else None)

    print(f"\n  [{label}]  r={corr:+.3f}  "
          f"High-Low spread={spread*100:+.1f}pp  (N={len(valid)})")
    for idx, row in tier.iterrows():
        print(f"    {str(idx):<22}  mean={row['mean']:+.1%}  "
              f"median={row['median']:+.1%}  n={int(row['count'])}")


def print_results(df: pd.DataFrame, focus: str = "DELL"):

    # ── Focus stock: all three variants ───────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"  {focus} — three scoring variants vs actual price action")
    print(f"{'='*80}")
    sub = df[df["symbol"] == focus].sort_values("date")
    print(f"  {'Date':<12} {'BizType':<6} {'V1(orig)':<10} {'V2(sector)':<12} "
          f"{'Simple':<8} {'PE':<7} {'RevGrowth':<11} {'3m':<8} {'6m'}")
    print(f"  {'-'*88}")
    for _, r in sub.iterrows():
        f3  = f"{r['ret_3m']*100:+.1f}%" if r['ret_3m'] is not None else " n/a"
        f6  = f"{r['ret_6m']*100:+.1f}%" if r['ret_6m'] is not None else " n/a"
        rg  = f"{r['rev_growth']:+.0f}%" if r['rev_growth'] is not None else " n/a"
        pe  = f"{r['hist_pe']:.0f}x"     if r['hist_pe']    else " n/a"
        v1  = f"{r['v1_score']:.3f}"
        v2  = f"{r['v2_score']:.3f}"
        si  = f"{r['simple_score']:.3f}"
        flag = " ◄" if r['v2_score'] >= 0.60 else ""
        print(f"  {str(r['date']):<12} {r['biz_type']:<6} {v1:<10} {v2:<12} "
              f"{si:<8} {pe:<7} {rg:<11} {f3:<8} {f6}{flag}")

    # ── Three-way tier comparison ──────────────────────────────────────────────
    print(f"\n{'='*80}")
    print("  BACKTEST COMPARISON — 3-month forward returns by score tier")
    print(f"{'='*80}")
    _tier_summary(df, "v1_score",     "ret_3m", "V1 Original (uniform weights)")
    _tier_summary(df, "v2_score",     "ret_3m", "V2 Sector-aware weights      ")
    _tier_summary(df, "simple_score", "ret_3m", "V3 Ultra-simple (PE×growth)  ")

    print(f"\n{'='*80}")
    print("  BACKTEST COMPARISON — 6-month forward returns by score tier")
    print(f"{'='*80}")
    _tier_summary(df, "v1_score",     "ret_6m", "V1 Original (uniform weights)")
    _tier_summary(df, "v2_score",     "ret_6m", "V2 Sector-aware weights      ")
    _tier_summary(df, "simple_score", "ret_6m", "V3 Ultra-simple (PE×growth)  ")

    # ── V2 top picks per quarter ───────────────────────────────────────────────
    print(f"\n{'='*80}")
    print("  V2 TOP 5 SCORES PER QUARTER (sector-aware)")
    print(f"{'='*80}")
    for qend in sorted(df["date"].unique()):
        q = df[df["date"] == qend].sort_values("v2_score", ascending=False).head(5)
        tops = [f"{r['symbol']}({r['v2_score']:.2f},{r['biz_type'][0]})" for _, r in q.iterrows()]
        print(f"  {qend}:  {',  '.join(tops)}")
