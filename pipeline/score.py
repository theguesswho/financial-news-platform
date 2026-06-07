"""
Mismatch Score — flags quality companies the market is underpricing
relative to their fundamental trajectory and thematic context.

Framework:
  Quality     — is this a good business? (ROIC, margins, FCF)
  Value       — is the market underpricing it? (P/E, PEG, EV/EBITDA vs peers)
  Trajectory  — are fundamentals improving? (revenue acceleration, margin trend)
  Theme       — is the company exposed to a growing macro theme?

Mismatch = Quality × Value × Trajectory  (theme acts as a multiplier/filter)

Calibrated so Dell (FY2024, ~10x P/E, ISG revenue +80%, growing AI exposure)
scores ~0.75-0.85 — clearly flagged. Dell today at 52x scores ~0.25.
"""
import json
from typing import Optional

import numpy as np
from sqlalchemy.orm import Session

from db.models import Fundamentals, ScreenerResult, EodPrice


# ── Component weights ─────────────────────────────────────────────────────────

QUALITY_WEIGHTS = {
    "roic":             0.35,   # best single measure of capital efficiency
    "gross_margin":     0.20,   # pricing power / competitive moat
    "operating_margin": 0.20,
    "fcf_margin":       0.15,   # real cash generation
    "debt_safety":      0.10,   # inverse of debt/equity risk
}

VALUE_WEIGHTS = {
    "pe_vs_peers":      0.30,   # percentile rank (lower P/E = higher score)
    "peg":              0.30,   # <1 = growing fast enough to justify price
    "ev_ebitda":        0.20,
    "price_vs_52w":     0.20,   # near 52w low = market bearish = opportunity
}

TRAJECTORY_WEIGHTS = {
    "revenue_acceleration": 0.40,  # is revenue growth speeding up?
    "margin_trend":         0.30,  # are margins expanding?
    "fcf_growth":           0.30,
}


def _clamp(x: float, lo=0.0, hi=1.0) -> float:
    return max(lo, min(hi, x))


def _score_roic(roic: Optional[float]) -> float:
    """ROIC: >20% = excellent, 10-20% = good, <10% = weak."""
    if roic is None: return 0.4
    if roic > 0.25: return 1.0
    if roic > 0.15: return 0.75
    if roic > 0.08: return 0.50
    if roic > 0.0:  return 0.25
    return 0.0


def _score_margin(margin: Optional[float], good: float, great: float) -> float:
    if margin is None: return 0.4
    return _clamp((margin - 0) / (great - 0))


def _score_debt(d_e: Optional[float]) -> float:
    """Lower D/E = safer. >3 = risky, 0 = ideal."""
    if d_e is None: return 0.5
    if d_e <= 0:    return 1.0
    if d_e <= 0.5:  return 0.9
    if d_e <= 1.0:  return 0.75
    if d_e <= 2.0:  return 0.55
    if d_e <= 3.0:  return 0.35
    return 0.1


def _score_peg(peg: Optional[float]) -> float:
    """Lynch: PEG <1 = undervalued relative to growth."""
    if peg is None: return 0.4
    if peg <= 0:    return 0.4   # negative = unprofitable
    if peg < 0.5:   return 1.0
    if peg < 1.0:   return 0.85
    if peg < 1.5:   return 0.65
    if peg < 2.0:   return 0.45
    if peg < 3.0:   return 0.25
    return 0.10


def _percentile_score(value: float, all_values: list[float], lower_is_better=True) -> float:
    """Rank this value within the universe. Returns 0-1."""
    if not all_values or value is None:
        return 0.5
    arr = np.array([v for v in all_values if v is not None])
    if len(arr) == 0:
        return 0.5
    pct = np.mean(arr < value)   # fraction of universe below this value
    return (1 - pct) if lower_is_better else pct


def _score_price_vs_52w(ratio: Optional[float]) -> float:
    """Price near 52w low = market is bearish = potential opportunity."""
    if ratio is None: return 0.5
    # ratio = current / 52w_high.  0.7 = 30% off high = market skeptical
    if ratio < 0.60: return 1.0   # deep discount from high
    if ratio < 0.75: return 0.85
    if ratio < 0.85: return 0.65
    if ratio < 0.92: return 0.45
    return 0.20                   # near all-time high = market already bullish


