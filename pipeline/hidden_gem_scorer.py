"""
Hidden Gem Scorer v2

Three multiplicative dimensions — must score well on ALL three:

  Narrative Score  — alignment to ACCELERATING meta-themes only
  Value Score      — cheap relative to growth, within gross-margin peer group
  Quality Score    — margins, ROIC, cash generation

  Hidden Gem Score = (Narrative × Value × Quality) ^ (1/3)

Key design decisions:
  - Gross margin buckets as sector proxy (no sector tags available)
      High  >50%  → software, pharma, financials
      Mid  25-50% → tech hardware, services, healthcare devices
      Low   <25%  → industrials, retailers, commodity, auto
  - Hard valuation ceiling: forward PE > 75x → value score = 0
    (stocks priced for perfection cannot be hidden gems)
  - PEG ratio as primary value metric (growth-adjusted)
  - Recent filing momentum weighted more heavily in narrative
"""

import os
import numpy as np
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv(override=True)

# Hard ceiling — above this forward PE, value score is zeroed out
PE_CEILING = 75.0
PEG_CEILING = 6.0

# Stocks excluded from scoring — pending M&A, delisted, or otherwise
# not valid for fundamental ranking
EXCLUDED_SYMBOLS = {
    "EA",   # Subject to acquisition bid — market price reflects takeover premium
}


def get_engine():
    if os.getenv("DATABASE_URL"):
        url = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg2://")
    else:
        host = os.getenv("DB_HOST_IP", "localhost")
        password = os.getenv("DB_PASSWORD", "")
        user = os.getenv("DB_USER", "postgres")
        name = os.getenv("DB_NAME", "postgres")
        url = f"postgresql+psycopg2://{user}:{password}@{host}/{name}"
    # keepalives + recycle: Railway's proxy silently kills idle connections;
    # without these a write to a dead socket hangs forever instead of failing.
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=120,
        connect_args={
            "connect_timeout": 10,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 3,
        },
    )


def _margin_bucket(gross_margin):
    """Gross-margin peer group — fallback when sector data is unavailable."""
    if gross_margin is None:
        return "mid"
    gm = float(gross_margin)
    if gm > 0.50:
        return "high"
    elif gm > 0.25:
        return "mid"
    else:
        return "low"


# Map yfinance sector strings → peer bucket names.
# Groups sectors with comparable margin/return profiles so that
# a consulting firm isn't ranked against oil refiners.
_SECTOR_BUCKET = {
    "Technology":             "tech",
    "Communication Services": "tech",
    "Healthcare":             "healthcare",
    "Financial Services":     "financials",
    "Real Estate":            "real_estate",
    "Utilities":              "defensives",
    "Energy":                 "cyclicals",
    "Basic Materials":        "cyclicals",
    "Industrials":            "industrials",
    "Consumer Defensive":     "consumer",
    "Consumer Cyclical":      "consumer",
}


def _peer_bucket(sector, industry, gross_margin, industry_counts=None):
    """
    Peer bucket — industry-first cascade:
      1. Industry  (most granular — airlines vs airlines, not airlines vs Caterpillar)
         Only skipped if the industry has ≤1 member in our universe.
      2. Sector    (fallback for singleton/missing industries)
      3. Gross-margin bucket (last resort when sector data is absent)
    """
    if industry and (industry_counts is None or industry_counts.get(industry, 0) > 1):
        return industry
    if sector and sector in _SECTOR_BUCKET:
        return _SECTOR_BUCKET[sector]
    return _margin_bucket(gross_margin)


def _rank_within_group(groups: dict, ascending=True) -> dict:
    """
    Rank each symbol within its gross-margin peer group.
    Returns {symbol: 0.0–1.0} where 1.0 = best in group.
    """
    scores = {}
    for bucket, members in groups.items():
        vals = [(sym, val) for sym, val in members if val is not None and np.isfinite(float(val))]
        if not vals:
            continue
        # Cap outliers at 95th percentile
        raw_vals = [float(v) for _, v in vals]
        cap = np.percentile(raw_vals, 95)
        vals = [(s, min(float(v), cap)) for s, v in vals]

        sorted_vals = sorted(vals, key=lambda x: x[1], reverse=not ascending)
        n = max(len(sorted_vals) - 1, 1)
        for i, (sym, _) in enumerate(sorted_vals):
            scores[sym] = i / n
    return scores


