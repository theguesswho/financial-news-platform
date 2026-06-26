"""
Buy-and-Hold Backtest

For each scoring date, identify Q1–Q5 quintiles (and S&P).
Buy on that date, hold to TODAY. No rebalancing, no exit.

This answers: "If I had screened on this date and just held,
how would each quintile have done vs buying the index?"

Three comparisons per period:
  • Q5 (top hidden gems) vs Q1 (bottom scores)
  • Q5 vs equal-weight S&P 500 universe
  • Q5 vs SPY ETF (total market benchmark)
"""

import os
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import date, timedelta
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv(override=True)

PE_CEILING  = 75.0
PEG_CEILING = 6.0
TODAY = date(2026, 6, 11)   # latest date with price data


def get_engine():
    host     = os.getenv("DB_HOST_IP", "localhost")
    password = os.getenv("DB_PASSWORD", "")
    user     = os.getenv("DB_USER", "postgres")
    name     = os.getenv("DB_NAME", "postgres")
    return create_engine(
        f"postgresql+psycopg2://{user}:{password}@{host}/{name}",
        pool_pre_ping=True,
    )


def _margin_bucket(gm):
    if gm is None:
        return "mid"
    return "high" if gm > 0.50 else ("mid" if gm > 0.25 else "low")


def _rank_within_groups(group_vals: dict, ascending=True) -> dict:
    scores = {}
    for bucket, members in group_vals.items():
        vals = [(s, v) for s, v in members if v is not None and np.isfinite(float(v))]
        if not vals:
            continue
        cap = np.percentile([float(v) for _, v in vals], 95)
        vals = [(s, min(float(v), cap)) for s, v in vals]
        sorted_v = sorted(vals, key=lambda x: x[1], reverse=not ascending)
        n = max(len(sorted_v) - 1, 1)
        for i, (s, _) in enumerate(sorted_v):
            scores[s] = i / n
    return scores


def get_spy_price(spy_df: pd.DataFrame, target: date) -> float | None:
    """Nearest available SPY close on or before target date."""
    subset = spy_df[spy_df.index.date <= target]
    if subset.empty:
        return None
    return float(subset["Close"].iloc[-1])


def get_price(engine, symbol: str, target: date) -> float | None:
    with engine.connect() as conn:
        r = conn.execute(text("""
            SELECT close FROM eod_prices
            WHERE symbol = :s AND date <= :d
            ORDER BY date DESC LIMIT 1
        """), {"s": symbol, "d": target}).fetchone()
    return float(r[0]) if r else None


