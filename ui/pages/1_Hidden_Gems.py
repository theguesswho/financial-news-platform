"""
Hidden Gem Leaderboard — your daily conviction check.

Tier 1: Strong Buy  (gem > 0.60)
Tier 2: Buy         (0.52 – 0.60)
Tier 3: Watch       (0.47 – 0.52)

Top 25 stocks have been qualitatively assessed by Claude Sonnet
with specific bull/bear write-ups and tier adjustments.
The remaining universe is ranked by raw gem score.
"""

import sys
import json
from pathlib import Path
from datetime import datetime

import html as html_lib

import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import text

root = Path(__file__).parent.parent
sys.path.insert(0, str(root))
load_dotenv(root / ".env", override=True)

from pipeline.hidden_gem_scorer import get_engine, score_all_stocks
from db.session import get_session
from db.models import WatchlistEntry

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="Hidden Gem Leaderboard", page_icon="💎", layout="wide")

st.markdown("""
<style>
/* Layout */
.block-container { max-width: 1080px; padding: 3.5rem 2rem 4rem; }
header[data-testid="stHeader"] { display: none; }

/* Page header */
.page-header {
    display: flex; justify-content: space-between; align-items: flex-end;
    margin-bottom: 1.75rem;
}
.page-title   { font-size: 1.75rem; font-weight: 800; color: #0f172a; }
.page-subtitle { font-size: 0.85rem; color: #64748b; margin-top: 0.2rem; }
.page-date    { font-size: 0.8rem; color: #94a3b8; text-align: right; }

/* Tier section header */
.tier-header {
    font-size: 0.72rem; font-weight: 800; letter-spacing: 0.1em;
    text-transform: uppercase; padding: 0.3rem 0.6rem;
    border-radius: 4px; display: inline-block; margin: 1.5rem 0 0.75rem;
}
.tier-strong-buy { background: #fef2f2; color: #991b1b; }
.tier-buy        { background: #f0fdf4; color: #166534; }
.tier-watch      { background: #fefce8; color: #854d0e; }
.tier-unassessed { background: #f8fafc; color: #475569; }

/* Stock card */
.stock-card {
    border: 1px solid #e2e8f0; border-radius: 12px;
    padding: 1rem 1.25rem; margin-bottom: 0.65rem;
    display: flex; gap: 1.25rem; align-items: flex-start;
    transition: border-color 0.15s;
}
.stock-card:hover { border-color: #94a3b8; }
.stock-card.strong-buy { border-left: 4px solid #ef4444; }
.stock-card.buy        { border-left: 4px solid #22c55e; }
.stock-card.watch      { border-left: 4px solid #eab308; }

/* Rank */
.rank { font-size: 0.75rem; font-weight: 700; color: #cbd5e1;
        min-width: 28px; padding-top: 0.3rem; text-align: right; }

/* Score block */
.score-block { min-width: 90px; text-align: center; }
.gem-score   { font-size: 1.5rem; font-weight: 800; color: #0f172a; line-height: 1; }
.gem-tier    { font-size: 0.68rem; font-weight: 700; letter-spacing: 0.05em;
               text-transform: uppercase; margin-top: 0.3rem; }
.tier-label-strong-buy { color: #ef4444; }
.tier-label-buy        { color: #16a34a; }
.tier-label-watch      { color: #ca8a04; }

/* Direction badge */
.direction-badge {
    display: inline-block; font-size: 0.65rem; font-weight: 700;
    padding: 0.15rem 0.4rem; border-radius: 3px; margin-left: 0.4rem;
    vertical-align: middle; letter-spacing: 0.04em;
}
.dir-upgrade   { background: #dcfce7; color: #166534; }
.dir-downgrade { background: #fee2e2; color: #991b1b; }

/* Stock info */
.stock-info { flex: 1; }
.stock-symbol   { font-size: 1.05rem; font-weight: 800; color: #0f172a; }
.stock-company  { font-size: 0.8rem; color: #64748b; margin-bottom: 0.5rem; }
.bull-bear      { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-top: 0.5rem; }
.bull-point, .bear-point {
    font-size: 0.8rem; line-height: 1.45; padding: 0.4rem 0.6rem; border-radius: 6px;
}
.bull-point { background: #f0fdf4; color: #166534; }
.bear-point { background: #fef2f2; color: #991b1b; }
.bull-label, .bear-label {
    font-size: 0.65rem; font-weight: 800; letter-spacing: 0.06em;
    text-transform: uppercase; margin-bottom: 0.2rem;
}
.rationale { font-size: 0.8rem; color: #475569; line-height: 1.5;
             margin-top: 0.4rem; font-style: italic; }

/* Score pills */
.score-pills { display: flex; gap: 0.4rem; flex-wrap: wrap; margin-top: 0.5rem; }
.score-pill  {
    font-size: 0.68rem; font-weight: 600; padding: 0.1rem 0.45rem;
    border-radius: 12px; background: #f1f5f9; color: #475569;
}

/* Sub-score bars */
.sub-scores { margin-top: 0.5rem; }
.sub-score-row { display: flex; align-items: center; gap: 0.5rem;
                 font-size: 0.72rem; color: #64748b; margin-bottom: 0.2rem; }
.sub-score-label { min-width: 70px; font-weight: 600; }
.sub-score-bar   { flex: 1; background: #f1f5f9; border-radius: 4px; height: 6px; }
.sub-score-fill  { height: 6px; border-radius: 4px; background: #3b82f6; }
.sub-score-val   { min-width: 36px; text-align: right; font-weight: 700; color: #0f172a; }

/* Watchlist pill */
.wl-pill {
    display: inline-block; background: #eff6ff; border: 1px solid #bfdbfe;
    border-radius: 20px; padding: 0.15rem 0.55rem;
    font-size: 0.72rem; font-weight: 700; color: #1d4ed8; margin-left: 0.5rem;
}

/* Summary stats bar */
.stats-bar {
    display: flex; gap: 1.5rem; padding: 0.75rem 1.25rem;
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px;
    margin-bottom: 1.5rem;
}
.stat-item { text-align: center; }
.stat-num  { font-size: 1.3rem; font-weight: 800; color: #0f172a; }
.stat-lbl  { font-size: 0.68rem; font-weight: 600; text-transform: uppercase;
             letter-spacing: 0.06em; color: #94a3b8; }
</style>
""", unsafe_allow_html=True)

# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def load_gem_scores():
    """Read today's scored universe from leaderboard_history — fast DB read."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT symbol, gem_score,
                   narrative_score, value_score, quality_score, gap_score,
                   COALESCE(qual_promoted, FALSE), gem_adjusted, assessed_tier
            FROM leaderboard_history
            WHERE date = (SELECT MAX(date) FROM leaderboard_history)
        """)).fetchall()
    return [
        {
            "symbol":          r[0],
            "hidden_gem_score": float(r[1]),
            "narrative_score":  float(r[2]) if r[2] is not None else 0.0,
            "value_score":      float(r[3]) if r[3] is not None else 0.0,
            "quality_score":    float(r[4]) if r[4] is not None else 0.0,
            "gap_score":        float(r[5]) if r[5] is not None else 0.0,
            "qual_promoted":    bool(r[6]),
            "gem_adjusted":     float(r[7]) if r[7] is not None else None,
            "promoted_tier":    r[8],
        }
        for r in rows
    ]

@st.cache_data(ttl=300, show_spinner=False)
def load_overrides():
    """Narrative-override details (rationale/evidence) for qual-promoted stocks."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT symbol, narrative_raw, narrative_adjusted, rationale,
                   evidence, key_bull, key_bear, assessed_at
            FROM narrative_overrides WHERE promoted
        """)).fetchall()
    return {r[0]: {
        "narrative_raw":      float(r[1]) if r[1] is not None else None,
        "narrative_adjusted": float(r[2]) if r[2] is not None else None,
        "rationale":          r[3],
        "evidence":           r[4],
        "key_bull":           r[5],
        "key_bear":           r[6],
        "assessed_at":        r[7],
    } for r in rows}

@st.cache_data(ttl=1800, show_spinner=False)
def load_buffett_tiers():
    """Load Buffett tier from deep_dives table for all stocks."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT symbol,
                   content_json->>'buffett_tier'      AS buffett_tier,
                   content_json->>'buffett_rationale' AS buffett_rationale
            FROM deep_dives
        """)).fetchall()
    return {r[0]: {"tier": r[1], "rationale": r[2]} for r in rows if r[1]}