def compute_call_vs_filing_gap(engine) -> dict:
    """
    Call-vs-filing narrative gap: avg(EARN_CALL narrative_strength) minus
    avg(10-K/10-Q narrative_strength) per symbol, using last 4 quarters.

    When management consistently sounds more confident on calls than filings,
    the market is likely anchoring on cautious legal language and missing the
    real momentum. This gap is itself a hidden gem signal.

    Returns a score in [-1, +1], normalised so 0 = no gap, positive = calls
    are more bullish than filings. Stored in results as 'call_filing_gap'.
    """
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                symbol,
                AVG(CASE WHEN filing_type = 'EARN_CALL' THEN narrative_strength END)
                    AS call_strength,
                AVG(CASE WHEN filing_type IN ('10-K','10-Q') THEN narrative_strength END)
                    AS filing_strength,
                COUNT(CASE WHEN filing_type = 'EARN_CALL' THEN 1 END)
                    AS call_count,
                COUNT(CASE WHEN filing_type IN ('10-K','10-Q') THEN 1 END)
                    AS filing_count
            FROM (
                SELECT ft.symbol, ft.filing_type, ft.narrative_strength
                FROM filing_themes ft
                WHERE ft.filing_type IN ('10-K','10-Q','EARN_CALL')
                  AND ft.filing_date >= NOW() - INTERVAL '18 months'
            ) sub
            GROUP BY symbol
            HAVING COUNT(CASE WHEN filing_type = 'EARN_CALL' THEN 1 END) >= 2
               AND COUNT(CASE WHEN filing_type IN ('10-K','10-Q') THEN 1 END) >= 1
        """)).fetchall()

    gaps = {}
    for sym, call_s, file_s, call_n, file_n in rows:
        if call_s is not None and file_s is not None:
            gaps[sym] = float(call_s) - float(file_s)

    # Normalise to [0, 1]: gap of 0 → 0.50 (neutral), large positive → near 1.0
    if not gaps:
        return {}
    max_gap  = max(abs(v) for v in gaps.values()) or 1.0
    return {s: max(0.0, min(1.0, 0.50 + (v / max_gap) * 0.50))
            for s, v in gaps.items()}


def compute_narrative_score(engine) -> dict:
    """
    Narrative score from the narrative brain (LLM-judged exposures with cited
    evidence — see pipeline/narrative_exposure.py), not cosine alignment.

    Per stock: noisy-OR over its exposures, each weighted by the narrative's
    momentum and status:
        accelerating active   × 1.00
        stable active         × 0.60
        declining             × 0.20   (a dying tailwind is nearly worthless)
    n = 1 - Π(1 - exposure_i × w_i)  — one strong narrative dominates; a second
    genuine one adds a modest kicker. No exposure → n = 0 → gated out.

    Blended 85/15 with the call-vs-filing gap signal.
    """
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT ne.symbol, ne.exposure, nar.momentum, nar.status
            FROM narrative_exposures ne
            JOIN narratives nar ON nar.id = ne.narrative_id
            WHERE nar.status IN ('active', 'declining')
        """)).fetchall()

    theme_scores: dict[str, float] = {}
    if rows:
        per_stock: dict[str, list[float]] = {}
        for sym, exposure, momentum, status in rows:
            if status == "declining":
                w = 0.20
            elif momentum == "accelerating":
                w = 1.00
            else:
                w = 0.60
            per_stock.setdefault(sym, []).append(float(exposure) * w)

        # Dominant exposure + small kicker for a genuine second narrative.
        # Then percentile-rank across exposed stocks: ~90% of large caps have
        # SOME narrative exposure, so absolute values alone don't discriminate —
        # the gate must separate "the business IS the narrative" (DELL, 0.78
        # with a cited 51B backlog) from "meaningful contributor" (0.35).
        raw = {}
        for sym, weighted in per_stock.items():
            ws = sorted(weighted, reverse=True)
            raw[sym] = min(1.0, ws[0] + (0.15 * ws[1] if len(ws) > 1 else 0.0))

        ranked = sorted(raw, key=raw.get)
        n_exposed = len(ranked)
        for i, sym in enumerate(ranked):
            pct = (i + 1) / n_exposed
            # Blend absolute exposure (60%) with percentile (40%): absolute
            # keeps cited-evidence meaning, percentile restores discrimination.
            theme_scores[sym] = 0.60 * raw[sym] + 0.40 * pct

    # Blend in call-vs-filing gap (15% weight)
    call_gap = compute_call_vs_filing_gap(engine)

    all_syms = set(theme_scores) | set(call_gap)
    blended  = {}
    for sym in all_syms:
        t = theme_scores.get(sym, 0.0)
        g = call_gap.get(sym, 0.50)   # 0.50 = neutral when no gap data
        blended[sym] = round(0.85 * t + 0.15 * g, 4)

    return blended


PFCF_CEILING = 200.0  # above this P/FCF is meaningless for ranking

