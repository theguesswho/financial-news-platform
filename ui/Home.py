"""
Daily Brief — the new home page.
Three sections: Earnings Intelligence · Leaderboard Moves · Insider Activity
"""
import json
from datetime import datetime, timedelta

import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv(override=True)

st.set_page_config(
    page_title="Daily Brief | FinResearch",
    page_icon="📋",
    layout="wide",
)

# ── shared helpers ────────────────────────────────────────────────────────────
@st.cache_resource
def get_engine():
    from pipeline.hidden_gem_scorer import get_engine as _ge
    return _ge()

engine = get_engine()

# ── HOME_MODE switch (Home revamp Phase 2) ───────────────────────────────────
# 'report' renders the stored Morning Report (ui/report_page.py, visual spec
# = approved mockup v2); anything else falls through to the original feed
# below, which also lives permanently on the News Wire page. Cutover is a
# Railway env change, no code deploy; rollback is unsetting it.
import os as _os
if _os.environ.get("HOME_MODE", "feed") == "report":
    from ui.report_page import render_report
    render_report(engine)
    st.stop()

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Page */
.block-container { padding-top: 3.5rem !important; max-width: 1300px; }
header[data-testid="stHeader"] { display: none; }

/* Header */
.brief-header {
    display: flex; justify-content: space-between; align-items: flex-end;
    border-bottom: 2px solid var(--primary-color, #3b82f6);
    padding-bottom: 0.5rem; margin-bottom: 1.4rem;
}
.brief-title { font-size: 1.5rem; font-weight: 700; letter-spacing: -0.02em; }
.brief-date  { font-size: 0.85rem; color: #6b7280; }

/* Section headers */
.section-hdr {
    font-size: 0.78rem; font-weight: 700; letter-spacing: 0.08em;
    text-transform: uppercase; color: #6b7280;
    border-bottom: 1px solid #e5e7eb;
    padding-bottom: 0.3rem; margin-bottom: 0.8rem;
}

/* Filing card */
.filing-card {
    background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px;
    padding: 0.75rem 1rem; margin-bottom: 0.6rem; position: relative;
}
.filing-card:hover { border-color: #3b82f6; }
.fc-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.3rem; }
.fc-sym    { font-weight: 700; font-size: 1rem; }
.fc-meta   { font-size: 0.72rem; color: #9ca3af; }
.fc-type   { font-size: 0.68rem; font-weight: 700; letter-spacing: 0.05em;
             padding: 2px 6px; border-radius: 4px; background: #dbeafe; color: #1d4ed8; }
.fc-type.earn { background: #fef3c7; color: #92400e; }
.fc-synopsis { font-size: 0.82rem; color: #374151; margin: 0.2rem 0; line-height: 1.45; }
.fc-signals  { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.4rem; }
.pill {
    font-size: 0.68rem; font-weight: 600; padding: 2px 8px;
    border-radius: 99px;
}
.pill-green  { background: #d1fae5; color: #065f46; }
.pill-red    { background: #fee2e2; color: #991b1b; }
.pill-amber  { background: #fef3c7; color: #92400e; }
.pill-blue   { background: #dbeafe; color: #1e40af; }
.pill-gray   { background: #f3f4f6; color: #4b5563; }

/* Leaderboard move pills */
.move-section { margin-bottom: 1rem; }
.move-label { font-size: 0.72rem; font-weight: 700; color: #6b7280; margin-bottom: 0.35rem; }
.move-pills { display: flex; flex-wrap: wrap; gap: 0.4rem; }
.move-pill {
    font-size: 0.78rem; font-weight: 600; padding: 4px 10px;
    border-radius: 6px; border: 1px solid transparent;
}
.mp-new      { background: #ede9fe; color: #5b21b6; border-color: #c4b5fd; }
.mp-upgrade  { background: #d1fae5; color: #065f46; border-color: #6ee7b7; }
.mp-downgrade{ background: #fee2e2; color: #991b1b; border-color: #fca5a5; }

/* Score mover row */
.mover-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 0.3rem 0; border-bottom: 1px solid #f3f4f6; font-size: 0.82rem;
}
.mover-sym  { font-weight: 700; width: 60px; }
.mover-tier { font-size: 0.7rem; color: #6b7280; }
.mover-delta-pos { color: #059669; font-weight: 600; }
.mover-delta-neg { color: #dc2626; font-weight: 600; }

/* Insider table */
.insider-block { margin-bottom: 1rem; }
.insider-hdr {
    font-size: 0.72rem; font-weight: 700; padding: 0.25rem 0.5rem;
    border-radius: 4px 4px 0 0; margin-bottom: 0;
}
.insider-hdr-buy  { background: #d1fae5; color: #065f46; }
.insider-hdr-sell { background: #fee2e2; color: #991b1b; }
.insider-row {
    display: flex; align-items: center; gap: 0.5rem;
    padding: 0.35rem 0.5rem; border-bottom: 1px solid #f3f4f6;
    font-size: 0.8rem;
}
.ir-sym   { font-weight: 700; width: 50px; flex-shrink: 0; }
.ir-role  { color: #6b7280; flex: 1; font-size: 0.72rem; overflow: hidden;
            text-overflow: ellipsis; white-space: nowrap; }
.ir-val   { font-weight: 600; flex-shrink: 0; text-align: right; }
.ir-date  { color: #9ca3af; font-size: 0.7rem; flex-shrink: 0; width: 50px; text-align: right; }
.ir-gem   { font-size: 0.68rem; padding: 1px 5px; border-radius: 4px;
            background: #ede9fe; color: #5b21b6; flex-shrink: 0; }
</style>
""", unsafe_allow_html=True)


# ── Data loaders ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_filings_intelligence(days: int = 14):
    """Recent noteworthy filings: strong narrative or significant shift."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            WITH ranked AS (
                SELECT
                    f.id, f.symbol, f.filing_type, f.filing_date, f.title,
                    f.llm_analysis,
                    ft.narrative_strength, ft.trajectory, ft.management_tone,
                    ft.catalysts, ft.risks,
                    LAG(ft.narrative_strength) OVER (
                        PARTITION BY f.symbol ORDER BY f.filing_date
                    ) AS prev_narrative
                FROM filings f
                JOIN filing_themes ft ON ft.filing_id = f.id
                WHERE f.filing_date >= :cutoff
                  AND ft.narrative_strength IS NOT NULL
            )
            SELECT id, symbol, filing_type, filing_date, title, llm_analysis,
                   narrative_strength, trajectory, management_tone,
                   catalysts, risks,
                   COALESCE(narrative_strength - prev_narrative, 0) AS narrative_delta
            FROM ranked
            WHERE narrative_strength >= 0.60
               OR ABS(COALESCE(narrative_strength - prev_narrative, 0)) >= 0.12
            ORDER BY filing_date DESC, narrative_strength DESC
            LIMIT 12
        """), {"cutoff": cutoff}).fetchall()

        # High-impact 8-Ks keep the feed live between earnings seasons
        eightks = conn.execute(text("""
            SELECT id, symbol, filing_type, filing_date, title, llm_analysis,
                   NULL, NULL, NULL, NULL, NULL, 0
            FROM filings
            WHERE filing_type IN ('8-K', '8-K/A')
              AND filing_date >= :cutoff8k
              AND llm_analysis IS NOT NULL
              AND ABS(COALESCE(sentiment_score, 0)) >= 2
            ORDER BY filing_date DESC, ABS(sentiment_score) DESC
            LIMIT 8
        """), {"cutoff8k": datetime.utcnow() - timedelta(days=7)}).fetchall()

    merged = sorted(list(rows) + list(eightks),
                    key=lambda r: r[3] or datetime.min, reverse=True)
    return merged[:14]


@st.cache_data(ttl=300)
def load_insider_activity(days: int = 30):
    """Recent insider buys and sells above $50k, excluding small-value option exercises."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT symbol, person_name, MIN(person_title), transaction_type,
                   SUM(shares),
                   ROUND(SUM(COALESCE(total_value,0)) / NULLIF(SUM(shares),0), 2),
                   SUM(total_value) AS tv, transaction_date
            FROM insider_trades
            WHERE transaction_date >= :cutoff
              AND transaction_type IN ('BUY', 'SELL')
              AND NOT (UPPER(person_name) ~ '(L\\.P|LLC|FUND|PARTNERS|CAPITAL|HOLDINGS|TRUST|MANAGEMENT|SPV| L P|LP$)')
            GROUP BY symbol, person_name, transaction_type, transaction_date
            HAVING SUM(total_value) >= 50000
            ORDER BY (transaction_type = 'BUY') DESC, tv DESC
        """), {"cutoff": cutoff}).fetchall()
    return rows


@st.cache_data(ttl=300)
def load_leaderboard_moves():
    """New entrants, upgrades, downgrades, and biggest score movers."""
    with engine.connect() as conn:
        # Two most recent snapshot dates
        dates = conn.execute(text("""
            SELECT date FROM leaderboard_history
            GROUP BY date ORDER BY date DESC LIMIT 2
        """)).fetchall()

        if len(dates) < 2:
            return {"new": [], "upgrades": [], "downgrades": [], "movers": []}

        today_d, prev_d = dates[0][0], dates[1][0]

        # Board members only (tier set) — every symbol in the universe gets a
        # score row daily, and a newly SCORED stock is not a new ENTRANT.
        # (Bug 2026-07-12: freshly onboarded mid-caps below the Watch cutoff
        # showed as "new entrants" with tier None.)
        today_rows = conn.execute(text("""
            SELECT symbol,
                   COALESCE(assessed_tier, tier) AS tier,
                   gem_score, rank
            FROM leaderboard_history
            WHERE date = :d AND COALESCE(assessed_tier, tier) IN ('Strong Buy','Buy','Watch')
        """), {"d": today_d}).fetchall()

        prev_rows = conn.execute(text("""
            SELECT symbol,
                   COALESCE(assessed_tier, tier) AS tier,
                   gem_score, rank
            FROM leaderboard_history
            WHERE date = :d AND COALESCE(assessed_tier, tier) IN ('Strong Buy','Buy','Watch')
        """), {"d": prev_d}).fetchall()

    today = {r[0]: {"tier": r[1], "score": float(r[2]), "rank": r[3]} for r in today_rows}
    prev  = {r[0]: {"tier": r[1], "score": float(r[2]), "rank": r[3]} for r in prev_rows}

    TIER_RANK = {"Strong Buy": 3, "Buy": 2, "Watch": 1}

    new_entrants, upgrades, downgrades, movers = [], [], [], []

    for sym, cur in today.items():
        if sym not in prev:
            new_entrants.append({"symbol": sym, "tier": cur["tier"], "score": cur["score"]})
            continue
        p = prev[sym]
        delta = cur["score"] - p["score"]
        ct, pt = TIER_RANK.get(cur["tier"], 0), TIER_RANK.get(p["tier"], 0)
        if ct > pt:
            upgrades.append({"symbol": sym, "from_tier": p["tier"], "to_tier": cur["tier"], "delta": delta})
        elif ct < pt:
            downgrades.append({"symbol": sym, "from_tier": p["tier"], "to_tier": cur["tier"], "delta": delta})
        if abs(delta) >= 0.003:
            movers.append({"symbol": sym, "tier": cur["tier"], "delta": delta})

    for sym in prev:
        if sym not in today:
            downgrades.append({"symbol": sym, "from_tier": prev[sym]["tier"], "to_tier": "Off board", "delta": 0})

    movers.sort(key=lambda x: -abs(x["delta"]))
    return {
        "new": new_entrants[:8],
        "upgrades": upgrades[:6],
        "downgrades": downgrades[:6],
        "movers": movers[:8],
    }


_UID = 3  # single-user app

def load_watchlist():
    from db.session import get_session
    from db.models import WatchlistEntry
    session = get_session()
    try:
        session.rollback()
        syms = {w.symbol for w in session.query(WatchlistEntry).filter_by(user_id=_UID).all()}
    finally:
        session.close()
    return syms

@st.cache_data(ttl=300)
def load_gem_scores_map():
    """
    Return {symbol: {gem_score, display_tier, narrative_score, ...}} from today's
    leaderboard_history + qual_assessments.  Single source of truth for the home page.
    """
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT lh.symbol,
                   lh.gem_score,
                   COALESCE(lh.assessed_tier, lh.tier) AS display_tier,
                   lh.narrative_score, lh.value_score,
                   lh.quality_score,  lh.gap_score
            FROM leaderboard_history lh
            WHERE lh.date = (SELECT MAX(date) FROM leaderboard_history)
              AND COALESCE(lh.assessed_tier, lh.tier) IN ('Strong Buy', 'Buy', 'Watch')
        """)).fetchall()
    return {
        r[0]: {
            "gem_score":      float(r[1]),
            "display_tier":   r[2],
            "narrative_score": float(r[3]) if r[3] is not None else 0.0,
            "value_score":    float(r[4]) if r[4] is not None else 0.0,
            "quality_score":  float(r[5]) if r[5] is not None else 0.0,
            "gap_score":      float(r[6]) if r[6] is not None else 0.0,
        }
        for r in rows
    }


def load_gem_symbols():
    """Set of symbols on the leaderboard (any tier). Derived from load_gem_scores_map."""
    return set(load_gem_scores_map().keys())


# ── Synopsis (cached per filing_id in DB) ────────────────────────────────────

def get_synopsis(filing_id, symbol, filing_type, title, llm_analysis,
                 trajectory, tone, catalysts, risks) -> str:
    # Check DB cache first
    if llm_analysis:
        try:
            cached = llm_analysis if isinstance(llm_analysis, dict) else json.loads(llm_analysis)
            if cached.get("synopsis"):
                return cached["synopsis"]
        except Exception:
            pass
    # Generate and cache
    from pipeline.synopsis import get_or_generate_synopsis
    cats = catalysts if isinstance(catalysts, list) else (json.loads(catalysts) if catalysts else [])
    rsks = risks if isinstance(risks, list) else (json.loads(risks) if risks else [])
    return get_or_generate_synopsis(
        engine, filing_id, symbol, filing_type, title, llm_analysis,
        trajectory or "stable", tone or "neutral", cats, rsks
    )


# ── Render helpers ────────────────────────────────────────────────────────────

def trajectory_pill(trajectory: str) -> str:
    mapping = {
        "accelerating": ("pill-green",  "↑ Accelerating"),
        "improving":    ("pill-green",  "↑ Improving"),
        "stable":       ("pill-gray",   "→ Stable"),
        "mixed":        ("pill-amber",  "~ Mixed"),
        "decelerating": ("pill-amber",  "↓ Slowing"),
        "declining":    ("pill-red",    "↓ Declining"),
    }
    cls, label = mapping.get((trajectory or "").lower(), ("pill-gray", trajectory or "–"))
    return f'<span class="pill {cls}">{label}</span>'


def narrative_pill(strength: float) -> str:
    if strength is None:
        return ""
    s = float(strength)
    if s >= 0.80:
        cls, lbl = "pill-green", f"Signal {s:.2f}"
    elif s >= 0.65:
        cls, lbl = "pill-blue",  f"Signal {s:.2f}"
    else:
        cls, lbl = "pill-gray",  f"Signal {s:.2f}"
    return f'<span class="pill {cls}">{lbl}</span>'


def delta_pill(delta: float) -> str:
    if abs(delta) < 0.05:
        return ""
    if delta > 0:
        return f'<span class="pill pill-green">▲ +{delta:.2f} narrative</span>'
    return f'<span class="pill pill-red">▼ {delta:.2f} narrative</span>'


def fmt_value(v) -> str:
    if v is None:
        return "–"
    v = float(v)
    if v >= 1_000_000:
        return f"${v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v/1_000:.0f}K"
    return f"${v:.0f}"


def shorten_title(title: str, role: str) -> str:
    """Return abbreviated insider title."""
    t = (title or "").lower()
    for kw, label in [
        ("chief executive", "CEO"), ("chief financial", "CFO"),
        ("chief operating", "COO"), ("chief technology", "CTO"),
        ("president", "President"), ("chairman", "Chairman"),
        ("director", "Director"), ("vp ", "VP"), ("vice president", "VP"),
        ("general counsel", "Gen. Counsel"),
    ]:
        if kw in t:
            return label
    return (title or role or "Insider")[:20]


def filing_type_label(ft: str) -> str:
    m = {"EARN_CALL": "Earnings Call", "10-K": "10-K Annual",
         "10-Q": "10-Q Quarterly", "8-K": "8-K Event"}
    return m.get(ft, ft)


# ── Page ─────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=600)
def load_daily_brief():
    """Latest stored brief + its date. Read-only: generation happens in the scheduler."""
    with get_engine().connect() as conn:
        row = conn.execute(text("""
            SELECT date, content FROM daily_briefs ORDER BY date DESC LIMIT 1
        """)).fetchone()
    if not row or not row[1]:
        return None, None
    try:
        return row[0], json.loads(row[1])
    except Exception:
        return row[0], None


brief_date, brief = load_daily_brief()
date_label = brief_date.strftime("%A, %B %d, %Y") if brief_date else datetime.utcnow().strftime("%A, %B %d, %Y")
st.markdown(f"""
<div class="brief-header">
  <div class="brief-title">📋 Daily Brief</div>
  <div class="brief-date">{date_label}</div>
</div>
""", unsafe_allow_html=True)

if brief:
    ts = brief.get("top_signal") or {}
    if ts.get("title"):
        sym_chip = f'<span class="pill pill-blue">{ts["symbol"]}</span>&nbsp;' if ts.get("symbol") else ""
        st.markdown(f"""
<div class="filing-card" style="border-left: 3px solid #3b82f6;">
  <div class="fc-header"><span class="fc-sym">{sym_chip}{ts['title']}</span></div>
  <div class="fc-synopsis">{ts.get('body', '')}</div>
  <div class="fc-synopsis" style="color:#1d4ed8; margin-top:0.35rem;"><b>Why it matters:</b> {ts.get('why_it_matters', '')}</div>
</div>
""", unsafe_allow_html=True)

    wl = brief.get("watch_list") or []
    rad = brief.get("on_radar") or []
    if wl or rad:
        bc1, bc2 = st.columns(2, gap="large")
        with bc1:
            if wl:
                st.markdown('<div class="section-hdr">👀 Watch Today</div>', unsafe_allow_html=True)
                for w in wl[:4]:
                    stance = w.get("stance", "NEUTRAL")
                    color = {"POSITIVE": "#059669", "NEGATIVE": "#dc2626"}.get(stance, "#6b7280")
                    st.markdown(f"""
<div class="filing-card">
  <div class="fc-header">
    <span class="fc-sym">{w.get('symbol', '')}</span>
    <span class="fc-meta" style="color:{color}; font-weight:600;">{stance}</span>
  </div>
  <div class="fc-synopsis"><b>{w.get('headline', '')}</b> — {w.get('detail', '')}</div>
  <div class="fc-synopsis" style="color:#6b7280;">Next: {w.get('action', '')}</div>
</div>
""", unsafe_allow_html=True)
        with bc2:
            if rad:
                st.markdown('<div class="section-hdr">📡 On the Radar</div>', unsafe_allow_html=True)
                for r_ in rad[:3]:
                    st.markdown(f"""
<div class="filing-card">
  <div class="fc-header">
    <span class="fc-sym">{r_.get('symbol', '')}</span>
    <span class="fc-meta">{r_.get('pattern', '')}</span>
  </div>
  <div class="fc-synopsis">{r_.get('detail', '')}</div>
  <div class="fc-synopsis" style="color:#6b7280;">Watch for: {r_.get('watch_for', '')}</div>
</div>
""", unsafe_allow_html=True)
else:
    st.caption("Today's brief hasn't been generated yet — it arrives with the 6 AM data run.")

# Load all data
with st.spinner("Loading…"):
    filings    = load_filings_intelligence()
    insiders   = load_insider_activity()
    moves      = load_leaderboard_moves()
    gem_syms   = load_gem_symbols()   # now derived from leaderboard_history, not live scorer
    watchlist  = load_watchlist()

# ── Layout: 2 cols top, full-width insider section below ──────────────────────
col_filings, col_moves = st.columns([3, 2], gap="large")

# ════════════════════════════════════════════════════════════════════
# LEFT — Earnings & Filing Intelligence
# ════════════════════════════════════════════════════════════════════
with col_filings:
    st.markdown('<div class="section-hdr">📄 Earnings & Filing Intelligence</div>', unsafe_allow_html=True)

    if not filings:
        st.caption("No noteworthy filings in the last 14 days.")
    else:
        for row in filings:
            (fid, sym, ftype, fdate, title, llm_analysis,
             narr_str, trajectory, tone, catalysts, risks, narr_delta) = row

            type_cls = "earn" if ftype == "EARN_CALL" else ""
            date_fmt = fdate.strftime("%b %d") if fdate else "–"

            # For 8-Ks use the structured LLM summary directly (filing_themes data is unreliable for 8-Ks)
            impact_pill = ""
            if ftype in ("8-K", "8-K/A"):
                try:
                    ana = json.loads(llm_analysis) if isinstance(llm_analysis, str) else (llm_analysis or {})
                    synopsis = ana.get("summary") or ana.get("headline") or title
                    impact = ana.get("impact", "NEUTRAL")
                    impact_cls = {"POSITIVE": "pill-green", "NEGATIVE": "pill-red"}.get(impact, "pill-gray")
                    impact_pill = f'<span class="pill {impact_cls}">{impact.title()}</span>'
                except Exception:
                    synopsis = title
            else:
                # Generate synopsis (cached in DB after first call)
                synopsis = get_synopsis(fid, sym, ftype, title, llm_analysis,
                                        trajectory, tone, catalysts, risks)

            # Score + status chip (user 2026-08-01): "5.2 Strong Buy", not a bare gem icon
            _g = load_gem_scores_map().get(sym)
            gem_badge = (f'&nbsp;<span class="pill pill-blue">💎 {float(_g["gem_score"])*10:.1f} '
                         f'{_g["display_tier"]}</span>' if _g else "")

            if ftype in ("8-K", "8-K/A"):
                pills = impact_pill
            else:
                pills = (
                    trajectory_pill(trajectory)
                    + narrative_pill(narr_str)
                    + delta_pill(narr_delta)
                )

            st.markdown(f"""
<div class="filing-card">
  <div class="fc-header">
    <span class="fc-sym">{sym}{gem_badge}</span>
    <span class="fc-meta">
      <span class="fc-type {type_cls}">{filing_type_label(ftype)}</span>
      &nbsp;{date_fmt}
    </span>
  </div>
  <div class="fc-synopsis">{synopsis.lstrip('# ').strip()}</div>
  <div class="fc-signals">{pills}</div>
</div>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════
# RIGHT — Leaderboard Moves
# ════════════════════════════════════════════════════════════════════
with col_moves:
    st.markdown('<div class="section-hdr">💎 Leaderboard Moves</div>', unsafe_allow_html=True)

    has_any = any([moves["new"], moves["upgrades"], moves["downgrades"]])

    if not has_any:
        st.caption("No tier changes since last snapshot.")
    else:
        if moves["new"]:
            pills_html = " ".join(
                f'<span class="move-pill mp-new">★ {m["symbol"]}<span style="font-weight:400; margin-left:4px; font-size:0.68rem;">{m["tier"]}</span></span>'
                for m in moves["new"]
            )
            st.markdown(f"""
<div class="move-section">
  <div class="move-label">🆕 New Entrants</div>
  <div class="move-pills">{pills_html}</div>
</div>
""", unsafe_allow_html=True)

        if moves["upgrades"]:
            pills_html = " ".join(
                f'<span class="move-pill mp-upgrade">⬆ {m["symbol"]} → {m["to_tier"]}</span>'
                for m in moves["upgrades"]
            )
            st.markdown(f"""
<div class="move-section">
  <div class="move-label">⬆️ Upgrades</div>
  <div class="move-pills">{pills_html}</div>
</div>
""", unsafe_allow_html=True)

        if moves["downgrades"]:
            pills_html = " ".join(
                f'<span class="move-pill mp-downgrade">⬇ {m["symbol"]} {("→ " + m["to_tier"]) if (m["to_tier"] and m["to_tier"] != "Off board") else "off board"}</span>'
                for m in moves["downgrades"]
            )
            st.markdown(f"""
<div class="move-section">
  <div class="move-label">⬇️ Downgrades / Dropped</div>
  <div class="move-pills">{pills_html}</div>
</div>
""", unsafe_allow_html=True)

    # Score movers
    if moves["movers"]:
        st.markdown('<div style="margin-top:1rem;" class="section-hdr">↕ Biggest Score Moves</div>',
                    unsafe_allow_html=True)
        for m in moves["movers"][:6]:
            delta_cls = "mover-delta-pos" if m["delta"] > 0 else "mover-delta-neg"
            delta_str = f'+{m["delta"]*10:.1f}' if m["delta"] > 0 else f'{m["delta"]*10:.1f}'
            tier_str  = m["tier"] or "–"
            st.markdown(f"""
<div class="mover-row">
  <span class="mover-sym">{m["symbol"]}</span>
  <span class="mover-tier">{tier_str}</span>
  <span class="{delta_cls}">{delta_str}</span>
</div>
""", unsafe_allow_html=True)
    else:
        if has_any or not has_any:
            st.caption("Score moves will appear once daily snapshots accumulate.")

# ════════════════════════════════════════════════════════════════════
# BOTTOM — Insider Activity (full width, two columns)
# ════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown('<div class="section-hdr">🔍 Notable Insider Activity (last 30 days)</div>',
            unsafe_allow_html=True)

# Separate buys and sells, normalise transaction_type codes
buys  = [r for r in insiders if str(r[3]).upper() in ("BUY",  "P", "PURCHASE")]
sells = [r for r in insiders if str(r[3]).upper() in ("SELL", "S")]

# Aggregate by symbol: pick the single largest transaction per symbol
def top_by_symbol(trades, n=6):
    seen = {}
    for r in sorted(trades, key=lambda x: -(float(x[6]) if x[6] else 0)):
        sym = r[0]
        if sym not in seen:
            seen[sym] = r
        if len(seen) >= n:
            break
    return list(seen.values())

top_buys  = top_by_symbol(buys,  6)
top_sells = top_by_symbol(sells, 6)

ins_col_buy, ins_col_sell = st.columns(2, gap="large")

def render_insider_block(col, trades, label, hdr_cls):
    with col:
        st.markdown(f'<div class="insider-hdr {hdr_cls}">{label}</div>', unsafe_allow_html=True)
        if not trades:
            st.caption("No significant activity.")
            return
        for r in trades:
            sym, name, title, txn_type, shares, price, value, txn_date = r
            role    = shorten_title(title, "")
            val_str = fmt_value(value)
            date_str = txn_date.strftime("%b %d") if txn_date else "–"
            _g2 = load_gem_scores_map().get(sym)
            gem_badge = (f' <span class="ir-gem">💎 {float(_g2["gem_score"])*10:.1f} '
                         f'{_g2["display_tier"]}</span>' if _g2 else "")
            st.markdown(f"""
<div class="insider-row">
  <span class="ir-sym">{sym}</span>
  <span class="ir-role">{role}</span>
  <span class="ir-val">{val_str}</span>
  <span class="ir-date">{date_str}</span>
  {gem_badge}
</div>
""", unsafe_allow_html=True)

render_insider_block(ins_col_buy,  top_buys,  "🟢 Top Buys",  "insider-hdr-buy")
render_insider_block(ins_col_sell, top_sells, "🔴 Top Sells", "insider-hdr-sell")

# ════════════════════════════════════════════════════════════════════
# WATCHLIST — current scores for your tracked stocks
# ════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown('<div class="section-hdr">⭐ Your Watchlist</div>', unsafe_allow_html=True)

if not watchlist:
    st.caption("No stocks on your watchlist yet. Add them from the Hidden Gems or Stock Detail page.")
else:
    _all_scores = load_gem_scores_map()

    def _tier_color(tier):
        return {"Strong Buy": "#ef4444", "Buy": "#16a34a", "Watch": "#ca8a04"}.get(tier, "#6b7280")

    wl_cols = st.columns(min(len(watchlist), 4))
    for i, sym in enumerate(sorted(watchlist)):
        g = _all_scores.get(sym)
        with wl_cols[i % 4]:
            if g:
                tier  = g.get("display_tier") or "—"
                score = g.get("gem_score", 0)
                color = _tier_color(tier)
                st.markdown(f"""
<div class="filing-card" style="text-align:center; cursor:pointer;">
  <div style="font-size:1.1rem; font-weight:700;">{sym}</div>
  <div style="font-size:1.5rem; font-weight:800; color:{color};">{score*10:.1f}</div>
  <div style="font-size:0.72rem; color:{color}; font-weight:600;">{tier}</div>
</div>""", unsafe_allow_html=True)
            else:
                st.markdown(f"""
<div class="filing-card" style="text-align:center;">
  <div style="font-size:1.1rem; font-weight:700;">{sym}</div>
  <div style="font-size:0.78rem; color:#9ca3af;">Not in universe</div>
</div>""", unsafe_allow_html=True)
            if st.button("Remove", key=f"wl_rm_{sym}", use_container_width=True):
                from db.session import get_session as _gs
                from db.models import WatchlistEntry as _WE
                _s = _gs()
                _s.query(_WE).filter_by(user_id=_UID, symbol=sym).delete()
                _s.commit()
                _s.close()
                st.cache_data.clear()
                st.rerun()
