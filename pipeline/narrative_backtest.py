"""
Narrative Backtest v2

Investment thesis: surface businesses whose FUNDAMENTALS are improving
and which the market is mispricing. Price follows earnings — eventually.

Backtest measures:
  1. 12-month forward price return (primary)
  2. 12-month fundamental improvement: earnings growth, FCF growth (secondary)
     A stock in Q5 with +40% earnings but flat price is the system WORKING.

Scoring:
  - Value + Quality fully point-in-time via historical_metrics
  - Narrative current-state (mild look-ahead — acknowledged)
  - Gross margin buckets as sector proxy
  - Hard PE ceiling applied historically too

Periods: every 6 months from 2022 onwards — as many as data allows.
"""

import os
import numpy as np
import pandas as pd
from datetime import date, timedelta
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv(override=True)

PE_CEILING  = 75.0
PEG_CEILING = 6.0


def get_engine():
    if os.getenv("DATABASE_URL"):
        url = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg2://")
        from sqlalchemy import create_engine
        return create_engine(url, pool_pre_ping=True)
    host = os.getenv("DB_HOST_IP", "localhost")
    password = os.getenv("DB_PASSWORD", "")
    user = os.getenv("DB_USER", "postgres")
    name = os.getenv("DB_NAME", "postgres")
    return create_engine(f"postgresql+psycopg2://{user}:{password}@{host}/{name}", pool_pre_ping=True)


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


def get_price(engine, symbol, target_date):
    with engine.connect() as conn:
        r = conn.execute(text("""
            SELECT close FROM eod_prices
            WHERE symbol = :s AND date <= :d
            ORDER BY date DESC LIMIT 1
        """), {"s": symbol, "d": target_date}).fetchone()
    return float(r[0]) if r else None