def compute_value_score(engine) -> dict:
    """
    Value score — four signals blended within gross-margin peer group.

    PEG rank   (50% weight) — growth-adjusted cheapness, primary signal.
    PE rank    (30% weight) — preference for reasonable absolute price.
    P/FCF rank (20% weight) — cash generation cheapness.
      → Low PEG + low PE + low P/FCF scores highest.
        Hard PE ceiling (75×) zeros the PE component only.
        Hard PEG ceiling (6×) zeros the PEG component.
        Negative P/FCF (negative FCF) or >200× treated as null.

    P/Sales rank — backstop for the "Dell pattern" where earnings are temporarily
      compressed but revenue is genuinely cheap. Takes the max of the
      PEG/PE/P/FCF blend and the P/Sales rank, so it only helps, never hurts.
      Disabled for stocks already PE-ceiling-capped (can't escape via revenue).

    All ranked correctly: lower value = higher score (ascending=False).
    """
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT f.symbol, f.peg_ratio, f.pe_forward, f.pe_trailing,
                   f.revenue_growth_yoy, f.gross_margin, f.operating_margin,
                   f.market_cap, f.price_to_fcf, f.sector, f.industry, hm.revenue_ttm
            FROM fundamentals f
            LEFT JOIN LATERAL (
                -- TTM revenue: sum of last 4 quarters to avoid Q×4 seasonality distortion
                SELECT SUM(revenue) AS revenue_ttm
                FROM (
                    SELECT revenue
                    FROM historical_metrics
                    WHERE symbol = f.symbol AND revenue IS NOT NULL AND revenue > 0
                    ORDER BY date DESC LIMIT 4
                ) q
            ) hm ON true
        """)).fetchall()

    # Build industry counts for the cascade: industry → sector → gm-bucket
    industry_counts = {}
    for row in rows:
        ind = row[10]  # industry column
        if ind:
            industry_counts[ind] = industry_counts.get(ind, 0) + 1

    all_buckets = (list(set(_SECTOR_BUCKET.values()))
                   + list({row[10] for row in rows if row[10]})
                   + ["high", "mid", "low"])
    peg_groups  = {b: [] for b in all_buckets}
    pe_groups   = {b: [] for b in all_buckets}
    pfcf_groups = {b: [] for b in all_buckets}
    ps_groups   = {b: [] for b in all_buckets}

    for row in rows:
        sym, peg, pe_fwd, pe_trail, rev_gr, gm, om, mcap, pfcf, sector, industry, revenue = row
        bucket = _peer_bucket(sector, industry, gm, industry_counts)

        pe_fwd_f  = float(pe_fwd)   if pe_fwd   and float(pe_fwd)  > 0 else None
        pe_trl_f  = float(pe_trail)  if pe_trail  and float(pe_trail) > 0 else None
        peg_f     = float(peg)      if peg      and float(peg)     > 0 else None
        pfcf_f    = float(pfcf)     if pfcf     and float(pfcf) > 0 and float(pfcf) <= PFCF_CEILING else None
        om_f      = float(om)    if om    else None
        mcap_f    = float(mcap)  if mcap  else None
        rev_f     = float(revenue) if revenue and float(revenue) > 0 else None

        pe_val     = pe_fwd_f or pe_trl_f
        pe_capped  = bool(pe_val  and pe_val  > PE_CEILING)
        peg_capped = bool(peg_f   and peg_f   > PEG_CEILING)

        peg_groups[bucket].append((sym, None if peg_capped else peg_f))
        pe_groups[bucket].append((sym, None if pe_capped else pe_val))
        pfcf_groups[bucket].append((sym, pfcf_f))

        if not (mcap_f and rev_f and om_f and om_f > 0.01):
            ps_groups[bucket].append((sym, None))
        else:
            ps_groups[bucket].append((sym, mcap_f / rev_f))

    peg_rank  = _rank_within_group(peg_groups,  ascending=False)
    pe_rank   = _rank_within_group(pe_groups,   ascending=False)
    pfcf_rank = _rank_within_group(pfcf_groups, ascending=False)
    ps_rank   = _rank_within_group(ps_groups,   ascending=False)

    # Build a lookup of raw P/Sales values to detect "expensive on both" stocks
    ps_raw = {}
    for row in rows:
        sym, peg, pe_fwd, pe_trail, rev_gr, gm, om, mcap, pfcf, sector, industry, revenue = row
        pe_fwd_f = float(pe_fwd)  if pe_fwd  and float(pe_fwd)  > 0 else None
        pe_trl_f = float(pe_trail) if pe_trail and float(pe_trail) > 0 else None
        pe_val = pe_fwd_f or pe_trl_f
        mcap_f = float(mcap)    if mcap    else None
        rev_f  = float(revenue) if revenue and float(revenue) > 0 else None
        om_f   = float(om)      if om      else None
        if pe_val and pe_val > PE_CEILING and mcap_f and rev_f and om_f and om_f > 0.01:
            ps_raw[sym] = mcap_f / rev_f

    ps_by_bucket = {b: [] for b in all_buckets}
    for row in rows:
        sym, peg, pe_fwd, pe_trail, rev_gr, gm, om, mcap, pfcf, sector, industry, revenue = row
        bucket = _peer_bucket(sector, industry, float(gm) if gm else None, industry_counts)
        mcap_f = float(mcap)    if mcap    else None
        rev_f  = float(revenue) if revenue and float(revenue) > 0 else None
        om_f   = float(om)      if om      else None
        if mcap_f and rev_f and om_f and om_f > 0.01:
            ps_by_bucket[bucket].append(mcap_f / (rev_f * 4))

    ps_expensive_threshold = {}
    for b, vals in ps_by_bucket.items():
        if vals:
            ps_expensive_threshold[b] = float(np.percentile(vals, 75))

    sym_bucket = {}
    for row in rows:
        sym, _peg, _pef, _pet, _rg, gm, _om, _mc, _pfcf, sector, industry, _rev = row
        sym_bucket[sym] = _peer_bucket(sector, industry, float(gm) if gm else None, industry_counts)

    all_syms = set(peg_rank) | set(pe_rank) | set(pfcf_rank) | set(ps_rank)
    combined = {}
    for sym in all_syms:
        peg_v  = peg_rank.get(sym,  0.0)
        pe_v   = pe_rank.get(sym,   0.0)
        pfcf_v = pfcf_rank.get(sym)
        ps_v   = ps_rank.get(sym)

        # Weighted blend — P/FCF distributes its 20% to PEG/PE when unavailable
        if pfcf_v is not None:
            blend = 0.50 * peg_v + 0.30 * pe_v + 0.20 * pfcf_v
        else:
            blend = 0.625 * peg_v + 0.375 * pe_v  # renormalise to 1.0

        if ps_v is not None:
            if sym in ps_raw:
                threshold = ps_expensive_threshold.get(sym_bucket.get(sym, "mid"), 999)
                if ps_raw[sym] < threshold:
                    blend = max(blend, ps_v)
            else:
                blend = max(blend, ps_v)

        combined[sym] = round(blend, 4)

    return combined


def compute_quality_score(engine) -> dict:
    """
    Quality score — trajectory-primary formulation.

    Quality = 70% trajectory + 30% absolute rank (within gross-margin peer group).

      Trajectory score (0.5 baseline):
        +0.25 if ROIC improved over last 2 quarters
        +0.25 if operating margin improved over last 2 quarters

      Absolute rank: ROIC and operating margin ranked correctly
        (higher = better, ascending=True) within peer group.

    Why trajectory-primary?
      The 'Dell pattern' is a company with low-but-IMPROVING ROIC — at the start
      of a recovery cycle, absolute ROIC is still depressed. A purely absolute
      ranking would miss it. Trajectory captures the direction of travel, which
      is what matters for a 12-month investment horizon.

      A company with high-and-stable ROIC still scores well (trajectory=0.5,
      absolute rank=high). A company with low-and-improving ROIC (Dell 2022)
      also scores well (trajectory=1.0, absolute rank=low).
      A company with low-and-declining ROIC scores poorly on both.
    """
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT symbol, roic, gross_margin, operating_margin, roe, net_margin,
                   pe_forward, pe_trailing, price_to_fcf, sector, industry
            FROM fundamentals
        """)).fetchall()

        # Last 2 ANNUAL rows of op_margin and roic per stock (Y/Y trajectory).
        # Annual (period_type='A') avoids quarterly seasonality and gives a clean
        # year-over-year direction signal — e.g. FY2024 vs FY2023.
        # Quarterly figures (from historical_metrics) are NOT used here because
        # Q vs Q comparisons are dominated by seasonality and one-off items,
        # not underlying business trajectory.
        trend_rows = conn.execute(text("""
            SELECT symbol, roic, op_margin AS operating_margin FROM (
                SELECT symbol, roic, op_margin,
                       ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY period_end DESC) AS rn
                FROM fundamentals_history
                WHERE period_type = 'A'
            ) sub
            WHERE rn <= 2
            ORDER BY symbol, rn
        """)).fetchall()

        # 3-year fundamental trend from fundamentals_history (annual rows)
        # Returns oldest and newest annual values for gross_margin, op_margin, roic
        longterm_rows = conn.execute(text("""
            SELECT symbol,
                   FIRST_VALUE(gross_margin) OVER w  AS gm_old,
                   LAST_VALUE(gross_margin)  OVER w  AS gm_new,
                   FIRST_VALUE(op_margin)    OVER w  AS om_old,
                   LAST_VALUE(op_margin)     OVER w  AS om_new,
                   FIRST_VALUE(roic)         OVER w  AS roic_old,
                   LAST_VALUE(roic)          OVER w  AS roic_new,
                   COUNT(*) OVER (PARTITION BY symbol) AS n_periods
            FROM fundamentals_history
            WHERE period_type = 'A'
              AND period_end >= NOW() - INTERVAL '4 years'
            WINDOW w AS (
                PARTITION BY symbol
                ORDER BY period_end
                ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
            )
        """)).fetchall()

    # Build trajectory signals: symbol → [newest, older] (short-term)
    roic_trend = {}
    om_trend   = {}
    for sym, roic, om in trend_rows:
        roic_trend.setdefault(sym, []).append(float(roic) if roic is not None else None)
        om_trend.setdefault(sym,   []).append(float(om)   if om   is not None else None)

    def is_improving(vals):
        return (len(vals) >= 2 and vals[0] is not None and vals[1] is not None
                and vals[0] > vals[1])

    roic_improving   = {sym: is_improving(v) for sym, v in roic_trend.items()}
    margin_improving = {sym: is_improving(v) for sym, v in om_trend.items()}

    # Long-term trend signals (deduplicate — window gives one row per period per sym)
    seen_lt = set()
    lt_trend = {}   # sym → {gm_delta, om_delta, roic_delta, n_periods}
    for sym, gm_old, gm_new, om_old, om_new, roic_old, roic_new, n in longterm_rows:
        if sym in seen_lt:
            continue
        seen_lt.add(sym)
        lt_trend[sym] = {
            "gm_delta":   (float(gm_new)   - float(gm_old))   if gm_old   and gm_new   else None,
            "om_delta":   (float(om_new)   - float(om_old))    if om_old   and om_new   else None,
            "roic_delta": (float(roic_new) - float(roic_old))  if roic_old and roic_new else None,
            "n_periods":  int(n),
        }

    # Absolute rank within peer group — correct direction: higher = better
    industry_counts_q = {}
    for row in rows:
        ind = row[10]
        if ind:
            industry_counts_q[ind] = industry_counts_q.get(ind, 0) + 1

    all_buckets_q = (list(set(_SECTOR_BUCKET.values()))
                     + list({row[10] for row in rows if row[10]})
                     + ["high", "mid", "low"])
    groups_roic = {b: [] for b in all_buckets_q}
    groups_om   = {b: [] for b in all_buckets_q}
    fund_map = {}
    for row in rows:
        sym, roic, gm, om, roe, nm, pe_fwd, pe_trail, pfcf, sector, industry = row
        bucket = _peer_bucket(sector, industry, gm, industry_counts_q)
        groups_roic[bucket].append((sym, float(roic) if roic else None))
        groups_om[bucket].append((sym, float(om) if om else None))
        fund_map[sym] = {
            "gm": gm,
            "roic": float(roic) if roic else None,
            "pe": (float(pe_fwd) if pe_fwd and float(pe_fwd) > 0 else
                   float(pe_trail) if pe_trail and float(pe_trail) > 0 else None),
            "pfcf": (float(pfcf) if pfcf and float(pfcf) > 0 and float(pfcf) <= PFCF_CEILING else None),
        }

    roic_abs = _rank_within_group(groups_roic, ascending=True)
    om_abs   = _rank_within_group(groups_om,   ascending=True)

    all_syms = set(roic_abs) | set(om_abs) | set(roic_improving) | set(margin_improving)
    scores = {}
    for sym in all_syms:
        # ── Trajectory component (70% weight) ─────────────────────────────────
        traj = 0.50
        if roic_improving.get(sym, False):
            traj += 0.25
        if margin_improving.get(sym, False):
            traj += 0.25

        # ── Absolute component (30% weight) ───────────────────────────────────
        abs_signals = [roic_abs.get(sym), om_abs.get(sym)]
        abs_signals = [x for x in abs_signals if x is not None]
        abs_rank = float(np.mean(abs_signals)) if abs_signals else 0.5

        # ── Absolute ROIC stability bonus ─────────────────────────────────────
        # Short-term trajectory requires two consecutive quarters of improvement.
        # A business with consistently high ROIC (19%+) in a cyclical trough
        # gets no trajectory bonus even though the underlying quality is excellent.
        # This floor ensures genuinely high-ROIC businesses are not suppressed
        # by normal quarter-to-quarter variance.
        fd = fund_map.get(sym, {})
        roic_annual = fd.get("roic")
        if roic_annual:
            if roic_annual > 0.20:
                traj = max(traj, 0.85)  # exceptional capital efficiency
            elif roic_annual > 0.15:
                traj = max(traj, 0.72)  # strong ROIC — partial credit for stability
            elif roic_annual > 0.10:
                traj = max(traj, 0.60)  # decent ROIC — modest floor

        quality = 0.70 * traj + 0.30 * abs_rank

        # ── FCF conversion bonus ───────────────────────────────────────────────
        # When P/FCF < PE, the company generates more cash than GAAP earnings
        # suggest — depreciation, amortisation, or stock-comp creates the spread.
        # Bonus scales with the size of the gap: max +8% quality boost.
        fd = fund_map.get(sym, {})
        pe_v   = fd.get("pe")
        pfcf_v = fd.get("pfcf")
        if pe_v and pfcf_v and pfcf_v < pe_v:
            # FCF yield > earnings yield → superior cash conversion
            spread_ratio = (pe_v - pfcf_v) / pe_v   # 0→1
            bonus = min(0.08, 0.08 * spread_ratio)
            quality = min(1.0, quality + bonus)

        # ── Long-term fundamental trend modifier (±10% max) ───────────────────
        # Uses 3–4 years of annual data from fundamentals_history.
        # Rewards companies with consistently improving margins and ROIC;
        # penalises secular deterioration. Bounded to avoid overwhelming the
        # short-term trajectory signal above.
        lt = lt_trend.get(sym)
        if lt and lt["n_periods"] >= 2:
            trend_adj = 0.0
            # Gross margin trend: >200bps expansion = +4%, >200bps contraction = -4%
            if lt["gm_delta"] is not None:
                gm_d = lt["gm_delta"]
                trend_adj += max(-0.04, min(0.04, gm_d * 2.0))
            # Operating margin trend: same weight
            if lt["om_delta"] is not None:
                om_d = lt["om_delta"]
                trend_adj += max(-0.04, min(0.04, om_d * 2.0))
            # ROIC trend: >300bps improvement = +2%, deterioration = -2%
            if lt["roic_delta"] is not None:
                roic_d = lt["roic_delta"]
                trend_adj += max(-0.02, min(0.02, roic_d * 0.67))
            quality = max(0.0, min(1.0, quality + trend_adj))

        scores[sym] = round(quality, 4)

    return scores