def _trend_score(values: list[Optional[float]]) -> float:
    """
    Score based on trajectory of a metric over recent quarters.
    Rewards acceleration (growing AND speeding up).
    """
    clean = [v for v in values if v is not None]
    if len(clean) < 3:
        return 0.5

    # Is it growing at all?
    recent_avg = np.mean(clean[-2:])
    prior_avg  = np.mean(clean[:2])

    if prior_avg == 0:
        return 0.5

    growth = (recent_avg - prior_avg) / abs(prior_avg)

    # Is it accelerating? Compare slope of first half vs second half
    mid = len(clean) // 2
    slope_early = clean[mid] - clean[0]
    slope_late  = clean[-1]  - clean[mid]
    accelerating = slope_late > slope_early

    base = _clamp(0.5 + growth * 1.5)
    bonus = 0.15 if accelerating else 0.0
    return _clamp(base + bonus)


def _revenue_acceleration(trends: dict) -> float:
    """Score revenue trajectory — rewards acceleration."""
    rev = trends.get("revenue", [])
    return _trend_score(rev)


def _margin_trend(trends: dict) -> float:
    """Score gross margin trajectory."""
    gm = trends.get("gross_margin", [])
    return _trend_score(gm)


def _fcf_trajectory(trends: dict) -> float:
    """Score FCF trajectory."""
    fcf = trends.get("fcf", [])
    return _trend_score(fcf)


# ── Main scoring function ─────────────────────────────────────────────────────

def compute_mismatch_score(fund: Fundamentals, all_funds: list[Fundamentals]) -> dict:
    """
    Compute the mismatch score for a single stock.
    Returns dict with component scores and overall score (0-1).
    """
    trends = {}
    if fund.quarterly_trends:
        try:
            raw = json.loads(fund.quarterly_trends)
            # Separate _themes metadata from actual trends
            trends = {k: v for k, v in raw.items() if not k.startswith("_")}
        except Exception:
            pass

    # Universe values for percentile scoring
    all_pe  = [float(f.pe_trailing) for f in all_funds if f.pe_trailing and f.pe_trailing > 0]
    all_ev  = [float(f.ev_to_ebitda) for f in all_funds if f.ev_to_ebitda and f.ev_to_ebitda > 0]

    # ── Quality score ──────────────────────────────────────────────────────────
    q = {
        "roic":             _score_roic(float(fund.roic) if fund.roic else None),
        "gross_margin":     _score_margin(float(fund.gross_margin) if fund.gross_margin else None,
                                          good=0.30, great=0.60),
        "operating_margin": _score_margin(float(fund.operating_margin) if fund.operating_margin else None,
                                          good=0.10, great=0.30),
        "fcf_margin":       _score_margin(float(fund.fcf_margin) if fund.fcf_margin else None,
                                          good=0.05, great=0.20),
        "debt_safety":      _score_debt(float(fund.debt_to_equity) if fund.debt_to_equity else None),
    }
    quality = sum(q[k] * QUALITY_WEIGHTS[k] for k in q)

    # ── Value score ────────────────────────────────────────────────────────────
    pe_val  = float(fund.pe_trailing)  if fund.pe_trailing  and fund.pe_trailing > 0  else None
    ev_val  = float(fund.ev_to_ebitda) if fund.ev_to_ebitda and fund.ev_to_ebitda > 0 else None
    peg_val = float(fund.peg_ratio)    if fund.peg_ratio else None
    p52w    = float(fund.price_vs_52w_high) if fund.price_vs_52w_high else None

    v = {
        "pe_vs_peers":  _percentile_score(pe_val, all_pe, lower_is_better=True) if pe_val else 0.4,
        "peg":          _score_peg(peg_val),
        "ev_ebitda":    _percentile_score(ev_val, all_ev, lower_is_better=True) if ev_val else 0.4,
        "price_vs_52w": _score_price_vs_52w(p52w),
    }
    value = sum(v[k] * VALUE_WEIGHTS[k] for k in v)

    # ── Trajectory score ───────────────────────────────────────────────────────
    t = {
        "revenue_acceleration": _revenue_acceleration(trends),
        "margin_trend":         _margin_trend(trends),
        "fcf_growth":           _fcf_trajectory(trends),
    }
    trajectory = sum(t[k] * TRAJECTORY_WEIGHTS[k] for k in t)

    # ── Theme modifier ─────────────────────────────────────────────────────────
    theme_data = {}
    if fund.quarterly_trends:
        try:
            raw = json.loads(fund.quarterly_trends)
            theme_data = raw.get("_themes", {})
        except Exception:
            pass

    theme_multiplier = 1.0
    if theme_data.get("exposure_trend") == "GROWING":
        theme_multiplier = 1.20
    elif theme_data.get("exposure_trend") == "DECLINING":
        theme_multiplier = 0.80

    # ── Final score ────────────────────────────────────────────────────────────
    # Geometric mean rewards balance — a company must score well on ALL three
    base = (quality * value * trajectory) ** (1/3)
    final = _clamp(base * theme_multiplier)

    return {
        "symbol":           fund.symbol,
        "mismatch_score":   round(final, 3),
        "quality":          round(quality, 3),
        "value":            round(value, 3),
        "trajectory":       round(trajectory, 3),
        "theme_multiplier": round(theme_multiplier, 2),
        "components": {
            "quality_detail":     q,
            "value_detail":       v,
            "trajectory_detail":  t,
        },
        "themes": theme_data.get("primary_themes", []),
        "catalyst": theme_data.get("catalyst"),
        "second_order": theme_data.get("second_order_note"),
        "pe": pe_val,
        "peg": peg_val,
        "revenue_growth": float(fund.revenue_growth_yoy) if fund.revenue_growth_yoy else None,
        "roic": float(fund.roic) if fund.roic else None,
    }