def compute_historical_scores(engine, as_of: date) -> dict:
    """
    Compute value + quality scores using point-in-time historical_metrics.

    Value score  = best of (PE rank, P/Sales rank) within gross-margin peer group.
    Quality score = ROIC + operating margin + margin trajectory bonus.

    The P/Sales metric catches the "Dell pattern": earnings temporarily compressed
    (PE looks expensive) but the underlying business is cheap on revenue.
    The margin trajectory bonus catches stocks where fundamentals are IMPROVING
    even while price is stagnant — exactly the hidden gem we want.
    """
    with engine.connect() as conn:
        # Latest snapshot per symbol (point-in-time)
        rows = conn.execute(text("""
            SELECT DISTINCT ON (hm.symbol)
                hm.symbol,
                hm.pe_ratio,
                hm.pfcf_ratio,
                hm.roic,
                hm.gross_margin,
                hm.operating_margin,
                hm.net_margin,
                hm.net_income,
                hm.market_cap,
                hm.revenue
            FROM historical_metrics hm
            WHERE hm.date <= :dt
            ORDER BY hm.symbol, hm.date DESC
        """), {"dt": as_of}).fetchall()

        # Last 2 snapshots per symbol — to detect ROIC and margin trajectory
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

    # Build trend map: symbol → [{"om": ..., "roic": ...}, ...]  newest first
    trend_map = {}
    for sym, om, roic, dt in trend_rows:
        trend_map.setdefault(sym, []).append({
            "om":   float(om)   if om   is not None else None,
            "roic": float(roic) if roic is not None else None,
        })

    stocks = {}
    for r in rows:
        sym, pe, pfcf, roic, gm, om, nm, ni, mcap, revenue = r
        pe_f    = float(pe)   if pe    and float(pe)   > 0 else None
        pfcf_f  = float(pfcf) if pfcf  and float(pfcf) > 0 else None
        roic_f  = float(roic) if roic else None
        gm_f    = float(gm)   if gm   else None
        om_f    = float(om)   if om   else None
        mcap_f  = float(mcap) if mcap else None
        rev_f   = float(revenue) if revenue and float(revenue) > 0 else None

        # Price-to-Sales (only for viable businesses; annualise quarterly revenue)
        # Hard PE ceiling also disables P/Sales — can't escape by switching metric
        pe_ok = pe_f is not None and pe_f <= PE_CEILING
        ps_f = None
        if pe_ok and mcap_f and rev_f and om_f and om_f > 0.01:
            annual_rev = rev_f * 4
            ps_f = mcap_f / annual_rev

        # Trajectory: is ROIC and operating margin improving over last 2 snapshots?
        trend = trend_map.get(sym, [])
        margin_improving = False
        roic_improving   = False
        if len(trend) >= 2:
            om_new, om_old   = trend[0].get("om"),   trend[1].get("om")
            ri_new, ri_old   = trend[0].get("roic"), trend[1].get("roic")
            if om_new is not None and om_old is not None:
                margin_improving = om_new > om_old
            if ri_new is not None and ri_old is not None:
                roic_improving   = ri_new > ri_old

        stocks[sym] = {
            "pe":               pe_f,
            "pfcf":             pfcf_f,
            "roic":             roic_f,
            "gm":               gm_f,
            "om":               om_f,
            "ps":               ps_f,
            "margin_improving": margin_improving,
            "roic_improving":   roic_improving,
        }

    # ── Value: PE rank + P/Sales rank, take the better of the two ─────────────
    pe_groups = {"high": [], "mid": [], "low": []}
    ps_groups = {"high": [], "mid": [], "low": []}

    for sym, d in stocks.items():
        bucket = _margin_bucket(d["gm"])

        # PE (hard ceiling)
        if d["pe"] and d["pe"] <= PE_CEILING:
            pe_groups[bucket].append((sym, d["pe"]))
        else:
            pe_groups[bucket].append((sym, None))

        # P/Sales (no ceiling — cheap revenue is always good)
        ps_groups[bucket].append((sym, d["ps"]))

    pe_rank = _rank_within_groups(pe_groups, ascending=True)    # existing direction
    ps_rank = _rank_within_groups(ps_groups, ascending=False)  # lower P/Sales = higher score

    # ── Quality: ROIC + operating margin + margin trajectory bonus ─────────────
    roic_groups = {"high": [], "mid": [], "low": []}
    om_groups   = {"high": [], "mid": [], "low": []}

    for sym, d in stocks.items():
        bucket = _margin_bucket(d["gm"])
        roic_groups[bucket].append((sym, d["roic"]))
        om_groups[bucket].append((sym, d["om"]))

    # Absolute ROIC and OM rank — correct direction: higher = better
    roic_abs = _rank_within_groups(roic_groups, ascending=True)
    om_abs   = _rank_within_groups(om_groups,   ascending=True)

    results = {}
    for sym in stocks:
        d = stocks[sym]

        # ── Value: best of PE rank and P/Sales rank ────────────────────────────
        pe_v = pe_rank.get(sym)
        ps_v = ps_rank.get(sym)
        if pe_v is not None and ps_v is not None:
            v = max(pe_v, ps_v)
        elif pe_v is not None:
            v = pe_v
        elif ps_v is not None:
            v = ps_v
        else:
            v = 0.0

        # ── Quality: trajectory-primary (70% traj + 30% absolute) ─────────────
        # Trajectory
        traj = 0.50
        if d.get("roic_improving"):
            traj += 0.25
        if d.get("margin_improving"):
            traj += 0.25

        # Absolute rank (correct direction)
        abs_signals = [roic_abs.get(sym), om_abs.get(sym)]
        abs_signals = [x for x in abs_signals if x is not None]
        abs_rank = float(np.mean(abs_signals)) if abs_signals else 0.5

        q = round(0.70 * traj + 0.30 * abs_rank, 4)

        results[sym] = {
            "value":            round(v, 4),
            "quality":          round(q, 4),
            "pe":               d["pe"],
            "roic":             d["roic"],
            "gm":               d["gm"],
            "ps":               d["ps"],
            "margin_improving": d.get("margin_improving", False),
        }

    return results


def compute_fundamental_improvement(engine, sym, start: date, end: date):
    """
    Measure how much earnings and FCF improved between start and end dates.
    Used as secondary validation — price may lag but fundamentals don't lie.
    """
    with engine.connect() as conn:
        start_r = conn.execute(text("""
            SELECT net_income, gross_profit FROM historical_metrics
            WHERE symbol = :s AND date <= :d ORDER BY date DESC LIMIT 1
        """), {"s": sym, "d": start}).fetchone()

        end_r = conn.execute(text("""
            SELECT net_income, gross_profit FROM historical_metrics
            WHERE symbol = :s AND date <= :d ORDER BY date DESC LIMIT 1
        """), {"s": sym, "d": end}).fetchone()

    if not start_r or not end_r:
        return None

    ni_start, gp_start = float(start_r[0] or 0), float(start_r[1] or 0)
    ni_end,   gp_end   = float(end_r[0]   or 0), float(end_r[1]   or 0)

    ni_growth = (ni_end - ni_start) / abs(ni_start) if ni_start != 0 else None
    gp_growth = (gp_end - gp_start) / abs(gp_start) if gp_start != 0 else None

    return {"ni_growth": ni_growth, "gp_growth": gp_growth}