def compute_gap_score(engine) -> dict:
    """
    Gap Score: degree to which the market has NOT yet priced the narrative.

    High gap (→ 1.0) = strong story, market hasn't noticed yet
    Low gap  (→ 0.0) = strong story, market has fully repriced it

    Applied in score_all_stocks as a gem multiplier:
        gem_adjusted = gem × (0.70 + 0.50 × gap_score)
        range: ×0.70 (no gap, fully priced) → ×1.20 (maximum gap, market wrong)
        crossover at gap = 0.60 → multiplier = 1.0 (neutral)

    Three components:
      price_lag       (50%) — stock lagging SPY over 6 months while narrative strong
      multiple_inertia (30%) — fundamentals improving but PE hasn't expanded to reflect it
      narrative_momentum (20%) — filing trajectory is accelerating
    """
    from datetime import date, timedelta

    today            = date.today()
    six_months_ago   = today - timedelta(days=182)
    twelve_months_ago = today - timedelta(days=365)

    # ── SPY 6-month return (benchmark) ───────────────────────────────────────
    spy_6m = None
    try:
        import yfinance as yf
        spy_raw = yf.download(
            "SPY",
            start=six_months_ago - timedelta(days=5),
            end=today,
            auto_adjust=True,
            progress=False,
        )
        if not spy_raw.empty and len(spy_raw) >= 2:
            spy_6m = float(spy_raw["Close"].iloc[-1]) / float(spy_raw["Close"].iloc[0]) - 1
    except Exception:
        pass

    # Fallback: median 6m return across universe if yfinance unavailable
    if spy_6m is None:
        with engine.connect() as conn:
            fb = conn.execute(text("""
                SELECT a.close / NULLIF(b.close, 0) - 1
                FROM (
                    SELECT DISTINCT ON (symbol) symbol, close
                    FROM eod_prices ORDER BY symbol, date DESC
                ) a
                LEFT JOIN LATERAL (
                    SELECT close FROM eod_prices
                    WHERE symbol = a.symbol AND date <= :d
                    ORDER BY date DESC LIMIT 1
                ) b ON true
            """), {"d": six_months_ago}).fetchall()
        vals = [float(r[0]) for r in fb if r[0] is not None]
        spy_6m = float(np.median(vals)) if vals else 0.10

    with engine.connect() as conn:
        # ── Stock prices: today vs 6 months ago ──────────────────────────────
        price_rows = conn.execute(text("""
            SELECT a.symbol,
                   a.close  AS price_now,
                   b.close  AS price_6m
            FROM (
                SELECT DISTINCT ON (symbol) symbol, close
                FROM eod_prices
                ORDER BY symbol, date DESC
            ) a
            LEFT JOIN LATERAL (
                SELECT close FROM eod_prices
                WHERE symbol = a.symbol AND date <= :six_months_ago
                ORDER BY date DESC LIMIT 1
            ) b ON true
        """), {"six_months_ago": six_months_ago}).fetchall()

        # ── PE multiple: now vs 12 months ago (quarterly FMP PE — direction only) ─
        # ── ROIC/margin: annual Y/Y from fundamentals_history ────────────────────
        # PE: historical_metrics quarterly PE from FMP is ~4× true annualised PE
        # because FMP computes it as price / quarterly EPS. We only use this for
        # direction (did the multiple expand or contract?) where the scale error
        # cancels out. It is NOT used as an absolute PE figure anywhere here.
        # ROIC and margin: use fundamentals_history annual figures compared Y/Y —
        # clean signal free of quarterly seasonality.
        pe_rows = conn.execute(text("""
            SELECT a.symbol,
                   a.pe_ratio  AS pe_now,
                   b.pe_ratio  AS pe_12m,
                   fh.roic_now,
                   fh.roic_12m,
                   fh.om_now,
                   fh.om_12m
            FROM (
                SELECT DISTINCT ON (symbol) symbol, pe_ratio
                FROM historical_metrics
                WHERE pe_ratio IS NOT NULL AND pe_ratio > 0 AND pe_ratio < 2000
                ORDER BY symbol, date DESC
            ) a
            LEFT JOIN LATERAL (
                SELECT pe_ratio
                FROM historical_metrics
                WHERE symbol = a.symbol
                  AND date <= :twelve_months_ago
                  AND pe_ratio IS NOT NULL AND pe_ratio > 0 AND pe_ratio < 2000
                ORDER BY date DESC LIMIT 1
            ) b ON true
            LEFT JOIN LATERAL (
                SELECT
                    MAX(CASE WHEN rn = 1 THEN roic      END) AS roic_now,
                    MAX(CASE WHEN rn = 2 THEN roic      END) AS roic_12m,
                    MAX(CASE WHEN rn = 1 THEN op_margin END) AS om_now,
                    MAX(CASE WHEN rn = 2 THEN op_margin END) AS om_12m
                FROM (
                    SELECT roic, op_margin,
                           ROW_NUMBER() OVER (ORDER BY period_end DESC) AS rn
                    FROM fundamentals_history
                    WHERE symbol = a.symbol AND period_type = 'A'
                ) sub
                WHERE rn <= 2
            ) fh ON true
        """), {"twelve_months_ago": twelve_months_ago}).fetchall()

        # ── Narrative trajectory ──────────────────────────────────────────────
        narr_rows = conn.execute(text("""
            SELECT DISTINCT ON (sta.symbol) sta.symbol, sta.trajectory
            FROM stock_theme_alignment sta
            JOIN meta_themes mt ON mt.id = sta.meta_theme_id
            WHERE mt.momentum = 'accelerating'
            ORDER BY sta.symbol, sta.alignment_score DESC
        """)).fetchall()

    # ── Component 1: price lag (50%) ──────────────────────────────────────────
    # Positive lag = stock underperformed SPY = market hasn't noticed the story.
    # Mapped from [-30pp, +30pp] range onto [0, 1].
    price_lag = {}
    for sym, p_now, p_6m in price_rows:
        if p_now and p_6m and float(p_6m) > 0:
            stock_6m = float(p_now) / float(p_6m) - 1
            lag      = spy_6m - stock_6m          # positive = lagged SPY
            price_lag[sym] = float(np.clip((lag + 0.30) / 0.60, 0.0, 1.0))

    # ── Component 2: multiple inertia (30%) ───────────────────────────────────
    # Fundamentals improving but PE unchanged/compressed = market not rewarding it.
    # If PE expanded to match improving fundamentals = gap already closed.
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
            # pe_change: +1.0 = PE doubled (market fully rewarded) → inertia 0.0
            #             0.0 = PE flat                              → inertia 0.5
            #            -0.5 = PE halved (market ignored)           → inertia 1.0
            pe_change = (pe_n - pe_o) / pe_o
            multiple_inertia[sym] = float(np.clip(0.5 - pe_change * 0.5, 0.0, 1.0))
        elif fund_improving:
            multiple_inertia[sym] = 0.60   # improving fundamentals, no PE data → lean toward gap
        else:
            multiple_inertia[sym] = 0.25   # not clearly improving → lean away from gap

    # ── Component 3: narrative momentum (20%) ─────────────────────────────────
    narr_momentum = {
        sym: (1.0 if traj == "accelerating" else (0.5 if traj == "stable" else 0.0))
        for sym, traj in narr_rows
    }

    # ── Combine ───────────────────────────────────────────────────────────────
    all_syms = set(price_lag) | set(multiple_inertia) | set(narr_momentum)
    gap_scores = {}
    for sym in all_syms:
        pl = price_lag.get(sym, 0.50)        # neutral if no price data
        mi = multiple_inertia.get(sym, 0.25) # lean-away if no fundamental data
        nm = narr_momentum.get(sym, 0.50)    # neutral if no narrative data
        gap_scores[sym] = round(0.50 * pl + 0.30 * mi + 0.20 * nm, 4)

    return gap_scores