def score_all(session: Session) -> list[dict]:
    """Score every stock with fundamentals. Returns list sorted by mismatch_score desc."""
    all_funds = session.query(Fundamentals).all()
    scores = [compute_mismatch_score(f, all_funds) for f in all_funds]
    return sorted(scores, key=lambda x: x["mismatch_score"], reverse=True)


def score_by_theme(session: Session, theme: str) -> list[dict]:
    """Score stocks filtered to a specific theme."""
    all_funds = session.query(Fundamentals).all()
    results = []
    for f in all_funds:
        s = compute_mismatch_score(f, all_funds)
        all_themes = s["themes"]
        if theme.upper() in [t.upper() for t in all_themes]:
            results.append(s)
    return sorted(results, key=lambda x: x["mismatch_score"], reverse=True)


# ─────────────────────────────────────────────────────────────────────────────────
# V2 LIVE SCORING (for current fundamentals, used in screener)
# ─────────────────────────────────────────────────────────────────────────────────

def _classify_live(gross_margin: float | None) -> str:
    """Classify business type from gross margin."""
    if gross_margin is None:     return "mid"
    if gross_margin > 0.40:      return "high"
    if gross_margin < 0.25:      return "low"
    return "mid"


def _quality_score_live(fund: Fundamentals, biz: str) -> float:
    """Compute quality score from current fundamentals."""
    roic = float(fund.roic) if fund.roic else None
    gm   = float(fund.gross_margin) if fund.gross_margin else None
    om   = float(fund.operating_margin) if fund.operating_margin else None
    de   = float(fund.debt_to_equity) if fund.debt_to_equity else None

    q_roic = _score_roic(roic)
    q_gm   = _score_margin(gm, 0.30, 0.60)
    q_om   = _score_margin(om, 0.10, 0.30)
    q_debt = _score_debt(de)

    if biz == "high":
        return q_roic*0.40 + q_gm*0.20 + q_om*0.20 + q_debt*0.20
    elif biz == "low":
        return q_roic*0.08 + q_gm*0.12 + q_om*0.45 + q_debt*0.35
    else:
        return q_roic*0.25 + q_gm*0.17 + q_om*0.33 + q_debt*0.25