def run_backtest():
    engine = get_engine()

    from pipeline.hidden_gem_scorer import compute_narrative_score
    narrative = compute_narrative_score(engine)

    # All scoring periods — every 6 months from 2022
    # 12-month return window means last usable score date ~ 12 months ago
    score_dates = [
        date(2022, 6, 30),
        date(2022, 12, 31),
        date(2023, 6, 30),
        date(2023, 12, 31),
        date(2024, 6, 30),
        date(2024, 12, 31),
    ]

    all_rows = []

    print("=" * 85)
    print("HIDDEN GEM BACKTEST v2 — 12-month horizon | Fundamental improvement tracked")
    print(f"PE ceiling: {PE_CEILING}x | Gross-margin peer groups")
    print("=" * 85)

    for score_date in score_dates:
        ret_date = score_date + timedelta(days=365)
        print(f"\nPeriod: Score {score_date} → 12m return by {ret_date}")

        vq = compute_historical_scores(engine, score_date)
        if not vq:
            print("  No data")
            continue

        rows = []
        for sym, d in vq.items():
            n = narrative.get(sym, 0.0)
            v = d["value"]
            q = d["quality"]

            gem    = (n * v * q) ** (1/3) if (n > 0 and v > 0 and q > 0) else 0.0
            vq_only = (v * q) ** 0.5

            p0  = get_price(engine, sym, score_date)
            p12 = get_price(engine, sym, ret_date)

            if not p0:
                continue

            ret_12m = (p12 / p0 - 1) if p12 else None

            # Fundamental improvement over the same window
            fund = compute_fundamental_improvement(engine, sym, score_date, ret_date)
            ni_growth = fund["ni_growth"] if fund else None
            gp_growth = fund["gp_growth"] if fund else None

            rows.append({
                "symbol":           sym,
                "score_date":       score_date,
                "gem_score":        round(gem, 4),
                "vq_score":         round(vq_only, 4),
                "narrative":        round(n, 4),
                "value":            round(v, 4),
                "quality":          round(q, 4),
                "pe":               d["pe"],
                "roic":             d["roic"],
                "ps":               d.get("ps"),
                "margin_improving": d.get("margin_improving", False),
                "ret_12m":          ret_12m,
                "ni_growth":        ni_growth,
                "gp_growth":        gp_growth,
            })

        df = pd.DataFrame(rows)
        df_priced = df.dropna(subset=["ret_12m"])
        if len(df_priced) < 20:
            print(f"  Only {len(df_priced)} stocks with prices, skipping")
            continue

        df_priced = df_priced.copy()
        df_priced["gem_q"] = pd.qcut(df_priced["gem_score"], 5, labels=[1,2,3,4,5])
        df_priced["vq_q"]  = pd.qcut(df_priced["vq_score"],  5, labels=[1,2,3,4,5])

        mkt = df_priced["ret_12m"].mean()
        gem_q5 = df_priced[df_priced["gem_q"] == 5]["ret_12m"].mean()
        gem_q1 = df_priced[df_priced["gem_q"] == 1]["ret_12m"].mean()
        vq_q5  = df_priced[df_priced["vq_q"]  == 5]["ret_12m"].mean()
        vq_q1  = df_priced[df_priced["vq_q"]  == 1]["ret_12m"].mean()

        # Fundamental improvement for top quintile
        q5_stocks = df_priced[df_priced["gem_q"] == 5]
        avg_ni_q5 = q5_stocks["ni_growth"].mean()

        print(f"  Stocks: {len(df_priced)} | Market avg 12m: {mkt:+.1%}")
        print(f"  Hidden Gem:     Q5={gem_q5:+.1%}  Q1={gem_q1:+.1%}  Spread={gem_q5-gem_q1:+.1%}  "
              f"vs Market: {gem_q5-mkt:+.1%}")
        print(f"  Value+Quality:  Q5={vq_q5:+.1%}  Q1={vq_q1:+.1%}  Spread={vq_q5-vq_q1:+.1%}")
        print(f"  Narrative premium: {(gem_q5-gem_q1)-(vq_q5-vq_q1):+.1%}")
        if avg_ni_q5 is not None:
            print(f"  Q5 avg earnings growth: {avg_ni_q5:+.1%}  "
                  f"{'✅ fundamentals improving' if avg_ni_q5 > 0 else '⚠️  earnings declined'}")

        # DELL in this period
        dell_row = df_priced[df_priced["symbol"] == "DELL"]
        if not dell_row.empty:
            dr = dell_row.iloc[0]
            ps_str = f"P/S={dr['ps']:.2f}x" if dr.get('ps') else ""
            mi_str = "↑margin" if dr.get('margin_improving') else ""
            ni_str = f"Earn:{dr['ni_growth']:+.1%}" if dr.get('ni_growth') is not None else ""
            print(f"  DELL: Score={dr['gem_score']:.3f} Q{dr['gem_q']} | "
                  f"PE={dr['pe'] or '-'} | {ps_str} | {mi_str} | "
                  f"12m={dr['ret_12m']:+.1%} | {ni_str}")

        all_rows.append(df_priced)

    if not all_rows:
        print("\nNo backtest data available.")
        return

    combined = pd.concat(all_rows, ignore_index=True)
    combined["gem_q"] = pd.qcut(combined["gem_score"], 5, labels=[1,2,3,4,5])

    print("\n" + "=" * 85)
    print("COMBINED — ALL PERIODS  (12-month horizon)")
    print("=" * 85)
    print(f"\n{'Quintile':<14} {'Avg 12m Return':>15} {'Avg Earn Growth':>16} {'Count':>7}")
    print("-" * 56)
    for q in [5, 4, 3, 2, 1]:
        grp = combined[combined["gem_q"] == q]
        label = "Q5 TOP" if q == 5 else ("Q1 BOTTOM" if q == 1 else f"Q{q}")
        avg_ni = grp["ni_growth"].mean()
        print(f"{label:<14} {grp['ret_12m'].mean():>+15.1%} "
              f"{avg_ni:>+15.1%} {len(grp):>7}")

    spread = (combined[combined["gem_q"]==5]["ret_12m"].mean() -
              combined[combined["gem_q"]==1]["ret_12m"].mean())
    mkt_avg = combined["ret_12m"].mean()
    q5_avg  = combined[combined["gem_q"]==5]["ret_12m"].mean()

    print(f"\n  Q5 vs Q1 spread: {spread:+.1%}")
    print(f"  Q5 vs Market:    {q5_avg - mkt_avg:+.1%}")

    # DELL full history
    dell_all = combined[combined["symbol"] == "DELL"].sort_values("score_date")
    if not dell_all.empty:
        print(f"\n  DELL across all periods:")
        for _, r in dell_all.iterrows():
            ni_str  = f"Earn:{r['ni_growth']:+.1%}" if r['ni_growth'] is not None else ""
            ps_str  = f"P/S={r['ps']:.2f}x" if r.get('ps') is not None else ""
            mi_str  = "↑mg" if r.get('margin_improving') else "  "
            print(f"    {r['score_date']}  Score={r['gem_score']:.3f} Q{r['gem_q']}  "
                  f"PE={r['pe'] or '-':.1f}  {ps_str}  {mi_str}  "
                  f"12m={r['ret_12m']:+.1%}  {ni_str}")

    # Top gems right now (current scores)
    print("\n" + "=" * 85)
    print("CURRENT TOP 20 HIDDEN GEMS")
    print("=" * 85)
    from pipeline.hidden_gem_scorer import score_all_stocks
    current = score_all_stocks(engine)

    print(f"\n{'#':>3} {'Sym':<7} {'Score':>6} {'Narr':>6} {'Val':>6} {'Qual':>6} "
          f"{'FwdPE':>7} {'RevGr':>7} {'EarnGr':>7}  Top Theme")
    print("-" * 110)
    for i, s in enumerate(current[:20], 1):
        theme = s["top_themes"][0]["theme"] if s["top_themes"] else "-"
        print(f"{i:>3} {s['symbol']:<7} {s['hidden_gem_score']:>6.3f} "
              f"{s['narrative_score']:>6.3f} {s['value_score']:>6.3f} {s['quality_score']:>6.3f} "
              f"{s['pe_forward'] or 0:>7.1f} "
              f"{(s['revenue_growth'] or 0)*100:>6.1f}% "
              f"{(s['earnings_growth'] or 0)*100:>6.1f}%  {theme[:45]}")


if __name__ == "__main__":
    run_backtest()