def score_all_stocks(engine=None) -> list:
    """
    Compute hidden gem scores for all stocks.
    Returns list sorted by hidden_gem_score descending.
    """
    if engine is None:
        engine = get_engine()

    narrative = compute_narrative_score(engine)
    value     = compute_value_score(engine)
    quality   = compute_quality_score(engine)
    gap       = compute_gap_score(engine)
    call_gap  = compute_call_vs_filing_gap(engine)  # for display in results

    # Valuation vs narrative peers (Dell detector) — per stock, the discount
    # on its highest-exposure narrative. Positive = cheaper than peers.
    peer_disc: dict[str, float] = {}
    with engine.connect() as conn:
        disc_rows = conn.execute(text("""
            SELECT DISTINCT ON (symbol) symbol,
                   COALESCE(pe_discount, ev_discount) AS disc
            FROM theme_valuation_gaps
            WHERE COALESCE(pe_discount, ev_discount) IS NOT NULL
            ORDER BY symbol, alignment_score DESC
        """)).fetchall()
        peer_disc = {r[0]: max(-1.0, min(1.0, float(r[1]))) for r in disc_rows}

    # Top accelerating themes per stock for display
    with engine.connect() as conn:
        theme_rows = conn.execute(text("""
            SELECT sta.symbol, mt.name, sta.alignment_score
            FROM stock_theme_alignment sta
            JOIN meta_themes mt ON mt.id = sta.meta_theme_id
            WHERE mt.momentum = 'accelerating'
              AND sta.alignment_score > 0.005
            ORDER BY sta.symbol, sta.alignment_score DESC
        """)).fetchall()

        fund_rows = conn.execute(text("""
            SELECT symbol, peg_ratio, pe_forward, pe_trailing,
                   revenue_growth_yoy, gross_margin, roic, sector,
                   earnings_growth_yoy, fcf_growth_yoy
            FROM fundamentals
        """)).fetchall()

    stock_themes = {}
    for sym, theme, score in theme_rows:
        stock_themes.setdefault(sym, []).append({"theme": theme, "score": round(score, 3)})

    fund_map = {r[0]: r for r in fund_rows}
    all_symbols = set(narrative) | set(value) | set(quality)

    results = []
    for sym in all_symbols:
        if sym in EXCLUDED_SYMBOLS:
            continue
        n = narrative.get(sym, 0.0)
        v = value.get(sym, 0.0)
        q = quality.get(sym, 0.0)

        f = fund_map.get(sym)

        # ── Signal 1: Narrative value floor ───────────────────────────────────
        # If PE > ceiling zeroed the value component but PEG is genuinely low
        # AND the narrative is very strong, the high PE is almost certainly an
        # earnings distortion (trough, one-time charge, heavy investment phase)
        # rather than true overvaluation. PEG already adjusts for growth — a
        # low PEG with high PE means earnings are recovering fast.
        # Give a partial value floor so the gem score isn't killed entirely.
        # Floor = 0.25 × narrative (max ~0.25) — surfaces but doesn't inflate.
        if f and n > 0.65 and v < 0.15:
            peg_f  = float(f[1]) if f[1] and float(f[1]) > 0 else None
            pe_fwd = float(f[2]) if f[2] and float(f[2]) > 0 else None
            pe_trl = float(f[3]) if f[3] and float(f[3]) > 0 else None
            pe_val = pe_fwd or pe_trl
            if pe_val and pe_val > PE_CEILING and peg_f and peg_f < 2.5:
                v = max(v, 0.25 * n)

        # ── Narrative gate (core thesis) ───────────────────────────────────────
        # Narrative is not one equal vote — it's the prerequisite.
        # A stock riding a genuine secular tailwind with an accelerating story
        # gets amplified. One with weak or absent narrative gets heavily penalised
        # regardless of how cheap or high-quality the business is.
        #
        # narrative_gate = n^1.5 (steep curve):
        #   n=0.90 → gate=0.854  (strong amplifier)
        #   n=0.70 → gate=0.592  (meaningful drag)
        #   n=0.50 → gate=0.354  (heavy penalty — halves the score)
        #   n=0.30 → gate=0.164  (near-zero — never makes the cut)
        #
        # No exceptions to the narrative gate: a stock earns its place on the
        # board through genuine exposure to a live narrative, or not at all.
        # (The old "value unlock" bypass let FSLR rank #3 with narrative 0.14.)
        narrative_gate = n ** 1.5 if n > 0 else 0.0
        roic_f = float(f[6]) if f and f[6] else 0
        gem = (v * q) ** 0.5 * narrative_gate if (v > 0 and q > 0) else 0.0

        # ── Fundamental momentum gate ──────────────────────────────────────────
        # Core thesis: "cheap AND improving." Both revenue AND earnings declining
        # = potential value trap. One declining is acceptable.
        # Option C: earnings dip alone (revenue still growing) with weak narrative
        # gets a lighter penalty — no story to justify looking through the dip.
        if f:
            rev_gr  = float(f[4]) if f[4] is not None else 0.0
            earn_gr = float(f[8]) if f[8] is not None else 0.0
            if rev_gr < 0 and earn_gr < 0:
                gem *= 0.5
            elif earn_gr < 0 and rev_gr >= 0 and n < 0.40:
                gem *= 0.75

        # ── Mispricing gate ────────────────────────────────────────────────────
        # The thesis is the GAP: a strong narrative alone is not a gem — the
        # market must not have priced it yet. Two multiplicative components:
        #
        # 1. Price-lag gap: ×0.45 (fully priced) → ×1.20 (market clearly lagging).
        #    A stock the market has already repriced gets nearly halved — a
        #    super-strong narrative cannot carry a fully-priced stock on board.
        g = gap.get(sym, 0.50)   # default neutral if no gap data
        gap_mult = 0.45 + 0.75 * g
        gem = min(gem * gap_mult, 1.0)

        # 2. Narrative-peer valuation (the Dell detector, from the brain):
        #    trading at a premium to the peers exposed to the SAME narrative
        #    means the market already believes — penalise. A discount means
        #    the market still prices the legacy category — reward.
        disc = peer_disc.get(sym)
        if disc is not None:
            if disc >= 0:
                gem *= min(1.0 + 0.30 * disc, 1.25)
            else:
                gem *= max(1.0 + 0.60 * disc, 0.55)
        gem = min(gem, 1.0)

        # call_filing_gap: raw normalised gap score for display (0.50 = neutral)
        cfg = call_gap.get(sym, 0.50)

        results.append({
            "symbol":            sym,
            "hidden_gem_score":  round(gem, 4),
            "narrative_score":   round(n, 4),
            "value_score":       round(v, 4),
            "quality_score":     round(q, 4),
            "gap_score":         round(g, 4),
            "call_filing_gap":   round(cfg, 4),   # >0.50 = calls more bullish than filings
            "peg_ratio":         float(f[1]) if f and f[1] else None,
            "pe_forward":        float(f[2]) if f and f[2] else None,
            "pe_trailing":       float(f[3]) if f and f[3] else None,
            "revenue_growth":    float(f[4]) if f and f[4] else None,
            "gross_margin":      float(f[5]) if f and f[5] else None,
            "roic":              float(f[6]) if f and f[6] else None,
            "sector":            f[7] if f else None,
            "earnings_growth":   float(f[8]) if f and f[8] else None,
            "fcf_growth":        float(f[9]) if f and f[9] else None,
            "top_themes":        stock_themes.get(sym, [])[:3],
        })

    results.sort(key=lambda x: x["hidden_gem_score"], reverse=True)
    return results