def _value_score_live(fund: Fundamentals, all_pes: list[float], all_pfcf: list[float],
                      price_vs_high: float | None, biz: str) -> float:
    """Compute value score from current fundamentals."""
    pe    = float(fund.pe_trailing) if fund.pe_trailing and float(fund.pe_trailing) > 0 else None
    pfcf  = float(fund.price_to_fcf) if fund.price_to_fcf and float(fund.price_to_fcf) > 0 else None
    pb    = float(fund.price_to_book) if fund.price_to_book else 1.0
    pb_penalty = 0.85 if pb < 0 else 1.0

    pe_score   = _percentile_score(pe, all_pes, lower_is_better=True) if pe else 0.40
    high_score = _score_price_vs_52w(price_vs_high)
    pfcf_score = _percentile_score(
        pfcf, all_pfcf or [15], lower_is_better=True
    ) if pfcf else 0.40

    # Updated weights: PE 30%, P/FCF 30%, Price vs 52w 20%, implicit buffer 20%
    if biz == "low":
        # Asset-heavy: FCF matters more
        raw = pe_score*0.25 + pfcf_score*0.40 + high_score*0.25 + 0.10
    elif biz == "high":
        # Software: PE and price momentum matter more
        raw = pe_score*0.30 + high_score*0.25 + pfcf_score*0.30 + 0.15
    else:
        # Mid-margin blend
        raw = pe_score*0.30 + pfcf_score*0.30 + high_score*0.25 + 0.15

    return raw * pb_penalty


def _margin_trend_from_quarterly(quarterly_trends_json: str | dict | None) -> tuple[float, float | None]:
    """
    Calculate margin trend from quarterly data (gross_margin + operating_margin).
    Requires minimum 6 quarters. Compares most recent quarters to older periods.
    Returns (trend_score, margin_change_pp) where:
      - trend_score: 0-1, higher = expanding margins
      - margin_change_pp: average pp change in (GM + OM) / 2
    """
    if not quarterly_trends_json:
        return 0.5, None

    try:
        if isinstance(quarterly_trends_json, str):
            data = json.loads(quarterly_trends_json)
        else:
            data = quarterly_trends_json

        gm_list = data.get("gross_margin", [])
        om_list = data.get("operating_margin", [])

        # Filter out None values and require at least 5 non-None quarters
        gm_clean = [v for v in gm_list if v is not None]
        om_clean = [v for v in om_list if v is not None]

        if len(gm_clean) < 5 or len(om_clean) < 5:
            return 0.5, None

        # Use most recent quarters vs earlier ones
        # Current: last 2 quarter average (to smooth out quarterly noise)
        curr_gm = (gm_clean[-1] + gm_clean[-2]) / 2 if len(gm_clean) >= 2 else gm_clean[-1]
        curr_om = (om_clean[-1] + om_clean[-2]) / 2 if len(om_clean) >= 2 else om_clean[-1]

        # Historical: 4-5 quarters back (or from beginning if fewer)
        hist_idx = max(0, len(gm_clean) - 5)
        hist_gm = gm_clean[hist_idx]
        hist_om = om_clean[hist_idx]

        # Average change across two main margins (in percentage points)
        gm_change = (curr_gm - hist_gm)
        om_change = (curr_om - hist_om)
        avg_change = (gm_change + om_change) / 2

        # Map change in percentage points to score
        if avg_change > 0.10:      score = 1.00   # +10pp or more expansion
        elif avg_change > 0.05:    score = 0.90   # +5-10pp expansion
        elif avg_change > 0.02:    score = 0.75   # +2-5pp expansion
        elif avg_change > -0.02:   score = 0.55   # Roughly flat (±2pp)
        elif avg_change > -0.05:   score = 0.40   # -2-5pp compression
        elif avg_change > -0.10:   score = 0.25   # -5-10pp compression
        else:                       score = 0.10   # -10pp or more compression

        return score, avg_change

    except Exception:
        return 0.5, None