def compute_historical_scores(engine, as_of: date) -> dict:
    """Point-in-time value + quality scores (mirrors narrative_backtest logic)."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT DISTINCT ON (hm.symbol)
                hm.symbol, hm.pe_ratio, hm.pfcf_ratio, hm.roic,
                hm.gross_margin, hm.operating_margin, hm.net_margin,
                hm.net_income, hm.market_cap, hm.revenue
            FROM historical_metrics hm
            WHERE hm.date <= :dt
            ORDER BY hm.symbol, hm.date DESC
        """), {"dt": as_of}).fetchall()

        trend_rows = conn.execute(text("""
            SELECT symbol, operating_margin, roic, date
            FROM (
                SELECT symbol, operating_margin, roic, date,
                       ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) as rn
                FROM historical_metrics
                WHERE date <= :dt
            ) sub
            WHERE rn <= 2
            ORDER BY symbol, date DESC
        """), {"dt": as_of}).fetchall()

    trend_map = {}
    for sym, om, roic, dt in trend_rows:
        trend_map.setdefault(sym, []).append({
            "om":   float(om)   if om   is not None else None,
            "roic": float(roic) if roic is not None else None,
        })

    stocks = {}
    for r in rows:
        sym, pe, pfcf, roic, gm, om, nm, ni, mcap, revenue = r
        pe_f   = float(pe)      if pe      and float(pe)      > 0 else None
        roic_f = float(roic)    if roic    else None
        gm_f   = float(gm)      if gm      else None
        om_f   = float(om)      if om      else None
        mcap_f = float(mcap)    if mcap    else None
        rev_f  = float(revenue) if revenue and float(revenue) > 0 else None

        pe_ok = pe_f is not None and pe_f <= PE_CEILING
        ps_f  = None
        if pe_ok and mcap_f and rev_f and om_f and om_f > 0.01:
            ps_f = mcap_f / (rev_f * 4)

        trend = trend_map.get(sym, [])
        margin_improving = roic_improving = False
        if len(trend) >= 2:
            om_new,  om_old  = trend[0].get("om"),   trend[1].get("om")
            ri_new,  ri_old  = trend[0].get("roic"), trend[1].get("roic")
            if om_new is not None and om_old is not None:
                margin_improving = om_new > om_old
            if ri_new is not None and ri_old is not None:
                roic_improving   = ri_new > ri_old

        stocks[sym] = {
            "pe": pe_f, "roic": roic_f, "gm": gm_f, "om": om_f,
            "ps": ps_f, "margin_improving": margin_improving,
            "roic_improving": roic_improving,
        }

    pe_groups = {"high": [], "mid": [], "low": []}
    ps_groups = {"high": [], "mid": [], "low": []}
    for sym, d in stocks.items():
        bucket = _margin_bucket(d["gm"])
        pe_groups[bucket].append((sym, d["pe"] if d["pe"] and d["pe"] <= PE_CEILING else None))
        ps_groups[bucket].append((sym, d["ps"]))

    pe_rank = _rank_within_groups(pe_groups, ascending=True)
    ps_rank = _rank_within_groups(ps_groups, ascending=False)

    roic_groups = {"high": [], "mid": [], "low": []}
    om_groups   = {"high": [], "mid": [], "low": []}
    for sym, d in stocks.items():
        bucket = _margin_bucket(d["gm"])
        roic_groups[bucket].append((sym, d["roic"]))
        om_groups[bucket].append((sym, d["om"]))

    roic_abs = _rank_within_groups(roic_groups, ascending=True)
    om_abs   = _rank_within_groups(om_groups,   ascending=True)

    results = {}
    for sym in stocks:
        d = stocks[sym]
        pe_v = pe_rank.get(sym)
        ps_v = ps_rank.get(sym)
        v = max(pe_v or 0, ps_v or 0)

        traj = 0.50
        if d.get("roic_improving"):   traj += 0.25
        if d.get("margin_improving"): traj += 0.25
        abs_signals = [x for x in [roic_abs.get(sym), om_abs.get(sym)] if x is not None]
        abs_rank = float(np.mean(abs_signals)) if abs_signals else 0.5
        q = round(0.70 * traj + 0.30 * abs_rank, 4)

        results[sym] = {"value": round(v, 4), "quality": round(q, 4), "pe": d["pe"], "ps": d["ps"]}

    return results