if __name__ == "__main__":
    engine = get_engine()
    results = score_all_stocks(engine)

    print(f"\n{'='*100}")
    print(f"TOP 30 HIDDEN GEMS  (PE ceiling: {PE_CEILING}x | PEG ceiling: {PEG_CEILING})")
    print(f"{'='*100}")
    print(f"{'#':>3} {'Sym':<6} {'Score':>6} {'Gap':>6} {'Narr':>6} {'Val':>6} {'Qual':>6} "
          f"{'PEG':>5} {'FwdPE':>7} {'RevGr':>7} {'EarnGr':>7}  Top Theme")
    print("-" * 125)

    for i, s in enumerate(results[:30], 1):
        theme = s["top_themes"][0]["theme"] if s["top_themes"] else "-"
        print(
            f"{i:>3} {s['symbol']:<6} {s['hidden_gem_score']:>6.3f} "
            f"{s.get('gap_score', 0):>6.3f} "
            f"{s['narrative_score']:>6.3f} {s['value_score']:>6.3f} {s['quality_score']:>6.3f} "
            f"{s['peg_ratio'] or 0:>5.1f} {s['pe_forward'] or 0:>7.1f} "
            f"{(s['revenue_growth'] or 0)*100:>6.1f}% "
            f"{(s['earnings_growth'] or 0)*100:>6.1f}%  {theme[:45]}"
        )

    # DELL specifically
    dell = next((s for s in results if s["symbol"] == "DELL"), None)
    if dell:
        rank = next(i for i, s in enumerate(results, 1) if s["symbol"] == "DELL")
        print(f"\n{'='*100}")
        print(f"DELL → Rank #{rank} of {len(results)}")
        print(f"  Score: {dell['hidden_gem_score']:.3f}  "
              f"Narrative: {dell['narrative_score']:.3f}  "
              f"Value: {dell['value_score']:.3f}  "
              f"Quality: {dell['quality_score']:.3f}")
        print(f"  PEG: {dell['peg_ratio']}  FwdPE: {dell['pe_forward']}x  "
              f"RevGr: {(dell['revenue_growth'] or 0)*100:.1f}%  "
              f"EarnGr: {(dell['earnings_growth'] or 0)*100:.1f}%")
        print(f"  Themes: {[t['theme'] for t in dell['top_themes']]}")