@st.cache_data(ttl=300, show_spinner=False)
def load_qual_assessments():
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT symbol, gem_score, raw_tier, adjusted_tier,
                   direction, rationale, key_bull, key_bear, assessed_at
            FROM qual_assessments
        """)).fetchall()
    return {r[0]: {
        "gem_score":     float(r[1]) if r[1] else None,
        "raw_tier":      r[2],
        "adjusted_tier": r[3],
        "direction":     r[4],
        "rationale":     r[5],
        "key_bull":      r[6],
        "key_bear":      r[7],
        "assessed_at":   r[8],
    } for r in rows}

@st.cache_data(ttl=300, show_spinner=False)
def load_prev_leaderboard():
    """Load previous day's leaderboard ranks for new-entrant and rank-change badges."""
    from pipeline.leaderboard_archiver import get_prev_leaderboard
    engine = get_engine()
    return get_prev_leaderboard(engine)

@st.cache_data(ttl=300, show_spinner=False)
def load_first_board_dates():
    """First-EVER board appearance per symbol (V2 #11): the ★ NEW badge means
    'first time on the board', full stop. A veteran knocked off for a day by
    churn and re-entering is NOT new (MCK case, 2026-07-28)."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT symbol, MIN(date) FROM leaderboard_history
            WHERE tier IS NOT NULL GROUP BY symbol
        """)).fetchall()
        snap_date = conn.execute(text(
            "SELECT MAX(date) FROM leaderboard_history")).scalar()
    return {r[0]: r[1] for r in rows}, snap_date

@st.cache_data(ttl=3600, show_spinner=False)
def load_company_names():
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT symbol, company_name FROM fundamentals WHERE company_name IS NOT NULL")).fetchall()
    return {r[0]: r[1] for r in rows if r[1]}

@st.cache_resource
def get_db():
    return get_session()

_UID = 3  # single-user app

def get_watchlist():
    # Cached session outlives its DB connection (Railway proxy idle-kills it);
    # a failed query then poisons the transaction and every rerun raises
    # PendingRollbackError. Rollback first (no-op when clean), retry once.
    session = get_db()
    for attempt in range(2):
        try:
            session.rollback()
            return {w.symbol for w in session.query(WatchlistEntry).filter_by(user_id=_UID).all()}
        except Exception:
            if attempt == 1:
                return set()   # degrade gracefully — page renders without watchlist stars
            try:
                session.rollback()
            except Exception:
                pass