def _traj_score_live(rev_growth: float | None, fcf_growth: float | None,
                     margin_trend: float | None, biz: str) -> float:
    """
    Compute trajectory score from current fundamentals.
    Weights: Revenue growth 35%, FCF growth 35%, Margin trend 30%
    """
    # Revenue growth score
    if rev_growth is None:
        rev_score = 0.50
    elif biz == "low":
        if rev_growth > 0.40: rev_score = 1.00
        elif rev_growth > 0.20: rev_score = 0.85
        elif rev_growth > 0.08: rev_score = 0.70
        elif rev_growth > 0.00: rev_score = 0.55
        elif rev_growth > -0.08: rev_score = 0.38
        else: rev_score = 0.20
    else:
        if rev_growth > 0.50: rev_score = 1.00
        elif rev_growth > 0.30: rev_score = 0.90
        elif rev_growth > 0.15: rev_score = 0.75
        elif rev_growth > 0.05: rev_score = 0.60
        elif rev_growth > 0.00: rev_score = 0.50
        elif rev_growth > -0.10: rev_score = 0.35
        else: rev_score = 0.20

    # FCF growth score (especially important for growth companies turning profitable)
    if fcf_growth is None:
        fcf_score = 0.50
    else:
        if fcf_growth > 1.00: fcf_score = 1.00    # Explosive FCF growth
        elif fcf_growth > 0.50: fcf_score = 0.90  # Strong FCF growth
        elif fcf_growth > 0.20: fcf_score = 0.75  # Solid growth
        elif fcf_growth > 0.00: fcf_score = 0.60  # Growing from small base
        elif fcf_growth > -0.10: fcf_score = 0.40 # Flat/slightly declining
        else: fcf_score = 0.20                    # Significant decline

    # Margin trend score (0-1, where 1.0 = strong expansion, 0.5 = flat, 0.0 = compression)
    margin_score = margin_trend if margin_trend is not None else 0.50

    # Combine: 35% revenue, 35% FCF growth, 30% margin trend
    return rev_score * 0.35 + fcf_score * 0.35 + margin_score * 0.30