def compute_historical_gap_score(engine, as_of: date,
                                 spy_df: pd.DataFrame,
                                 narr_momentum: dict) -> dict:
    """
    Point-in-time gap score at a historical scoring date.

    Mirrors compute_gap_score() in hidden_gem_scorer.py but uses historical
    prices and metrics anchored to `as_of`.

    price_lag       (50%) — stock's 6m return ending at as_of vs SPY
    multiple_inertia (30%) — PE at as_of vs PE 12 months prior + fundamental trend
    narrative_momentum (20%) — current trajectory (acknowledged look-ahead)
    """
    six_months_prior  = as_of - timedelta(days=182)
    twelve_months_prior = as_of - timedelta(days=365)

    # ── SPY return over the 6 months ending at as_of ─────────────────────────
    spy_now = get_spy_price(spy_df, as_of)
    spy_6m_ago = get_spy_price(spy_df, six_months_prior)
    spy_6m = (spy_now / spy_6m_ago - 1) if spy_now and spy_6m_ago and spy_6m_ago > 0 else 0.10

    with engine.connect() as conn:
        # Stock prices: at as_of vs 6 months prior
        price_rows = conn.execute(text("""
            SELECT a.symbol, a.close AS price_now, b.close AS price_6m
            FROM (
                SELECT DISTINCT ON (symbol) symbol, close
                FROM eod_prices WHERE date <= :as_of
                ORDER BY symbol, date DESC
            ) a
            LEFT JOIN LATERAL (
                SELECT close FROM eod_prices
                WHERE symbol = a.symbol AND date <= :six_months_prior
                ORDER BY date DESC LIMIT 1
            ) b ON true
        """), {"as_of": as_of, "six_months_prior": six_months_prior}).fetchall()

        # PE + fundamentals: at as_of vs 12 months prior
        pe_rows = conn.execute(text("""
            SELECT a.symbol,
                   a.pe_ratio AS pe_now,  b.pe_ratio AS pe_12m,
                   a.roic     AS roic_now, b.roic     AS roic_12m,
                   a.operating_margin AS om_now, b.operating_margin AS om_12m
            FROM (
                SELECT DISTINCT ON (symbol) symbol, pe_ratio, roic, operating_margin
                FROM historical_metrics
                WHERE date <= :as_of
                  AND pe_ratio IS NOT NULL AND pe_ratio > 0 AND pe_ratio < 500
                ORDER BY symbol, date DESC
            ) a
            LEFT JOIN LATERAL (
                SELECT pe_ratio, roic, operating_margin
                FROM historical_metrics
                WHERE symbol = a.symbol AND date <= :twelve_months_prior
                  AND pe_ratio IS NOT NULL AND pe_ratio > 0 AND pe_ratio < 500
                ORDER BY date DESC LIMIT 1
            ) b ON true
        """), {"as_of": as_of, "twelve_months_prior": twelve_months_prior}).fetchall()

    # price_lag: positive = stock underperformed SPY
    price_lag = {}
    for sym, p_now, p_6m in price_rows:
        if p_now and p_6m and float(p_6m) > 0:
            stock_6m = float(p_now) / float(p_6m) - 1
            lag = spy_6m - stock_6m
            price_lag[sym] = float(np.clip((lag + 0.30) / 0.60, 0.0, 1.0))

    # multiple_inertia: did PE expand to reward improving fundamentals?
    multiple_inertia = {}
    for sym, pe_now, pe_12m, roic_now, roic_12m, om_now, om_12m in pe_rows:
        pe_n  = float(pe_now)   if pe_now   else None
        pe_o  = float(pe_12m)   if pe_12m   else None
        ri_n  = float(roic_now) if roic_now else None
        ri_o  = float(roic_12m) if roic_12m else None
        om_n  = float(om_now)   if om_now   else None
        om_o  = float(om_12m)   if om_12m   else None

        fund_improving = (
            ri_n is not None and ri_o is not None and ri_n > ri_o and
            om_n is not None and om_o is not None and om_n > om_o
        )
        if pe_n and pe_o and fund_improving:
            pe_change = (pe_n - pe_o) / pe_o
            multiple_inertia[sym] = float(np.clip(0.5 - pe_change * 0.5, 0.0, 1.0))
        elif fund_improving:
            multiple_inertia[sym] = 0.60
        else:
            multiple_inertia[sym] = 0.25

    # Combine
    all_syms = set(price_lag) | set(multiple_inertia) | set(narr_momentum)
    gap_scores = {}
    for sym in all_syms:
        pl = price_lag.get(sym, 0.50)
        mi = multiple_inertia.get(sym, 0.25)
        nm = narr_momentum.get(sym, 0.50)
        gap_scores[sym] = round(0.50 * pl + 0.30 * mi + 0.20 * nm, 4)

    return gap_scores