def go_to_stock(symbol):
    st.session_state["detail_symbol"] = symbol
    st.switch_page("pages/5_Stock_Detail.py")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 💎 Leaderboard")
    st.markdown("---")

    st.markdown("**Filter by tier**")
    _show_sb  = st.checkbox("🔥 Strong Buy", value=True)
    _show_buy = st.checkbox("✅ Buy",         value=True)
    _show_wch = st.checkbox("👀 Watch",       value=True)
    _tier_set = (
        ({"Strong Buy"} if _show_sb  else set()) |
        ({"Buy"}        if _show_buy else set()) |
        ({"Watch"}      if _show_wch else set())
    )

    st.markdown("**Filter by attribute**")
    _only_assessed = st.checkbox("Claude assessed only", value=False)
    _only_new      = st.checkbox("★ New entrants only",  value=False)
    _only_buffett  = st.checkbox("🏆 Buffett tier only",  value=False)

    show_all  = st.checkbox("Show full universe (all 498)", value=False)

    st.markdown("---")
    st.markdown("**Your Watchlist**")
    session = get_db()
    watchlist_syms = get_watchlist()
    if watchlist_syms:
        for sym in sorted(watchlist_syms):
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**{sym}**")
            if c2.button("×", key=f"rm_{sym}"):
                session.query(WatchlistEntry).filter_by(user_id=_UID, symbol=sym).delete()
                session.commit()
                st.cache_data.clear()
                st.rerun()
    else:
        st.caption("No stocks added yet.")

    new_sym = st.text_input("Add to watchlist", placeholder="e.g. NVDA",
                             label_visibility="collapsed")
    if st.button("＋ Add", use_container_width=True) and new_sym:
        clean = new_sym.strip().upper()
        if not session.query(WatchlistEntry).filter_by(user_id=_UID, symbol=clean).first():
            session.add(WatchlistEntry(user_id=_UID, symbol=clean))
            session.commit()
        st.rerun()

    st.markdown("---")
    if st.button("🔄 Refresh scores", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("Scores refresh automatically every hour.\nData from FMP, SEC EDGAR, Claude AI.")

# ── Load data ─────────────────────────────────────────────────────────────────
with st.spinner("Loading scores…"):
    gems          = load_gem_scores()
    qual          = load_qual_assessments()
    companies     = load_company_names()
    watchlist     = get_watchlist()
    prev_rank_map = load_prev_leaderboard()
    buffett_tiers = load_buffett_tiers()
    overrides     = load_overrides()

# ── Helper fns ────────────────────────────────────────────────────────────────
from pipeline.tiers import tier_for

def tier_css(tier):
    return {"Strong Buy": "strong-buy", "Buy": "buy", "Watch": "watch"}.get(tier, "")

def tier_label_css(tier):
    return {"Strong Buy": "tier-label-strong-buy",
            "Buy": "tier-label-buy",
            "Watch": "tier-label-watch"}.get(tier, "")

def tier_emoji(tier):
    return {"Strong Buy": "🔥", "Buy": "✅", "Watch": "👀"}.get(tier, "–")

def fmt_score(v):
    return f"{v:.3f}" if v is not None else "—"

def bar_html(val, color="#3b82f6"):
    pct = int((val or 0) * 100)
    return (f'<div class="sub-score-bar">'
            f'<div class="sub-score-fill" style="width:{pct}%;background:{color}"></div>'
            f'</div>')

# ── Merge qual into gems ───────────────────────────────────────────────────────
for g in gems:
    q = qual.get(g["symbol"])
    raw_tier = tier_for(g["hidden_gem_score"])
    ov = overrides.get(g["symbol"]) if g.get("qual_promoted") else None
    g["display_score"] = g["hidden_gem_score"]
    if ov and g.get("promoted_tier") in ("Strong Buy", "Buy", "Watch"):
        # Narrative-override promotion: quant-qualified stock whose company-level
        # narrative the macro/sector library can't see. Adjusted score drives
        # display; raw score stays visible on the card.
        g["display_tier"]   = g["promoted_tier"]
        g["display_score"]  = g["gem_adjusted"] or g["hidden_gem_score"]
        g["direction"]      = "promoted"
        g["rationale"]      = ov["rationale"]
        g["key_bull"]       = ov["key_bull"]
        g["key_bear"]       = ov["key_bear"]
        g["assessed"]       = True
    elif q and raw_tier:
        # Use Claude's adjusted tier, but only if raw score still clears the Watch floor.
        # Prevents a stale qual assessment keeping a stock visible after its score dropped.
        # Assessor can return the string 'None' = "not even Watch" — off board
        g["display_tier"]  = q["adjusted_tier"] if q["adjusted_tier"] in ("Strong Buy", "Buy", "Watch") else None
        g["direction"]     = q["direction"]
        g["rationale"]     = q["rationale"]
        g["key_bull"]      = q["key_bull"]
        g["key_bear"]      = q["key_bear"]
        g["assessed"]      = True
    elif raw_tier:
        g["display_tier"]  = raw_tier
        g["direction"]     = "hold"
        g["rationale"]     = None
        g["key_bull"]      = None
        g["key_bear"]      = None
        g["assessed"]      = False
    else:
        g["display_tier"]  = None
        g["direction"]     = "hold"
        g["rationale"]     = None
        g["key_bull"]      = None
        g["key_bear"]      = None
        g["assessed"]      = False

# ── Compute rank changes vs previous session ──────────────────────────────────
TIER_ORDER = {"Strong Buy": 0, "Buy": 1, "Watch": 2, None: 3}

prev_on_board = set(prev_rank_map.keys())

# Current ranked list (display_tier != None), in display order
current_ranked = sorted(
    [g for g in gems if g["display_tier"] is not None],
    key=lambda g: (TIER_ORDER.get(g["display_tier"], 3), -g["display_score"])
)
current_rank_map = {g["symbol"]: i + 1 for i, g in enumerate(current_ranked)}

# Tag each gem with movement metadata.
# ★ NEW = FIRST-EVER board appearance is the current snapshot (V2 #11 fix,
# 2026-07-28): survives refreshes all day, and a veteran that flapped off for
# a day and returned is never relabeled new.
first_dates, _snap_date = load_first_board_dates()
for g in gems:
    sym = g["symbol"]
    cur_rank = current_rank_map.get(sym)
    prv_rank = prev_rank_map.get(sym)
    if cur_rank is None:
        g["rank_change"] = None
        g["is_new"]      = False
        continue
    g["is_new"] = bool(_snap_date and first_dates.get(sym) == _snap_date)
    if prv_rank is not None and not g["is_new"]:
        g["rank_change"] = prv_rank - cur_rank   # positive = moved up
    else:
        g["rank_change"] = None

# Apply tier filter
filtered = sorted(gems, key=lambda g: (
    TIER_ORDER.get(g["display_tier"], 3),
    -g["display_score"]
))
filtered = [g for g in filtered if g["display_tier"] in _tier_set]
if _only_assessed:
    filtered = [g for g in filtered if g.get("assessed")]
if _only_new:
    filtered = [g for g in filtered if g.get("is_new")]
if _only_buffett:
    filtered = [g for g in filtered if buffett_tiers.get(g["symbol"], {}).get("tier") in ("Buffett Stock", "Potential Buffett")]

# ── Page header ───────────────────────────────────────────────────────────────
today_str = datetime.utcnow().strftime("%A, %B %d, %Y")
n_strong   = sum(1 for g in gems if g["display_tier"] == "Strong Buy")
n_buy      = sum(1 for g in gems if g["display_tier"] == "Buy")
n_watch    = sum(1 for g in gems if g["display_tier"] == "Watch")
n_assessed = sum(1 for g in gems if g["assessed"])
n_new      = sum(1 for g in gems if g.get("is_new"))
n_buffett  = sum(1 for g in gems if buffett_tiers.get(g["symbol"], {}).get("tier") == "Buffett Stock")

st.markdown(f"""
<div class="page-header">
  <div>
    <div class="page-title">💎 Hidden Gem Leaderboard</div>
    <div class="page-subtitle">
      Stocks benefiting from accelerating macro themes, priced as if they aren't
    </div>
  </div>
  <div class="page-date">{today_str}</div>
</div>

<div class="stats-bar">
  <div class="stat-item">
    <div class="stat-num" style="color:#ef4444">{n_strong}</div>
    <div class="stat-lbl">🔥 Strong Buy</div>
  </div>
  <div class="stat-item">
    <div class="stat-num" style="color:#16a34a">{n_buy}</div>
    <div class="stat-lbl">✅ Buy</div>
  </div>
  <div class="stat-item">
    <div class="stat-num" style="color:#ca8a04">{n_watch}</div>
    <div class="stat-lbl">👀 Watch</div>
  </div>
  <div class="stat-item">
    <div class="stat-num">{n_assessed}</div>
    <div class="stat-lbl">Claude assessed</div>
  </div>
  <div class="stat-item">
    <div class="stat-num" style="color:#6b21a8">{n_new}</div>
    <div class="stat-lbl">★ New entrants</div>
  </div>
  <div class="stat-item">
    <div class="stat-num" style="color:#92400e">{n_buffett}</div>
    <div class="stat-lbl">🏆 Buffett Stocks</div>
  </div>
  <div class="stat-item">
    <div class="stat-num">{len(gems)}</div>
    <div class="stat-lbl">Universe</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Track record: weekly $1,000 Strong Buy lots vs paired SPY twins ──────────
@st.cache_data(ttl=900)
def load_scorecard():
    try:
        from pipeline.track_record import get_scorecard
        return get_scorecard(get_engine())
    except Exception:
        return None

_sc = load_scorecard()
if _sc and _sc["n_lots"]:
    _pdelta = _sc["portfolio_return_pct"] - _sc["spy_return_pct"]
    _pcol = "#16a34a" if _pdelta >= 0 else "#dc2626"
    st.markdown(f"""
<div class="stats-bar" style="margin-top:0.5rem; background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px;">
  <div class="stat-item">
    <div class="stat-num" style="color:{_pcol}">{_sc['portfolio_return_pct']:+.1f}%</div>
    <div class="stat-lbl">📈 Strong Buy portfolio</div>
  </div>
  <div class="stat-item">
    <div class="stat-num">{_sc['spy_return_pct']:+.1f}%</div>
    <div class="stat-lbl">S&P 500 (paired)</div>
  </div>
  <div class="stat-item">
    <div class="stat-num" style="color:{_pcol}">{_pdelta:+.1f}pp</div>
    <div class="stat-lbl">Edge vs index</div>
  </div>
  <div class="stat-item">
    <div class="stat-num">{_sc['lots_beating_spy']}/{_sc['n_lots']}</div>
    <div class="stat-lbl">Lots beating SPY</div>
  </div>
  <div class="stat-item">
    <div class="stat-num">{_sc['entry_lots_beating']}/{_sc['n_entry_lots']}</div>
    <div class="stat-lbl">Entry signals beating</div>
  </div>
</div>
<div style="font-size:0.72rem; color:#94a3b8; margin:0.3rem 0 1rem;">
Track record (v2 era): USD 1,000 into every Strong Buy each week, each lot paired with a
same-day USD 1,000 SPY twin. Buy-and-hold, recorded picks only — never reconstructed.
Started {_sc['lots'][0]['lot_date'].strftime('%b %d, %Y')} · USD {_sc['total_invested']:,.0f}
deployed. The v1-era record (Jun 22 – Jul 21, 2026) is archived, not deleted.
</div>""", unsafe_allow_html=True)

    with st.expander("📊 Holdings breakdown — every lot vs its SPY twin"):
        _by_sym = {}
        for l in _sc["lots"]:
            b = _by_sym.setdefault(l["symbol"], {"lots": 0, "inv": 0.0, "val": 0.0, "spy": 0.0})
            b["lots"] += 1
            b["inv"] += l["invested"]
            b["val"] += l["stock_value"]
            b["spy"] += l["spy_value"]

        _names = load_company_names()
        _hold = pd.DataFrame([{
            "Stock": f"{s} — {_names.get(s, '')}"[:44],
            "Weeks bought": b["lots"],
            "Invested": b["inv"],
            "Value now": round(b["val"], 0),
            "Our return %": round((b["val"] / b["inv"] - 1) * 100, 1),
            "Same $ in S&P %": round((b["spy"] / b["inv"] - 1) * 100, 1),
            "Pick's edge (pp)": round((b["val"] - b["spy"]) / b["inv"] * 100, 1),
        } for s, b in _by_sym.items()]).sort_values("Invested", ascending=False)
        st.markdown("**By stock** — weekly buys accumulate while a stock stays Strong Buy; "
                    "buying stops when it drops out, holdings are kept.")
        st.dataframe(_hold, use_container_width=True, hide_index=True)

        _lotdf = pd.DataFrame([{
            "Week": l["lot_date"].strftime("%b %d"),
            "Stock": l["symbol"],
            "Entry signal": "★" if l["is_entry"] else "",
            "Stock value": l["stock_value"],
            "S&P twin value": l["spy_value"],
            "Edge (pp)": l["vs_spy_pct"],
            "Beating": "✓" if l["beat"] else "✗",
        } for l in _sc["lots"]])
        st.markdown("**Every lot**: USD 1,000 in the stock and USD 1,000 in the S&P, bought the same day. "
                    "'Edge' = stock value minus twin value, as % of the 1,000. ★ = week the stock first became Strong Buy.")
        st.dataframe(_lotdf, use_container_width=True, hide_index=True)

# ── Render stock cards ────────────────────────────────────────────────────────
display_stocks = filtered if show_all else [g for g in filtered if g["display_tier"] is not None]

TIER_BORDER = {"Strong Buy": "#ef4444", "Buy": "#22c55e", "Watch": "#eab308"}
TIER_BG     = {"Strong Buy": "#fff5f5", "Buy": "#f0fdf4", "Watch": "#fefce8"}

current_tier = None
rank = 0

for g in display_stocks:
    tier  = g["display_tier"]
    score = g["display_score"]

    # Tier section header
    if tier != current_tier:
        current_tier = tier
        if tier:
            tier_css_class = {"Strong Buy": "tier-strong-buy",
                              "Buy":        "tier-buy",
                              "Watch":      "tier-watch"}.get(tier, "tier-unassessed")
            st.markdown(
                f'<div class="tier-header {tier_css_class}">'
                f'{tier_emoji(tier)} {tier}</div>',
                unsafe_allow_html=True
            )

    if tier is not None:
        rank += 1

    sym       = g["symbol"]
    company   = companies.get(sym, "")
    in_wl     = sym in watchlist
    direction = g.get("direction", "hold")
    n_score   = g.get("narrative_score", 0) or 0
    v_score   = g.get("value_score", 0) or 0
    q_score   = g.get("quality_score", 0) or 0

    # Card container via columns
    border_col = TIER_BORDER.get(tier, "#e2e8f0")
    rank_str   = f"#{rank}" if tier else "—"

    # Header row: rank | score+tier | symbol+badges | deep dive button
    c_rank, c_score, c_info, c_btn = st.columns([0.5, 1.1, 5, 1.5])

    with c_rank:
        st.markdown(f'<div style="color:#cbd5e1;font-size:0.75rem;font-weight:700;'
                    f'padding-top:0.6rem;text-align:right">{rank_str}</div>',
                    unsafe_allow_html=True)

    with c_score:
        tier_col = {"Strong Buy": "#ef4444", "Buy": "#16a34a",
                    "Watch": "#ca8a04"}.get(tier, "#64748b")
        st.markdown(
            f'<div style="text-align:center;padding-top:0.3rem">'
            f'<div style="font-size:1.4rem;font-weight:900;color:{tier_col};line-height:1">'
            f'{score:.3f}</div>'
            f'<div style="font-size:0.62rem;font-weight:700;text-transform:uppercase;'
            f'letter-spacing:0.06em;color:{tier_col};margin-top:0.15rem">'
            f'{tier_emoji(tier)} {tier or "—"}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    with c_info:
        # Symbol + badges
        dir_badge = ""
        if direction == "promoted":
            _ovr = overrides.get(sym, {})
            _tip = html_lib.escape(_ovr.get("evidence") or "")
            _nr, _na = _ovr.get("narrative_raw"), _ovr.get("narrative_adjusted")
            _ntxt = f" n {_nr:.2f}→{_na:.2f}" if _nr is not None and _na is not None else ""
            dir_badge = (f' <span title="{_tip}" style="background:#f3e8ff;color:#6b21a8;'
                         f'font-size:0.62rem;font-weight:700;padding:0.1rem 0.35rem;'
                         f'border-radius:3px;vertical-align:middle;border:1px solid #d8b4fe">'
                         f'⭐ QUAL-PROMOTED{_ntxt} · raw {g["hidden_gem_score"]:.3f}</span>')
        elif direction == "upgrade":
            dir_badge = ' <span style="background:#dcfce7;color:#166534;font-size:0.62rem;font-weight:700;padding:0.1rem 0.35rem;border-radius:3px;vertical-align:middle">↑ UPGRADED</span>'
        elif direction == "downgrade":
            dir_badge = ' <span style="background:#fee2e2;color:#991b1b;font-size:0.62rem;font-weight:700;padding:0.1rem 0.35rem;border-radius:3px;vertical-align:middle">↓ DOWNGRADED</span>'
        wl_badge = ' <span style="background:#eff6ff;color:#1d4ed8;font-size:0.62rem;font-weight:700;padding:0.1rem 0.35rem;border-radius:3px;vertical-align:middle;border:1px solid #bfdbfe">★ Watchlist</span>' if in_wl else ""

        # Buffett tier badge
        bt = buffett_tiers.get(sym, {})
        buffett_badge = ""
        if bt.get("tier") == "Buffett Stock":
            buffett_badge = (
                ' <span title="' + html_lib.escape(bt.get("rationale", "")) + '" '
                'style="background:#fef3c7;color:#92400e;font-size:0.62rem;font-weight:700;'
                'padding:0.1rem 0.35rem;border-radius:3px;vertical-align:middle;'
                'border:1px solid #fcd34d">🏆 BUFFETT</span>'
            )
        elif bt.get("tier") == "Potential Buffett":
            buffett_badge = (
                ' <span title="' + html_lib.escape(bt.get("rationale", "")) + '" '
                'style="background:#f8fafc;color:#64748b;font-size:0.62rem;font-weight:600;'
                'padding:0.1rem 0.35rem;border-radius:3px;vertical-align:middle;'
                'border:1px solid #e2e8f0">⭐ Potential</span>'
            )

        # New entrant / rank-change badge
        move_badge = ""
        if g.get("is_new"):
            move_badge = ' <span style="background:#f3e8ff;color:#6b21a8;font-size:0.62rem;font-weight:700;padding:0.1rem 0.35rem;border-radius:3px;vertical-align:middle">★ NEW</span>'
        elif g.get("rank_change") is not None:
            delta = g["rank_change"]
            if delta >= 2:
                move_badge = f' <span style="background:#dcfce7;color:#166534;font-size:0.62rem;font-weight:700;padding:0.1rem 0.35rem;border-radius:3px;vertical-align:middle">▲{delta}</span>'
            elif delta <= -2:
                move_badge = f' <span style="background:#fee2e2;color:#991b1b;font-size:0.62rem;font-weight:700;padding:0.1rem 0.35rem;border-radius:3px;vertical-align:middle">▼{abs(delta)}</span>'

        st.markdown(
            f'<span style="font-size:1rem;font-weight:800;color:#0f172a">{sym}</span>'
            f'{dir_badge}{buffett_badge}{move_badge}{wl_badge}'
            f'<span style="font-size:0.78rem;color:#64748b;margin-left:0.5rem">{html_lib.escape(company)}</span>',
            unsafe_allow_html=True
        )

        # Score bars using st.progress
        for label, val, color in [
            ("Exposure", n_score, "#6366f1"),   # signed narrative exposure (v2)
            ("Value",    v_score, "#0ea5e9"),   # standalone ex-growth value (v2)
            ("Quality",  q_score, "#10b981"),
        ]:
            bcol1, bcol2, bcol3 = st.columns([1, 4, 0.7])
            bcol1.markdown(f'<span style="font-size:0.68rem;color:#94a3b8;font-weight:600">{label}</span>', unsafe_allow_html=True)
            bcol2.progress(float(val))
            bcol3.markdown(f'<span style="font-size:0.72rem;font-weight:700;color:#0f172a">{val:.2f}</span>', unsafe_allow_html=True)

    with c_btn:
        st.markdown("<div style='padding-top:0.3rem'></div>", unsafe_allow_html=True)
        if st.button(f"→ {sym}", key=f"dd_{sym}", use_container_width=True):
            go_to_stock(sym)

    # Bull / bear write-ups (full width, below the row)
    if g.get("key_bull") and g.get("key_bear"):
        b1, b2 = st.columns(2)
        with b1:
            st.markdown(
                f'<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;'
                f'padding:0.6rem 0.8rem;font-size:0.78rem;color:#374151;line-height:1.45;margin-bottom:0.25rem">'
                f'<span style="font-size:0.62rem;font-weight:800;text-transform:uppercase;'
                f'letter-spacing:0.06em;color:#166534;display:block;margin-bottom:0.2rem">▲ Bull</span>'
                f'{html_lib.escape(g["key_bull"])}</div>',
                unsafe_allow_html=True
            )
        with b2:
            st.markdown(
                f'<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;'
                f'padding:0.6rem 0.8rem;font-size:0.78rem;color:#374151;line-height:1.45;margin-bottom:0.25rem">'
                f'<span style="font-size:0.62rem;font-weight:800;text-transform:uppercase;'
                f'letter-spacing:0.06em;color:#991b1b;display:block;margin-bottom:0.2rem">▼ Bear</span>'
                f'{html_lib.escape(g["key_bear"])}</div>',
                unsafe_allow_html=True
            )
        # Show the assessor's reasoning for EVERY assessed stock — a "hold"
        # rationale is the why-we-agree note (user request 2026-07-14)
        if g.get("rationale"):
            st.markdown(
                f'<div style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;'
                f'padding:0.5rem 0.8rem;font-size:0.78rem;color:#92400e;line-height:1.45;'
                f'font-style:italic;margin-bottom:0.25rem">'
                f'<strong>Claude note:</strong> {html_lib.escape(g["rationale"])}</div>',
                unsafe_allow_html=True
            )

    st.markdown('<hr style="border:none;border-top:1px solid #f1f5f9;margin:0.5rem 0">', unsafe_allow_html=True)

# ── Full universe table ───────────────────────────────────────────────────────
if show_all:
    st.markdown("---")
    st.markdown("### Full Universe")
    rows = []
    for g in gems:
        rows.append({
            "Symbol":    g["symbol"],
            "Company":   companies.get(g["symbol"], ""),
            "Gem Score": round(g["hidden_gem_score"], 3),
            "Tier":      g["display_tier"] or "—",
            "Narrative": round(g.get("narrative_score", 0) or 0, 2),
            "Value":     round(g.get("value_score", 0) or 0, 2),
            "Quality":   round(g.get("quality_score", 0) or 0, 2),
            "Assessed":  "✓" if g["assessed"] else "",
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, height=500, hide_index=True,
                 column_config={
                     "Gem Score": st.column_config.NumberColumn(format="%.3f"),
                     "Narrative": st.column_config.NumberColumn(format="%.2f"),
                     "Value":     st.column_config.NumberColumn(format="%.2f"),
                     "Quality":   st.column_config.NumberColumn(format="%.2f"),
                 })

st.markdown('<p style="font-size:0.72rem;color:#94a3b8;margin-top:2rem">'
            'Scores computed from SEC filings, earnings calls, and fundamentals. '
            'Top 25 qualitatively reviewed by Claude Sonnet. Not financial advice.</p>',
            unsafe_allow_html=True)