def compute_v2_score_with_breakdown(fund: Fundamentals, session: Session) -> dict:
    """
    Compute V2 score AND return full breakdown of components.
    Returns dict with final score + all intermediate calculations for display.
    """
    if not fund or not fund.market_cap or not fund.fifty_two_week_high:
        return {
            "final_score": 0.0,
            "quality_score": 0.0,
            "value_score": 0.0,
            "trajectory_score": 0.0,
            "business_type": "unknown",
            "breakdown": {
                "quality": {},
                "value": {},
                "trajectory": {},
            }
        }

    biz = _classify_live(float(fund.gross_margin) if fund.gross_margin else None)

    # Quality components
    roic = float(fund.roic) if fund.roic else None
    gm = float(fund.gross_margin) if fund.gross_margin else None
    om = float(fund.operating_margin) if fund.operating_margin else None
    de = float(fund.debt_to_equity) if fund.debt_to_equity else None

    q_roic = _score_roic(roic)
    q_gm = _score_margin(gm, 0.30, 0.60)
    q_om = _score_margin(om, 0.10, 0.30)
    q_debt = _score_debt(de)
    quality = _quality_score_live(fund, biz)

    # Value components
    pe = float(fund.pe_trailing) if fund.pe_trailing and float(fund.pe_trailing) > 0 else None
    pfcf = float(fund.price_to_fcf) if fund.price_to_fcf and float(fund.price_to_fcf) > 0 else None
    pb = float(fund.price_to_book) if fund.price_to_book else 1.0

    latest_price = None
    latest = session.query(EodPrice).filter_by(symbol=fund.symbol).order_by(EodPrice.date.desc()).first()
    if latest:
        latest_price = float(latest.close)

    price_vs_high = latest_price / float(fund.fifty_two_week_high) if latest_price and fund.fifty_two_week_high else None

    all_pes = [float(f.pe_trailing) for f in session.query(Fundamentals).all() if f.pe_trailing and float(f.pe_trailing) > 0]
    all_pfcf = [float(f.price_to_fcf) for f in session.query(Fundamentals).all() if f.price_to_fcf and float(f.price_to_fcf) > 0]

    # Component scores for breakdown
    pe_score = _percentile_score(pe, all_pes, lower_is_better=True) if pe else 0.40
    pfcf_score = _percentile_score(pfcf, all_pfcf or [15], lower_is_better=True) if pfcf else 0.40
    high_score = _score_price_vs_52w(price_vs_high)

    value = _value_score_live(fund, all_pes, all_pfcf, price_vs_high, biz)

    # Trajectory
    rev_growth = float(fund.revenue_growth_yoy) if fund.revenue_growth_yoy else None
    fcf_growth = float(fund.fcf_growth_yoy) if fund.fcf_growth_yoy else None
    margin_trend_score, margin_change_pp = _margin_trend_from_quarterly(fund.quarterly_trends)
    trajectory = _traj_score_live(rev_growth, fcf_growth, margin_trend_score, biz)

    # Final score
    final = _clamp((quality * value * trajectory) ** (1/3))

    return {
        "final_score": final,
        "quality_score": quality,
        "value_score": value,
        "trajectory_score": trajectory,
        "business_type": biz,
        "breakdown": {
            "quality": {
                "roic": {"value": roic, "score": q_roic},
                "gross_margin": {"value": gm, "score": q_gm},
                "operating_margin": {"value": om, "score": q_om},
                "debt_to_equity": {"value": de, "score": q_debt},
            },
            "value": {
                "pe_ratio": {"value": pe, "score": pe_score},
                "pfcf_ratio": {"value": pfcf, "score": pfcf_score},
                "price_vs_52w": {"value": price_vs_high, "score": high_score},
                "pb_ratio": {"value": pb},
            },
            "trajectory": {
                "revenue_growth_yoy": {"value": rev_growth},
                "fcf_growth_yoy": {"value": fcf_growth},
                "margin_trend": {"score": margin_trend_score, "change_pp": margin_change_pp},
            }
        }
    }


def compute_v2_score(fund: Fundamentals, session: Session) -> float:
    """
    Compute V2 (sector-aware) mismatch score from current fundamentals.
    Returns float 0-1.
    Used by the live screener to rank stocks.
    """
    if not fund or not fund.market_cap or not fund.fifty_two_week_high:
        return 0.0

    # Business type from gross margin
    biz = _classify_live(float(fund.gross_margin) if fund.gross_margin else None)

    # Price vs 52-week high
    price_vs_high = None
    if fund.fifty_two_week_high and fund.fifty_two_week_high > 0:
        # Get latest price
        from db.models import EodPrice
        latest = (
            session.query(EodPrice)
            .filter_by(symbol=fund.symbol)
            .order_by(EodPrice.date.desc())
            .first()
        )
        if latest and latest.close:
            price_vs_high = float(latest.close) / float(fund.fifty_two_week_high)

    # Revenue growth & FCF growth YoY (from fundamentals)
    rev_growth = float(fund.revenue_growth_yoy) if fund.revenue_growth_yoy else None
    fcf_growth = float(fund.fcf_growth_yoy) if fund.fcf_growth_yoy else None

    # All PEs and P/FCF for percentile scoring
    all_funds = session.query(Fundamentals).all()
    all_pes = [
        float(f.pe_trailing) for f in all_funds
        if f.pe_trailing and float(f.pe_trailing) > 0
    ]
    all_pfcf = [
        float(f.price_to_fcf) for f in all_funds
        if f.price_to_fcf and float(f.price_to_fcf) > 0
    ]

    # Component scores
    quality = _quality_score_live(fund, biz)
    value   = _value_score_live(fund, all_pes, all_pfcf, price_vs_high, biz)
    margin_trend_score, _ = _margin_trend_from_quarterly(fund.quarterly_trends)
    traj    = _traj_score_live(rev_growth, fcf_growth, margin_trend_score, biz)

    # Geometric mean
    return _clamp((quality * value * traj) ** (1/3))