def run_buyhold_backtest():
    engine = get_engine()

    # Current narrative scores (mild look-ahead — acknowledged)
    from pipeline.hidden_gem_scorer import compute_narrative_score
    narrative = compute_narrative_score(engine)

    # Current narrative trajectory (look-ahead — consistent with narrative score)
    with engine.connect() as conn:
        narr_traj_rows = conn.execute(text("""
            SELECT DISTINCT ON (sta.symbol) sta.symbol, sta.trajectory
            FROM stock_theme_alignment sta
            JOIN meta_themes mt ON mt.id = sta.meta_theme_id
            WHERE mt.momentum = 'accelerating'
            ORDER BY sta.symbol, sta.alignment_score DESC
        """)).fetchall()
    narr_momentum = {
        sym: (1.0 if traj == "accelerating" else (0.5 if traj == "stable" else 0.0))
        for sym, traj in narr_traj_rows
    }

    # Download SPY once
    print("Fetching SPY prices...")
    spy_raw = yf.download("SPY", start="2021-12-01", end="2026-06-12",
                          auto_adjust=True, progress=False)
    spy_df = spy_raw[["Close"]].copy()

    score_dates = [
        date(2022, 6, 30),
        date(2022, 12, 31),
        date(2023, 6, 30),
        date(2023, 12, 31),
        date(2024, 6, 30),
        date(2024, 12, 31),
    ]

    print("\n" + "=" * 90)
    print("BUY-AND-HOLD BACKTEST  |  Buy at scoring date, hold to today ({})".format(TODAY))
    print("No rebalancing. No exit. Quintiles vs SPY.")
    print("=" * 90)

    period_summaries = []

    for score_date in score_dates:
        holding_years = (TODAY - score_date).days / 365.25

        vq = compute_historical_scores(engine, score_date)
        if not vq:
            continue

        # Point-in-time gap scores for this scoring date
        hist_gap = compute_historical_gap_score(engine, score_date, spy_df, narr_momentum)

        rows = []
        for sym, d in vq.items():
            n = narrative.get(sym, 0.0)
            v = d["value"]
            q = d["quality"]

            # Signal 1: narrative value floor (unchanged — operates before gem)
            hist_pe = d.get("pe")
            g_score = hist_gap.get(sym, 0.50)
            if n > 0.65 and v < 0.15 and hist_pe and hist_pe > PE_CEILING and g_score > 0.60:
                v = max(v, 0.25 * n)

            gem = (n * v * q) ** (1/3) if (n > 0 and v > 0 and q > 0) else 0.0

            # Gap multiplier: rewards overlooked stocks, penalises fully-priced ones
            gap_mult = 0.70 + 0.50 * g_score
            gem = min(gem * gap_mult, 1.0)

            p0      = get_price(engine, sym, score_date)
            p_today = get_price(engine, sym, TODAY)

            if not p0 or not p_today:
                continue

            total_return = p_today / p0 - 1
            # Annualised CAGR
            cagr = (p_today / p0) ** (1 / holding_years) - 1 if holding_years > 0 else 0

            rows.append({
                "symbol":    sym,
                "gem_score": round(gem, 4),
                "ret_total": total_return,
                "cagr":      cagr,
            })

        if not rows:
            continue

        df = pd.DataFrame(rows)
        df["gem_q"] = pd.qcut(df["gem_score"], 5, labels=[1, 2, 3, 4, 5])

        # SPY return over same period
        spy0      = get_spy_price(spy_df, score_date)
        spy_today = get_spy_price(spy_df, TODAY)
        spy_total = spy_today / spy0 - 1 if spy0 and spy_today else None
        spy_cagr  = (spy_today / spy0) ** (1 / holding_years) - 1 if spy0 and spy_today else None

        # Equal-weight universe (all stocks we scored)
        ew_total = df["ret_total"].mean()
        ew_cagr  = df["cagr"].mean()

        print(f"\n{'─'*90}")
        print(f"  Scored {score_date}  →  Hold to {TODAY}  ({holding_years:.1f} years)")
        print(f"  {len(df)} stocks scored | SPY: {spy_total:+.1%} total  ({spy_cagr:+.1%}/yr)")
        print(f"  {'Quintile':<12} {'Total Return':>14} {'CAGR/yr':>10} {'vs SPY':>10} {'Stocks':>8}")
        print(f"  {'─'*58}")

        for q in [5, 4, 3, 2, 1]:
            grp   = df[df["gem_q"] == q]
            label = "Q5 (Gems)" if q == 5 else ("Q1 (Worst)" if q == 1 else f"Q{q}")
            tr    = grp["ret_total"].mean()
            cg    = grp["cagr"].mean()
            vs_spy = tr - spy_total if spy_total is not None else None
            vs_str = f"{vs_spy:+.1%}" if vs_spy is not None else "—"
            print(f"  {label:<12} {tr:>+14.1%} {cg:>+10.1%} {vs_str:>10} {len(grp):>8}")

        print(f"  {'Equal-Weight':<12} {ew_total:>+14.1%} {ew_cagr:>+10.1%} "
              f"{(ew_total-spy_total):>+10.1%}" if spy_total else "")
        print(f"  {'SPY':<12} {spy_total:>+14.1%} {spy_cagr:>+10.1%} {'0.0%':>10}")

        q5_total = df[df["gem_q"] == 5]["ret_total"].mean()
        q1_total = df[df["gem_q"] == 1]["ret_total"].mean()

        period_summaries.append({
            "score_date":    score_date,
            "holding_years": holding_years,
            "q5_total":      q5_total,
            "q1_total":      q1_total,
            "spy_total":     spy_total,
            "ew_total":      ew_total,
            "q5_vs_spy":     q5_total - spy_total if spy_total is not None else None,
            "q5_vs_q1":      q5_total - q1_total,
            "n_stocks":      len(df),
        })

    # ── Summary table ───────────────────────────────────────────────────────────
    if period_summaries:
        print("\n" + "=" * 90)
        print("SUMMARY ACROSS ALL SCORING DATES")
        print("=" * 90)
        print(f"\n  {'Date':<14} {'Years':<8} {'Q5':>10} {'Q1':>10} {'SPY':>10} "
              f"{'Q5 vs SPY':>12} {'Q5 vs Q1':>12}")
        print(f"  {'─'*78}")
        for s in period_summaries:
            spy_str   = f"{s['spy_total']:+.1%}"   if s["spy_total"]  is not None else "—"
            vs_spy_str = f"{s['q5_vs_spy']:+.1%}"  if s["q5_vs_spy"] is not None else "—"
            print(f"  {str(s['score_date']):<14} {s['holding_years']:<8.1f} "
                  f"{s['q5_total']:>+10.1%} {s['q1_total']:>+10.1%} {spy_str:>10} "
                  f"{vs_spy_str:>12} {s['q5_vs_q1']:>+12.1%}")

        avg_q5_vs_spy = np.mean([s["q5_vs_spy"] for s in period_summaries if s["q5_vs_spy"] is not None])
        avg_q5_vs_q1  = np.mean([s["q5_vs_q1"] for s in period_summaries])
        wins_vs_spy   = sum(1 for s in period_summaries if s.get("q5_vs_spy", -1) > 0)
        wins_vs_q1    = sum(1 for s in period_summaries if s["q5_vs_q1"] > 0)

        print(f"\n  Avg Q5 outperformance vs SPY:  {avg_q5_vs_spy:+.1%}")
        print(f"  Avg Q5 outperformance vs Q1:   {avg_q5_vs_q1:+.1%}")
        print(f"  Q5 beat SPY: {wins_vs_spy}/{len(period_summaries)} periods")
        print(f"  Q5 beat Q1:  {wins_vs_q1}/{len(period_summaries)} periods")


if __name__ == "__main__":
    run_buyhold_backtest()
