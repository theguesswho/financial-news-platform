"""
Stock Detail — everything you need to decide on a buy-and-hold position.

Sections:
  1. Score & Conviction      — gem score, tier, component breakdown
  2. Fundamentals            — the key numbers
  3. Earnings Call History   — last 4 calls: themes, tone, catalysts, risks, claims
  4. SEC Filings             — 10-K / 10-Q narrative
  5. Insider Activity        — buys and sells with value
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime, date

import html as html_lib

import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import text, desc
from anthropic import Anthropic

root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root))
load_dotenv(root / ".env", override=True)

from pipeline.hidden_gem_scorer import get_engine, score_all_stocks
from db.session import get_session
from db.models import WatchlistEntry

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Stock Detail", page_icon="📊", layout="wide")

st.markdown("""
<style>
.block-container { max-width: 980px; padding: 3.5rem 2rem 4rem; }
header[data-testid="stHeader"] { display: none; }

/* Section header */
.section-hdr {
    font-size: 0.72rem; font-weight: 800; letter-spacing: 0.1em;
    text-transform: uppercase; color: #64748b;
    margin: 2rem 0 0.75rem; padding-bottom: 0.4rem;
    border-bottom: 2px solid #e2e8f0;
}

/* Hero header */
.stock-hero {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    border-radius: 14px; padding: 1.5rem 2rem; color: white;
    margin-bottom: 1.5rem;
}
.hero-symbol   { font-size: 2rem; font-weight: 900; letter-spacing: -0.02em; }
.hero-company  { font-size: 1rem; color: #94a3b8; margin-top: 0.1rem; }
.hero-sector   { font-size: 0.75rem; color: #64748b; margin-top: 0.2rem; }
.hero-score    { font-size: 2.5rem; font-weight: 900; line-height: 1; }
.hero-tier     { font-size: 0.75rem; font-weight: 700; letter-spacing: 0.08em;
                 text-transform: uppercase; margin-top: 0.25rem; }
.hero-assessed { font-size: 0.7rem; color: #475569; margin-top: 0.2rem; }

/* Score cards */
.score-card {
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px;
    padding: 0.9rem 1rem; text-align: center;
}
.score-card-label { font-size: 0.68rem; font-weight: 700; letter-spacing: 0.07em;
                    text-transform: uppercase; color: #94a3b8; margin-bottom: 0.3rem; }
.score-card-value { font-size: 1.5rem; font-weight: 800; color: #0f172a; }
.score-card-bar   { height: 5px; border-radius: 3px; background: #e2e8f0; margin-top: 0.4rem; }
.score-card-fill  { height: 5px; border-radius: 3px; }

/* Fundamentals grid */
.fund-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; }
.fund-item {
    display: flex; justify-content: space-between; align-items: center;
    padding: 0.5rem 0.75rem; border-radius: 8px; background: #f8fafc;
    border: 1px solid #e2e8f0;
}
.fund-label { font-size: 0.78rem; color: #64748b; font-weight: 600; }
.fund-value { font-size: 0.88rem; font-weight: 800; color: #0f172a; }
.fund-value.positive { color: #16a34a; }
.fund-value.negative { color: #dc2626; }

/* Call cards */
.call-card {
    border: 1px solid #e2e8f0; border-radius: 12px;
    padding: 1.1rem 1.25rem; margin-bottom: 0.75rem;
}
.call-header { display: flex; justify-content: space-between; align-items: center;
               margin-bottom: 0.75rem; }
.call-date   { font-size: 0.75rem; font-weight: 700; color: #94a3b8; }
.call-badges { display: flex; gap: 0.4rem; }
.call-badge  {
    font-size: 0.68rem; font-weight: 700; padding: 0.15rem 0.5rem;
    border-radius: 12px; letter-spacing: 0.04em;
}
.badge-confident    { background: #dcfce7; color: #166534; }
.badge-cautious     { background: #fef3c7; color: #92400e; }
.badge-mixed        { background: #f1f5f9; color: #475569; }
.badge-accelerating { background: #ede9fe; color: #5b21b6; }
.badge-decelerating { background: #fee2e2; color: #991b1b; }
.badge-stable       { background: #f1f5f9; color: #475569; }

.call-section-title {
    font-size: 0.68rem; font-weight: 800; text-transform: uppercase;
    letter-spacing: 0.06em; color: #94a3b8; margin: 0.65rem 0 0.3rem;
}
.call-theme, .call-catalyst, .call-risk {
    font-size: 0.82rem; color: #374151; line-height: 1.45;
    padding: 0.25rem 0; border-bottom: 1px solid #f3f4f6;
}
.call-theme::before    { content: "◆ "; color: #6366f1; font-size: 0.6rem; }
.call-catalyst::before { content: "▲ "; color: #16a34a; font-size: 0.6rem; }
.call-risk::before     { content: "▼ "; color: #dc2626; font-size: 0.6rem; }

.narrative-strength {
    display: inline-block; font-size: 0.68rem; font-weight: 700;
    color: #64748b; margin-left: 0.5rem;
}

/* Claims */
.claim-item {
    padding: 0.55rem 0.75rem; border-radius: 8px; margin-bottom: 0.4rem;
    border-left: 3px solid #6366f1; background: #f8fafc;
    font-size: 0.82rem; color: #374151; line-height: 1.5;
}
.claim-meta { font-size: 0.68rem; color: #94a3b8; margin-bottom: 0.2rem; font-weight: 600; }

/* Insider trades */
.trade-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 0.6rem 0.75rem; border-radius: 8px; margin-bottom: 0.3rem;
    border: 1px solid #e2e8f0;
}
.trade-buy  { border-left: 3px solid #22c55e; }
.trade-sell { border-left: 3px solid #ef4444; }
.trade-person { font-size: 0.82rem; font-weight: 700; color: #0f172a; }
.trade-title  { font-size: 0.72rem; color: #64748b; }
.trade-value  { font-size: 0.88rem; font-weight: 800; }
.trade-buy  .trade-value { color: #16a34a; }
.trade-sell .trade-value { color: #dc2626; }
.trade-date   { font-size: 0.72rem; color: #94a3b8; text-align: right; }
.trade-shares { font-size: 0.7rem; color: #64748b; }

/* Bull/bear panels */
.bull-panel {
    background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 10px;
    padding: 0.9rem 1.1rem;
}
.bear-panel {
    background: #fef2f2; border: 1px solid #fecaca; border-radius: 10px;
    padding: 0.9rem 1.1rem;
}
.panel-label { font-size: 0.68rem; font-weight: 800; text-transform: uppercase;
               letter-spacing: 0.07em; margin-bottom: 0.4rem; }
.bull-panel .panel-label { color: #166534; }
.bear-panel .panel-label { color: #991b1b; }
.panel-text  { font-size: 0.85rem; line-height: 1.55; color: #374151; }

/* Rationale box */
.rationale-box {
    background: #fffbeb; border: 1px solid #fde68a; border-radius: 10px;
    padding: 0.9rem 1.1rem; margin-top: 0.75rem;
    font-size: 0.85rem; color: #374151; line-height: 1.55;
    font-style: italic;
}
.rationale-label { font-size: 0.68rem; font-weight: 800; text-transform: uppercase;
                   letter-spacing: 0.07em; color: #92400e; margin-bottom: 0.4rem; }

/* Direction banner */
.direction-banner {
    border-radius: 8px; padding: 0.5rem 0.9rem; margin-top: 0.5rem;
    font-size: 0.8rem; font-weight: 700; display: inline-block;
}
.dir-upgrade   { background: #dcfce7; color: #166534; }
.dir-downgrade { background: #fee2e2; color: #991b1b; }
.dir-hold      { background: #f1f5f9; color: #475569; }

/* Deep Dive / Buffett Memo */
.dd-section {
    background: #fffdf5; border: 1px solid #fde68a;
    border-radius: 12px; padding: 1.1rem 1.4rem; margin-bottom: 0.75rem;
}
.dd-section-label {
    font-size: 0.65rem; font-weight: 800; text-transform: uppercase;
    letter-spacing: 0.1em; color: #92400e; margin-bottom: 0.45rem;
}
.dd-section-text {
    font-size: 0.85rem; line-height: 1.65; color: #1c1917;
}
.dd-verdict {
    background: #1c1917; border-radius: 12px;
    padding: 1.1rem 1.4rem; margin-bottom: 0.75rem;
}
.dd-verdict-label {
    font-size: 0.65rem; font-weight: 800; text-transform: uppercase;
    letter-spacing: 0.1em; color: #a16207; margin-bottom: 0.45rem;
}
.dd-verdict-text {
    font-size: 0.88rem; line-height: 1.65; color: #fef9c3;
}
.dd-meta {
    font-size: 0.7rem; color: #94a3b8; margin-top: 0.5rem; font-style: italic;
}
</style>
""", unsafe_allow_html=True)

# ── Data loading ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def load_gem_scores():
    engine = get_engine()
    return {g["symbol"]: g for g in score_all_stocks(engine)}

@st.cache_data(ttl=3600, show_spinner=False)
def load_company_names():
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT symbol, company_name FROM fundamentals WHERE company_name IS NOT NULL")).fetchall()
    return {r[0]: r[1] for r in rows if r[1]}

@st.cache_resource
def get_db_session():
    return get_session()

def load_symbol_data(symbol):
    engine = get_engine()
    with engine.connect() as conn:

        # Qual assessment
        qa = conn.execute(text("""
            SELECT gem_score, raw_tier, adjusted_tier, direction,
                   rationale, key_bull, key_bear, assessed_at
            FROM qual_assessments WHERE symbol = :s
        """), {"s": symbol}).fetchone()

        # Fundamentals
        fund = conn.execute(text("""
            SELECT peg_ratio, pe_forward, pe_trailing, revenue_growth_yoy,
                   earnings_growth_yoy, roic, gross_margin, operating_margin,
                   net_margin, fcf_margin, debt_to_equity, market_cap,
                   fifty_two_week_high, fifty_two_week_low, price_vs_52w_high,
                   analyst_rating, analyst_target_price, analysts_count,
                   sector, industry
            FROM fundamentals WHERE symbol = :s
        """), {"s": symbol}).fetchone()

        # Earnings calls (last 6)
        calls = conn.execute(text("""
            SELECT f.filing_date, ft.narrative_strength, ft.trajectory,
                   ft.management_tone, ft.raw_themes, ft.catalysts, ft.risks
            FROM filing_themes ft
            JOIN filings f ON f.id = ft.filing_id
            WHERE ft.symbol = :s AND f.filing_type = 'EARN_CALL'
            ORDER BY f.filing_date DESC
            LIMIT 6
        """), {"s": symbol}).fetchall()

        # SEC filings (last 4 10-K/10-Q)
        filings = conn.execute(text("""
            SELECT f.filing_date, f.filing_type, ft.narrative_strength,
                   ft.trajectory, ft.management_tone, ft.raw_themes,
                   ft.catalysts, ft.risks, f.url
            FROM filing_themes ft
            JOIN filings f ON f.id = ft.filing_id
            WHERE ft.symbol = :s AND f.filing_type IN ('10-K','10-Q')
            ORDER BY f.filing_date DESC
            LIMIT 4
        """), {"s": symbol}).fetchall()

        # Top earnings claims
        claims = conn.execute(text("""
            SELECT claim_type, claim_text, confidence, call_date, direction
            FROM earnings_claims
            WHERE symbol = :s AND confidence >= 0.75
            ORDER BY call_date DESC, confidence DESC
            LIMIT 12
        """), {"s": symbol}).fetchall()

        # Insider trades (last 12 months)
        trades = conn.execute(text("""
            SELECT person_name, person_title, transaction_date,
                   transaction_type, shares, price_per_share, total_value
            FROM insider_trades
            WHERE symbol = :s
            ORDER BY transaction_date DESC
            LIMIT 30
        """), {"s": symbol}).fetchall()

        # Price (last 90 days)
        prices = conn.execute(text("""
            SELECT date, close FROM eod_prices
            WHERE symbol = :s
            ORDER BY date DESC LIMIT 90
        """), {"s": symbol}).fetchall()

        # Meta-theme alignments
        themes = conn.execute(text("""
            SELECT mt.name, sta.alignment_score, sta.trajectory
            FROM stock_theme_alignment sta
            JOIN meta_themes mt ON mt.id = sta.meta_theme_id
            WHERE sta.symbol = :s
            ORDER BY sta.alignment_score DESC
            LIMIT 8
        """), {"s": symbol}).fetchall()

    return dict(qa=qa, fund=fund, calls=calls, filings=filings,
                claims=claims, trades=trades, prices=prices, themes=themes)

# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_pct(v, dp=1):
    if v is None: return "—"
    return f"{float(v)*100:+.{dp}f}%"

def fmt_x(v, dp=1):
    if v is None: return "—"
    return f"{float(v):.{dp}f}x"

def fmt_m(v):
    if v is None: return "—"
    v = float(v)
    if v >= 1e12: return f"${v/1e12:.1f}T"
    if v >= 1e9:  return f"${v/1e9:.1f}B"
    if v >= 1e6:  return f"${v/1e6:.0f}M"
    return f"${v:,.0f}"

def pct_class(v):
    if v is None: return ""
    return "positive" if float(v) > 0 else "negative"

def tone_badge(tone):
    if not tone: return ""
    t = (tone or "").lower()
    css = "confident" if "conf" in t else ("cautious" if "caut" in t else "mixed")
    return f'<span class="call-badge badge-{css}">{tone.title()}</span>'

def traj_badge(traj):
    if not traj: return ""
    t = (traj or "").lower()
    css = ("accelerating" if "acc" in t or "improv" in t
           else "decelerating" if "dec" in t or "deteri" in t
           else "stable")
    icon = "↑" if css == "accelerating" else ("↓" if css == "decelerating" else "→")
    return f'<span class="call-badge badge-{css}">{icon} {traj.title()}</span>'

def safe_json_list(val):
    if not val: return []
    if isinstance(val, list): return val
    try:    return json.loads(val)
    except: return [str(val)]

def build_stock_context(symbol, company, gem, qa, fund, calls, filings, claims, trades, themes):
    """Build a structured text snapshot of all available data for the AI system prompt."""
    parts = []

    # ── Gem score ──────────────────────────────────────────────────────────────
    parts.append(f"## Hidden Gem Score for {symbol} ({company})")
    if gem:
        score = gem.get("hidden_gem_score")
        parts.append(f"Overall Score: {score*10:.1f}/10" if score else "Overall Score: N/A")
        parts.append(f"  Narrative Score:       {gem.get('narrative_score', 0):.2f}  (macro theme alignment)")
        parts.append(f"  Value Score:           {gem.get('value_score', 0):.2f}  (valuation vs quality)")
        parts.append(f"  Quality Score:         {gem.get('quality_score', 0):.2f}  (ROIC, margins, growth)")
        parts.append(f"  Call-Filing Gap Score: {gem.get('gap_score', 0):.2f}  (signal divergence)")
        if gem.get("sector"):
            parts.append(f"  Sector: {gem['sector']}")

    # ── Claude's conviction assessment ─────────────────────────────────────────
    if qa:
        parts.append(f"\n## Claude's Conviction Assessment")
        parts.append(f"Tier:      {qa[2]}")
        parts.append(f"Direction: {qa[3]}")
        if qa[5]: parts.append(f"Bull Case: {qa[5]}")
        if qa[6]: parts.append(f"Bear Case: {qa[6]}")
        if qa[4]: parts.append(f"Rationale: {qa[4]}")

    # ── Fundamentals ───────────────────────────────────────────────────────────
    if fund:
        peg, fwd_pe, trail_pe, rev_g, earn_g, roic, gm, om, nm, fcfm, de, mktcap, \
            high52, low52, pvh, rating, target, n_analysts, sector, industry = fund
        def pct(v): return f"{float(v)*100:.1f}%" if v is not None else "N/A"
        def xf(v):  return f"{float(v):.1f}x"     if v is not None else "N/A"
        parts.append(f"\n## Fundamentals")
        if sector:   parts.append(f"Sector: {sector}{', ' + industry if industry else ''}")
        if mktcap:   parts.append(f"Market Cap: {fmt_m(mktcap)}")
        parts.append(f"Forward P/E: {xf(fwd_pe)}")
        parts.append(f"PEG Ratio:   {xf(peg)}")
        parts.append(f"Revenue Growth (YoY):  {pct(rev_g)}")
        parts.append(f"Earnings Growth (YoY): {pct(earn_g)}")
        parts.append(f"ROIC:             {pct(roic)}")
        parts.append(f"Gross Margin:     {pct(gm)}")
        parts.append(f"Operating Margin: {pct(om)}")
        parts.append(f"FCF Margin:       {pct(fcfm)}")
        parts.append(f"Debt/Equity:      {xf(de)}")
        parts.append(f"Price vs 52w High: {pct(pvh) if pvh else 'N/A'}")
        if target and rating:
            parts.append(f"Analyst Target: ${float(target):.0f} ({rating}, {n_analysts or '?'} analysts)")

    # ── Earnings calls ─────────────────────────────────────────────────────────
    if calls:
        parts.append(f"\n## Earnings Call History (last {len(calls)} calls)")
        for call in calls:
            call_date, ns, traj, tone, raw_themes, cats_j, risks_j = call
            ds = call_date.strftime("%Y-%m-%d") if call_date else "Unknown"
            ns_str = f"{float(ns)*100:.0f}%" if ns else "N/A"
            parts.append(f"\n### {ds}  |  Tone: {tone or 'N/A'}  |  Trajectory: {traj or 'N/A'}  |  Narrative Strength: {ns_str}")
            tl = safe_json_list(raw_themes)
            cl = safe_json_list(cats_j)
            rl = safe_json_list(risks_j)
            if tl: parts.append(f"Key Themes:  {'; '.join(tl[:5])}")
            if cl: parts.append(f"Catalysts:   {'; '.join(cl[:4])}")
            if rl: parts.append(f"Risks:       {'; '.join(rl[:4])}")

    # ── SEC filings ────────────────────────────────────────────────────────────
    if filings:
        parts.append(f"\n## SEC Filings (last {len(filings)})")
        for f in filings:
            f_date, f_type, f_ns, f_traj, f_tone, f_themes, f_cats, f_risks, _ = f
            ds = f_date.strftime("%Y-%m-%d") if f_date else "Unknown"
            ns_str = f"{float(f_ns)*100:.0f}%" if f_ns else "N/A"
            parts.append(f"\n### {f_type}: {ds}  |  Tone: {f_tone or 'N/A'}  |  Trajectory: {f_traj or 'N/A'}  |  Narrative Strength: {ns_str}")
            tl = safe_json_list(f_themes)
            cl = safe_json_list(f_cats)
            rl = safe_json_list(f_risks)
            if tl: parts.append(f"Key Themes: {'; '.join(tl[:5])}")
            if cl: parts.append(f"Catalysts:  {'; '.join(cl[:4])}")
            if rl: parts.append(f"Risks:      {'; '.join(rl[:4])}")

    # ── Forward-looking claims ──────────────────────────────────────────────────
    if claims:
        parts.append(f"\n## High-Confidence Management Claims (≥75% confidence)")
        for cl in claims[:10]:
            claim_type, claim_text, confidence, call_date, dir_cl = cl
            conf_str = f"{int(float(confidence)*100)}%" if confidence else "N/A"
            dir_str  = {"up": "↑", "down": "↓"}.get(dir_cl or "", "→")
            type_str = (claim_type or "").replace("_", " ").title()
            parts.append(f"- [{call_date} | {type_str} | {dir_str} {conf_str}] {claim_text}")

    # ── Insider activity ────────────────────────────────────────────────────────
    if trades:
        buys  = [t for t in trades if t[3] == "BUY"]
        sells = [t for t in trades if t[3] == "SELL"]
        total_buy  = sum(float(t[6] or 0) for t in buys)
        total_sell = sum(float(t[6] or 0) for t in sells)
        parts.append(f"\n## Insider Activity (last 30 transactions)")
        parts.append(f"Buys:  {len(buys)} transactions  |  Total value: {fmt_m(total_buy)}")
        parts.append(f"Sells: {len(sells)} transactions  |  Total value: {fmt_m(total_sell)}")
        for t in buys[:5]:
            person, title, t_date, _, shares, price, value = t
            ds = t_date.strftime("%Y-%m-%d") if t_date else "—"
            sh = f"{float(shares):,.0f} shares @ ${float(price):.2f}" if shares and price else ""
            parts.append(f"  BUY  {person or 'Unknown'} ({title or ''})  {sh}  {fmt_m(float(value)) if value else ''}  {ds}")
        for t in sells[:5]:
            person, title, t_date, _, shares, price, value = t
            ds = t_date.strftime("%Y-%m-%d") if t_date else "—"
            sh = f"{float(shares):,.0f} shares @ ${float(price):.2f}" if shares and price else ""
            parts.append(f"  SELL {person or 'Unknown'} ({title or ''})  {sh}  {fmt_m(float(value)) if value else ''}  {ds}")

    # ── Macro themes ────────────────────────────────────────────────────────────
    if themes:
        parts.append(f"\n## Macro Theme Alignment")
        for t in themes:
            pct_val = f"{float(t[1])*100:.0f}%" if t[1] else "N/A"
            parts.append(f"  - {t[0]}: {pct_val} alignment, trajectory: {t[2] or 'N/A'}")

    return "\n".join(parts)

def tier_color(tier):
    return {"Strong Buy": "#ef4444", "Buy": "#16a34a", "Watch": "#ca8a04"}.get(tier or "", "#64748b")

def tier_emoji(tier):
    return {"Strong Buy": "🔥", "Buy": "✅", "Watch": "👀"}.get(tier or "", "–")

# ── Symbol selection ──────────────────────────────────────────────────────────
all_gems     = load_gem_scores()
all_symbols  = sorted(all_gems.keys())
companies    = load_company_names()

default_sym  = st.session_state.get("detail_symbol", all_symbols[0] if all_symbols else "AAPL")
if default_sym not in all_symbols and all_symbols:
    default_sym = all_symbols[0]

session = get_db_session()
try:
    session.rollback()  # clear any poisoned transaction from a previous failed run
except Exception:
    pass

with st.sidebar:
    if st.button("← Back to Leaderboard", use_container_width=True):
        st.switch_page("Home.py")

    st.markdown("---")
    st.markdown("### 📊 Select Stock")
    symbol = st.selectbox(
        "Stock",
        all_symbols,
        index=all_symbols.index(default_sym) if default_sym in all_symbols else 0,
        label_visibility="collapsed"
    )
    st.session_state["detail_symbol"] = symbol

    # Watchlist toggle (single-user app — always user_id=3)
    _UID = 3
    in_wl = session.query(WatchlistEntry).filter_by(user_id=_UID, symbol=symbol).first()
    if in_wl:
        if st.button("★ Remove from Watchlist", use_container_width=True):
            session.delete(in_wl)
            session.commit()
            st.cache_data.clear()
            st.rerun()
    else:
        if st.button("☆ Add to Watchlist", use_container_width=True):
            session.add(WatchlistEntry(user_id=_UID, symbol=symbol))
            session.commit()
            st.cache_data.clear()
            st.rerun()

    st.markdown("---")
    st.caption("All data from SEC EDGAR, FMP, and Claude AI analysis.\nNot financial advice.")

# ── Load data ─────────────────────────────────────────────────────────────────
with st.spinner(f"Loading {symbol}…"):
    data = load_symbol_data(symbol)
    gem  = all_gems.get(symbol, {})

qa      = data["qa"]
fund    = data["fund"]
calls   = data["calls"]
filings = data["filings"]
claims  = data["claims"]
trades  = data["trades"]
prices  = data["prices"]
themes  = data["themes"]

company = companies.get(symbol, symbol)
gem_score = gem.get("hidden_gem_score")

# Determine display tier. A qual verdict is only CURRENT while the raw score
# still qualifies for the board — NFLX kept showing "Buy (assessed Jun 24)"
# next to a 0.197 score after falling off. Stale verdicts become dated
# historical context, not a live tier.
from pipeline.tiers import tier_for as _tier_for, WATCH as _WATCH, BUY as _BUY, STRONG_BUY as _SB
_score_now = gem_score or 0
_on_board  = _score_now > _WATCH
if qa and _on_board:
    display_tier = qa[2] if qa[2] in ("Strong Buy", "Buy", "Watch") else None
    direction    = qa[3]
    rationale    = qa[4]
    key_bull     = qa[5]
    key_bear     = qa[6]
    assessed_at  = qa[7]
elif qa:
    # Off the board: show raw state; keep the old assessment as history only
    display_tier = None
    direction    = None
    rationale    = qa[4]
    key_bull     = qa[5]
    key_bear     = qa[6]
    assessed_at  = qa[7]
else:
    score = gem_score or 0
    display_tier = _tier_for(score)
    direction    = "hold"
    rationale    = None
    key_bull     = None
    key_bear     = None
    assessed_at  = None

tier_col = tier_color(display_tier)
tier_em  = tier_emoji(display_tier)

# ────────────────────────────────────────────────────────────────────────────
# 1. HERO HEADER
# ────────────────────────────────────────────────────────────────────────────
sector   = (fund[18] if fund and fund[18] else "")
industry = (fund[19] if fund and fund[19] else "")
sector_str = f"{sector} · {industry}" if sector and industry else sector or industry or ""

dir_text = {"upgrade": "↑ Claude upgraded this stock",
            "downgrade": "↓ Claude downgraded this stock",
            "hold": "Tier confirmed by Claude"}.get(direction or "hold", "")
dir_css  = {"upgrade": "dir-upgrade", "downgrade": "dir-downgrade",
            "hold": "dir-hold"}.get(direction or "hold", "dir-hold")
if qa and _on_board:
    assessed_str = f'Assessed {assessed_at.strftime("%b %d, %Y") if assessed_at else ""}'
elif qa:
    assessed_str = (f'Below board threshold — last assessed '
                    f'{assessed_at.strftime("%b %d, %Y") if assessed_at else ""} '
                    f'({qa[2]} at the time; historical, not a current call)')
else:
    assessed_str = "Raw quant score — not yet Claude-assessed"

col_left, col_right = st.columns([2, 1])
with col_left:
    st.markdown(f"""
<div class="stock-hero">
  <div class="hero-symbol">{symbol}</div>
  <div class="hero-company">{company}</div>
  {"<div class='hero-sector'>" + sector_str + "</div>" if sector_str else ""}
  {"<div class='direction-banner " + dir_css + "'>" + dir_text + "</div>" if qa else ""}
</div>
""", unsafe_allow_html=True)

with col_right:
    score_display = f"{gem_score*10:.1f}" if gem_score else "—"
    st.markdown(f"""
<div class="stock-hero" style="text-align:center">
  <div style="font-size:0.68rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;
              color:#64748b;margin-bottom:0.4rem">Hidden Gem Score</div>
  <div class="hero-score" style="color:{tier_col}">{score_display}</div>
  <div class="hero-tier" style="color:{tier_col}">{tier_em} {display_tier or "Below threshold"}</div>
  <div class="hero-assessed">{assessed_str}</div>
</div>
""", unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────────────────────
# 2. SCORE COMPONENTS
# ────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-hdr">Score Components</div>', unsafe_allow_html=True)

n_score = gem.get("narrative_score", 0) or 0
v_score = gem.get("value_score", 0) or 0
q_score = gem.get("quality_score", 0) or 0
g_score = gem.get("gap_score", 0) or 0

component_cols = st.columns(4)
for col, label, val, color, desc in [
    (component_cols[0], "Narrative", n_score, "#6366f1",
     "How strongly management's narrative aligns with accelerating macro themes"),
    (component_cols[1], "Value", v_score, "#0ea5e9",
     "How cheap the stock is relative to its quality (PEG, Fwd PE, Price vs 52w)"),
    (component_cols[2], "Quality", q_score, "#10b981",
     "Business quality: ROIC, margins, growth trajectory"),
    (component_cols[3], "Call–Filing Gap", g_score, "#f59e0b",
     "Divergence between management calls and official filings — bigger gap = more signal"),
]:
    pct = int(val * 100)
    with col:
        st.markdown(f"""
<div class="score-card">
  <div class="score-card-label">{label}</div>
  <div class="score-card-value" style="color:{color}">{val*10:.1f}</div>
  <div class="score-card-bar">
    <div class="score-card-fill" style="width:{pct}%;background:{color}"></div>
  </div>
</div>
""", unsafe_allow_html=True)
        st.caption(desc)

# ────────────────────────────────────────────────────────────────────────────
# 2b. PRICE & SCORE HISTORY
# ────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=900)
def load_history(sym: str):
    eng = get_engine()
    with eng.connect() as conn:
        px = conn.execute(text("""
            SELECT date, close FROM eod_prices
            WHERE symbol = :s ORDER BY date
        """), {"s": sym}).fetchall()
        sc = conn.execute(text("""
            SELECT date, gem_score, narrative_score, value_score, quality_score, gap_score
            FROM leaderboard_history WHERE symbol = :s ORDER BY date
        """), {"s": sym}).fetchall()
        ev = conn.execute(text("""
            SELECT filing_date::date, filing_type, title FROM filings
            WHERE symbol = :s AND filing_date >= NOW() - INTERVAL '8 months'
            ORDER BY filing_date
        """), {"s": sym}).fetchall()
    return px, sc, ev


px_rows, sc_rows, ev_rows = load_history(symbol)

if px_rows:
    import altair as alt
    st.markdown('<div class="section-hdr">Price & Score History</div>', unsafe_allow_html=True)

    px_df = pd.DataFrame(px_rows, columns=["date", "close"])
    px_df["date"] = pd.to_datetime(px_df["date"])
    px_df["close"] = px_df["close"].astype(float)

    price_line = alt.Chart(px_df).mark_line(color="#0ea5e9", strokeWidth=1.8).encode(
        x=alt.X("date:T", title=None),
        y=alt.Y("close:Q", title="Close (USD)", scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip("date:T"), alt.Tooltip("close:Q", format=".2f")],
    )

    layers = [price_line]
    if ev_rows:
        ev_df = pd.DataFrame(ev_rows, columns=["date", "type", "title"])
        ev_df["date"] = pd.to_datetime(ev_df["date"])
        ev_df = ev_df[ev_df["date"] >= px_df["date"].min()]
        if not ev_df.empty:
            layers.append(
                alt.Chart(ev_df).mark_rule(color="#f59e0b", strokeDash=[3, 3], opacity=0.6).encode(
                    x="date:T",
                    tooltip=[alt.Tooltip("date:T"), "type:N", "title:N"],
                )
            )
    st.altair_chart(alt.layer(*layers).properties(height=260), use_container_width=True)
    st.caption("Dashed markers = SEC filings (hover for details). Price reaction — or lack of it — after a filing is the price-lag signal.")

    if sc_rows and len(sc_rows) >= 2:
        sc_df = pd.DataFrame(sc_rows, columns=["date", "Gem Score", "Narrative", "Value", "Quality", "Gap"])
        sc_df["date"] = pd.to_datetime(sc_df["date"])
        for c in ["Gem Score", "Narrative", "Value", "Quality", "Gap"]:
            sc_df[c] = sc_df[c].astype(float)

        # Gem score vs the tier thresholds — shows distance to upgrade/downgrade
        y_max = max(0.70, float(sc_df["Gem Score"].max()) + 0.05)
        tiers = pd.DataFrame([
            {"y0": _SB,    "y1": y_max, "tier": "Strong Buy", "color": "#dcfce7"},
            {"y0": _BUY,   "y1": _SB,   "tier": "Buy",        "color": "#dbeafe"},
            {"y0": _WATCH, "y1": _BUY,  "tier": "Watch",      "color": "#fef9c3"},
        ])
        bands = alt.Chart(tiers).mark_rect(opacity=0.45).encode(
            y="y0:Q", y2="y1:Q",
            color=alt.Color("color:N", scale=None),
            tooltip=["tier:N"],
        )
        score_line = alt.Chart(sc_df).mark_line(color="#111827", strokeWidth=2.6, point=True).encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("Gem Score:Q", title="Gem score",
                    scale=alt.Scale(domain=[0, y_max])),
            tooltip=[alt.Tooltip("date:T"), alt.Tooltip("Gem Score:Q", format=".3f")],
        )
        st.altair_chart((bands + score_line).properties(height=220), use_container_width=True)
        st.caption(f"Gem score against tier bands (green = Strong Buy >{_SB}, blue = Buy >{_BUY}, "
                   f"yellow = Watch >{_WATCH}). Scores before the 2026-07-22 v2 cutover are on the v1 scale. "
                   "How close is this stock to an upgrade or downgrade?")

        with st.expander("What's driving the score? (component history)"):
            sc_long = sc_df.melt("date", var_name="component", value_name="score")
            comp_chart = alt.Chart(sc_long[sc_long["component"] != "Gem Score"]).mark_line(strokeWidth=1.6).encode(
                x=alt.X("date:T", title=None),
                y=alt.Y("score:Q", title="Component (0–1)", scale=alt.Scale(domain=[0, 1])),
                color=alt.Color("component:N", title=None, scale=alt.Scale(
                    domain=["Narrative", "Value", "Quality", "Gap"],
                    range=["#6366f1", "#0ea5e9", "#10b981", "#f59e0b"])),
                tooltip=[alt.Tooltip("date:T"), "component:N", alt.Tooltip("score:Q", format=".3f")],
            ).properties(height=200)
            st.altair_chart(comp_chart, use_container_width=True)
            st.caption("If the gem score moved, this shows which input (narrative, value, quality, call–filing gap) drove it.")

# Bull / Bear from qual assessment
if key_bull and key_bear:
    st.markdown('<div class="section-hdr">Conviction Summary</div>', unsafe_allow_html=True)
    b1, b2 = st.columns(2)
    with b1:
        st.markdown(f"""
<div class="bull-panel">
  <div class="panel-label">▲ Bull case</div>
  <div class="panel-text">{html_lib.escape(key_bull)}</div>
</div>
""", unsafe_allow_html=True)
    with b2:
        st.markdown(f"""
<div class="bear-panel">
  <div class="panel-label">▼ Bear case</div>
  <div class="panel-text">{html_lib.escape(key_bear)}</div>
</div>
""", unsafe_allow_html=True)

    if rationale:
        # Label must match what actually happened — BR's UPGRADE note once
        # rendered under "Why Claude downgraded" because everything non-upgrade
        # fell into the else branch (2026-07-17).
        label = {"upgrade":   "Why Claude upgraded",
                 "downgrade": "Why Claude downgraded",
                 "hold":      "Why Claude agrees with the score"}.get(
                    direction, "Claude's assessment at the time (historical)")
        st.markdown(f"""
<div class="rationale-box">
  <div class="rationale-label">{label}</div>
  {html_lib.escape(rationale)}
</div>
""", unsafe_allow_html=True)

# Meta-theme alignment
if themes:
    st.markdown('<div class="section-hdr">Macro Theme Alignment</div>', unsafe_allow_html=True)
    theme_cols = st.columns(min(len(themes), 4))
    for i, t in enumerate(themes[:4]):
        pct = int(float(t[1]) * 100)
        traj = (t[2] or "").lower()
        traj_icon = "↑" if "acc" in traj or "improv" in traj else ("↓" if "dec" in traj else "→")
        with theme_cols[i]:
            st.markdown(f"""
<div class="score-card">
  <div class="score-card-label">{t[0]}</div>
  <div class="score-card-value" style="font-size:1rem">{pct}% {traj_icon}</div>
  <div class="score-card-bar">
    <div class="score-card-fill" style="width:{pct}%;background:#6366f1"></div>
  </div>
</div>
""", unsafe_allow_html=True)

# Theme-relative valuation gap — the Dell detector
@st.cache_data(ttl=900)
def load_theme_gaps(sym: str):
    eng = get_engine()
    with eng.connect() as conn:
        try:
            return conn.execute(text("""
                SELECT theme_name, alignment_score, peer_count,
                       stock_pe_fwd, peer_median_pe, pe_discount,
                       stock_ev_ebitda, peer_median_ev, ev_discount
                FROM theme_valuation_gaps
                WHERE symbol = :s
                ORDER BY GREATEST(COALESCE(pe_discount, -9), COALESCE(ev_discount, -9)) DESC
            """), {"s": sym}).fetchall()
        except Exception:
            return []


gaps = load_theme_gaps(symbol)
if gaps:
    st.markdown('<div class="section-hdr">Theme-Relative Valuation (the Dell test)</div>', unsafe_allow_html=True)
    for g in gaps[:2]:
        tname, align, peers, pe_s, med_pe, pe_d, ev_s, med_ev, ev_d = g
        parts = []
        if pe_d is not None:
            direction = "discount" if pe_d > 0 else "premium"
            parts.append(f"<b>{float(pe_s):.1f}x</b> fwd P/E vs theme peers at <b>{float(med_pe):.1f}x</b> "
                         f"→ <b>{abs(float(pe_d))*100:.0f}% {direction}</b>")
        if ev_d is not None:
            direction = "discount" if ev_d > 0 else "premium"
            parts.append(f"{float(ev_s):.1f}x EV/EBITDA vs {float(med_ev):.1f}x → {abs(float(ev_d))*100:.0f}% {direction}")
        headline_d = pe_d if pe_d is not None else ev_d
        border = "#059669" if (headline_d or 0) > 0.25 else ("#f59e0b" if (headline_d or 0) > 0 else "#94a3b8")
        st.markdown(f"""
<div class="filing-card" style="border-left: 3px solid {border};">
  <div class="fc-header">
    <span class="fc-sym">{tname}</span>
    <span class="fc-meta">alignment {float(align):.2f} · {peers} theme peers</span>
  </div>
  <div class="fc-synopsis">{' &nbsp;·&nbsp; '.join(parts) if parts else 'No comparable multiples available.'}</div>
</div>
""", unsafe_allow_html=True)
    st.caption("The Dell test: is this stock priced like its legacy category while its filings show real exposure to an "
               "accelerating structural theme? A large discount to theme peers = the market hasn't re-categorised it yet.")

# ────────────────────────────────────────────────────────────────────────────
# 3. FUNDAMENTALS
# ────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-hdr">Fundamentals</div>', unsafe_allow_html=True)

if fund:
    peg, fwd_pe, trail_pe, rev_g, earn_g, roic, gm, om, nm, fcfm, de, mktcap, \
        high52, low52, pvh, rating, target, n_analysts, _, _ = fund

    left_metrics = [
        ("Fwd P/E",          fmt_x(fwd_pe)),
        ("PEG Ratio",        fmt_x(peg)),
        ("Revenue Growth",   fmt_pct(rev_g)),
        ("Earnings Growth",  fmt_pct(earn_g)),
        ("ROIC",             fmt_pct(roic)),
        ("Gross Margin",     fmt_pct(gm)),
    ]
    right_metrics = [
        ("Operating Margin", fmt_pct(om)),
        ("FCF Margin",       fmt_pct(fcfm)),
        ("Debt / Equity",    fmt_x(de)),
        ("Market Cap",       fmt_m(mktcap)),
        ("vs 52w High",      fmt_pct(pvh) if pvh else "—"),
        ("Analyst Target",   f"${float(target):.0f} ({rating})" if target and rating else fmt_x(target, 0)),
    ]

    col_l, col_r = st.columns(2)
    with col_l:
        for label, val in left_metrics:
            num_val = None
            try:
                if "%" in str(val) and val not in ("—",):
                    num_val = float(val.replace("%","").replace("+",""))
            except: pass
            val_css = ("positive" if num_val and num_val > 0
                       else "negative" if num_val and num_val < 0 else "")
            st.markdown(f"""
<div class="fund-item">
  <span class="fund-label">{label}</span>
  <span class="fund-value {val_css}">{val}</span>
</div>
""", unsafe_allow_html=True)
    with col_r:
        for label, val in right_metrics:
            num_val = None
            try:
                if "%" in str(val) and val not in ("—",):
                    num_val = float(val.replace("%","").replace("+",""))
            except: pass
            val_css = ("positive" if num_val and num_val > 0
                       else "negative" if num_val and num_val < 0 else "")
            st.markdown(f"""
<div class="fund-item">
  <span class="fund-label">{label}</span>
  <span class="fund-value {val_css}">{val}</span>
</div>
""", unsafe_allow_html=True)
else:
    st.info("No fundamentals data available for this stock.")

# ────────────────────────────────────────────────────────────────────────────
# 4. EARNINGS CALL HISTORY
# ────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-hdr">Earnings Call History</div>', unsafe_allow_html=True)

if not calls:
    st.info("No earnings call data found for this stock.")
else:
    for i, call in enumerate(calls):
        call_date, ns, traj, tone, raw_themes, catalysts, risks = call
        date_str = call_date.strftime("%b %d, %Y") if call_date else "Unknown"
        ns_pct   = f"{float(ns)*100:.0f}%" if ns else "—"

        themes_list    = safe_json_list(raw_themes)
        catalyst_list  = safe_json_list(catalysts)
        risk_list      = safe_json_list(risks)

        is_latest = (i == 0)
        with st.expander(
            f"{'📞 Most Recent — ' if is_latest else ''}{date_str}  ·  "
            f"Narrative strength: {ns_pct}",
            expanded=is_latest
        ):
            st.markdown(f"""
<div class="call-header">
  <div class="call-date">{date_str}</div>
  <div class="call-badges">
    {tone_badge(tone)}
    {traj_badge(traj)}
    <span style="font-size:0.72rem;color:#94a3b8">Narrative: {ns_pct}</span>
  </div>
</div>
""", unsafe_allow_html=True)

            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown('<div class="call-section-title">Key Themes</div>', unsafe_allow_html=True)
                for t in themes_list[:4]:
                    st.markdown(f'<div class="call-theme">{t}</div>', unsafe_allow_html=True)
            with c2:
                st.markdown('<div class="call-section-title">Catalysts</div>', unsafe_allow_html=True)
                for c in catalyst_list[:4]:
                    st.markdown(f'<div class="call-catalyst">{c}</div>', unsafe_allow_html=True)
            with c3:
                st.markdown('<div class="call-section-title">Risks</div>', unsafe_allow_html=True)
                for r in risk_list[:4]:
                    st.markdown(f'<div class="call-risk">{r}</div>', unsafe_allow_html=True)

# Top forward-looking claims
if claims:
    st.markdown('<div class="section-hdr">Forward-Looking Claims</div>', unsafe_allow_html=True)
    st.caption("High-confidence statements extracted from earnings calls — "
               "what management committed to on the record.")

    # Group by call date
    claims_by_date = {}
    for c in claims:
        d = str(c[3])
        claims_by_date.setdefault(d, []).append(c)

    for date_key in sorted(claims_by_date.keys(), reverse=True)[:2]:
        st.markdown(f"**{date_key}**")
        for cl in claims_by_date[date_key][:6]:
            claim_type, claim_text, confidence, _, direction_cl = cl
            type_clean = (claim_type or "").replace("_", " ").title()
            dir_icon   = "↑" if direction_cl == "up" else ("↓" if direction_cl == "down" else "→")
            conf_pct   = f"{int(float(confidence)*100)}% confidence" if confidence else ""
            st.markdown(f"""
<div class="claim-item">
  <div class="claim-meta">{type_clean} · {dir_icon} {conf_pct}</div>
  {html_lib.escape(claim_text or "")}
</div>
""", unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────────────────────
# 5. SEC FILINGS
# ────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-hdr">SEC Filings (10-K / 10-Q)</div>', unsafe_allow_html=True)

if not filings:
    st.info("No 10-K/10-Q filing data found for this stock.")
else:
    for i, f in enumerate(filings):
        f_date, f_type, f_ns, f_traj, f_tone, f_themes, f_cats, f_risks, f_url = f
        date_str = f_date.strftime("%b %d, %Y") if f_date else "Unknown"
        ns_pct   = f"{float(f_ns)*100:.0f}%" if f_ns else "—"

        with st.expander(
            f"{f_type} — {date_str}  ·  Narrative: {ns_pct}",
            expanded=(i == 0)
        ):
            st.markdown(f"""
<div class="call-header">
  <div class="call-date">{f_type} · {date_str}</div>
  <div class="call-badges">
    {tone_badge(f_tone)}
    {traj_badge(f_traj)}
  </div>
</div>
""", unsafe_allow_html=True)

            themes_list   = safe_json_list(f_themes)
            catalyst_list = safe_json_list(f_cats)
            risk_list     = safe_json_list(f_risks)

            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown('<div class="call-section-title">Key Themes</div>', unsafe_allow_html=True)
                for t in themes_list[:4]:
                    st.markdown(f'<div class="call-theme">{t}</div>', unsafe_allow_html=True)
            with c2:
                st.markdown('<div class="call-section-title">Catalysts</div>', unsafe_allow_html=True)
                for c in catalyst_list[:4]:
                    st.markdown(f'<div class="call-catalyst">{c}</div>', unsafe_allow_html=True)
            with c3:
                st.markdown('<div class="call-section-title">Risks</div>', unsafe_allow_html=True)
                for r in risk_list[:4]:
                    st.markdown(f'<div class="call-risk">{r}</div>', unsafe_allow_html=True)

            if f_url:
                st.markdown(f"[View on SEC EDGAR ↗]({f_url})")

# ────────────────────────────────────────────────────────────────────────────
# 6. INSIDER ACTIVITY
# ────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-hdr">Insider Activity</div>', unsafe_allow_html=True)

if not trades:
    st.info("No insider trading data available.")
else:
    buys  = [t for t in trades if t[3] == "BUY"]
    sells = [t for t in trades if t[3] == "SELL"]

    total_buy_val  = sum(float(t[6] or 0) for t in buys)
    total_sell_val = sum(float(t[6] or 0) for t in sells)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Insider Buys", len(buys))
    m2.metric("Total Buy Value", fmt_m(total_buy_val))
    m3.metric("Insider Sells", len(sells))
    m4.metric("Total Sell Value", fmt_m(total_sell_val))

    tab_buy, tab_sell = st.tabs([f"🟢 Purchases ({len(buys)})", f"🔴 Sales ({len(sells)})"])

    for tab, trade_list, css, sign in [
        (tab_buy, buys, "trade-buy", "+"),
        (tab_sell, sells, "trade-sell", "-"),
    ]:
        with tab:
            if not trade_list:
                st.caption("No data.")
            for t in trade_list[:15]:
                person, title, t_date, t_type, shares, price, value = t
                val_str    = fmt_m(float(value)) if value else "—"
                shares_str = f"{float(shares):,.0f} shares @ ${float(price):.2f}" if shares and price else ""
                date_str   = t_date.strftime("%b %d, %Y") if t_date else "—"
                st.markdown(f"""
<div class="trade-row {css}">
  <div>
    <div class="trade-person">{person or "Unknown"}</div>
    <div class="trade-title">{title or ""}</div>
    <div class="trade-shares">{shares_str}</div>
  </div>
  <div style="text-align:right">
    <div class="trade-value">{sign}{val_str}</div>
    <div class="trade-date">{date_str}</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────────────────────
# DEEP DIVE — Buffett-style credit memo (on-demand, cached 7 days)
# ────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-hdr">📖 Deep Dive — Buffett Framework</div>', unsafe_allow_html=True)

_dd_key = f"deep_dive_{symbol}"

# Auto-load cached memo from DB on first visit (no click required)
if _dd_key not in st.session_state:
    try:
        from pipeline.deep_dive import get_cached, create_table as _dd_create
        _dd_create(get_engine())
        _cached = get_cached(get_engine(), symbol)
        st.session_state[_dd_key] = _cached  # None if no memo yet
    except Exception:
        st.session_state[_dd_key] = None

# Check staleness (new filing since last generation)
try:
    from pipeline.deep_dive import is_stale
    _memo_stale = is_stale(get_engine(), symbol)
except Exception:
    _memo_stale = False

_force_regen = st.session_state.pop(f"_force_{_dd_key}", False)
_has_memo    = st.session_state.get(_dd_key) is not None

# Controls row — only show Generate if no memo exists; always show Regenerate if one does
_col_btn, _col_info = st.columns([2, 5])
_generate = False

with _col_btn:
    if not _has_memo:
        _generate = st.button("✦ Generate Deep Dive", key="gen_dd",
                              type="primary", use_container_width=True)
    else:
        if st.button("↺ Regenerate", key="regen_dd", use_container_width=True):
            st.session_state[_dd_key] = None
            st.session_state[f"_force_{_dd_key}"] = True
            st.rerun()

with _col_info:
    if _has_memo:
        st.caption(
            "Buffett-framework credit memo · updates automatically when new filings arrive · "
            "~$0.02 per regeneration (Sonnet 4.6) · Not financial advice."
        )
        if _memo_stale:
            st.warning("📬 New filing data available — click Regenerate to refresh.", icon="📬")
    else:
        st.caption(
            "A one-page credit memo in Warren Buffett's framework: "
            "moat, management & shareholders, owner earnings, financial fortress, and margin of safety. "
            "~$0.02 per generation (Sonnet 4.6)."
        )

if _generate:
    with st.spinner(f"Analysing {symbol} through Buffett's lens…"):
        try:
            from pipeline.deep_dive import generate_deep_dive
            _dd_content = generate_deep_dive(get_engine(), symbol, force=_force_regen)
            st.session_state[_dd_key] = _dd_content
        except Exception as _e:
            st.error(f"Deep dive failed: {_e}")

_dd = st.session_state.get(_dd_key)

if _dd:
    _section_labels = {
        "business_quality":                  "① Business Quality",
        "corporate_story":                   "② Corporate Story",
        "economic_moat":                     "③ Economic Moat",
        "management_and_capital_allocation": "④ Management & Capital Allocation",
        "ownership_quality":                 "⑤ Ownership Quality",
        "financial_fortress":                "⑥ Financial Fortress",
        "owner_earnings":                    "⑦ Owner Earnings (FCF)",
        "intrinsic_value":                   "⑧ Intrinsic Value",
    }

    # Render sections in 2 columns (4 left, 4 right)
    _section_keys = list(_section_labels.keys())
    _left_keys  = _section_keys[:4]
    _right_keys = _section_keys[4:]

    _dd_col1, _dd_col2 = st.columns(2)
    for _col, _keys in [(_dd_col1, _left_keys), (_dd_col2, _right_keys)]:
        with _col:
            for _k in _keys:
                if _k in _dd:
                    st.markdown(
                        f'<div class="dd-section">'
                        f'<div class="dd-section-label">{_section_labels[_k]}</div>'
                        f'<div class="dd-section-text">{html_lib.escape(_dd[_k])}</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

    # Verdict (now ⑧) full-width, dark background
    if "verdict" in _dd:
        st.markdown(
            f'<div class="dd-verdict">'
            f'<div class="dd-verdict-label">⑨ Buffett Verdict</div>'
            f'<div class="dd-verdict-text">{html_lib.escape(_dd["verdict"])}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    # Meta
    _meta = _dd.get("_meta", {})
    _gen_at = _meta.get("generated_at", "")[:10]
    _model  = _meta.get("model", MODEL if "MODEL" in dir() else "claude-sonnet-4-6")
    st.markdown(
        f'<div class="dd-meta">Generated {_gen_at} · {_model} · '
        f'Not financial advice.</div>',
        unsafe_allow_html=True
    )
else:
    st.markdown(
        '<div style="color:#94a3b8;font-size:0.85rem;padding:0.5rem 0">'
        'Click <strong>Generate Deep Dive</strong> to run a Buffett-style analysis on this stock.</div>',
        unsafe_allow_html=True
    )

# ────────────────────────────────────────────────────────────────────────────
# AI RESEARCH CHAT  (collapsed by default so the page doesn't jump on load)
# ────────────────────────────────────────────────────────────────────────────
_api_key = os.environ.get("ANTHROPIC_API_KEY")
_chat_key = f"chat_{symbol}"

# Reset chat when symbol changes (do this outside the expander so it always runs)
if st.session_state.get("_last_chat_symbol") != symbol:
    st.session_state[_chat_key] = []
    st.session_state["_last_chat_symbol"] = symbol
if _chat_key not in st.session_state:
    st.session_state[_chat_key] = []

_has_history = bool(st.session_state[_chat_key])
_chat_label  = (
    f"💬 Ask about {symbol}  ·  {len(st.session_state[_chat_key])//2} message(s)"
    if _has_history else f"💬 Ask about {symbol}"
)

with st.expander(_chat_label, expanded=_has_history):
    if not _api_key:
        st.warning("Set ANTHROPIC_API_KEY in .env to enable the research chat.")
    else:
        st.caption(
            f"Ask anything about {symbol} — the model has access to all the data on this page. "
            "Chat resets when you switch stocks or refresh. ~$0.01 per message (Sonnet)."
        )

        if _has_history:
            if st.button("🗑 Clear conversation", key="clear_chat"):
                st.session_state[_chat_key] = []
                st.rerun()

        # Render existing messages
        for _msg in st.session_state[_chat_key]:
            with st.chat_message(_msg["role"]):
                st.markdown(_msg["content"])

        # Chat input
        if _user_q := st.chat_input(f"Ask about {symbol}…"):
            st.session_state[_chat_key].append({"role": "user", "content": _user_q})
            with st.chat_message("user"):
                st.markdown(_user_q)

            # Build system prompt with all stock data
            _context = build_stock_context(symbol, company, gem, qa, fund, calls, filings, claims, trades, themes)
            _system = f"""You are a financial research assistant helping analyse {symbol} ({company}) for a buy-and-hold investor.

You have access to the following data about this stock, sourced from SEC filings, earnings call transcripts, and quantitative scoring:

{_context}

Answer questions factually and specifically using the data above.
Be concise and precise. If the data doesn't cover a question, say so clearly.
Do not give financial advice or make specific buy/sell recommendations — you are an analytical assistant only."""

            # Stream response
            _client = Anthropic(api_key=_api_key)
            with st.chat_message("assistant"):
                with _client.messages.stream(
                    model="claude-sonnet-4-6",
                    max_tokens=1024,
                    system=_system,
                    messages=st.session_state[_chat_key][:-1] + [{"role": "user", "content": _user_q}],
                ) as _stream:
                    _response_text = st.write_stream(_stream.text_stream)

            st.session_state[_chat_key].append({"role": "assistant", "content": _response_text})

st.markdown('<p style="font-size:0.72rem;color:#94a3b8;margin-top:2rem">'
            'Data from SEC EDGAR, Financial Modeling Prep, and Claude AI analysis. '
            'Not financial advice.</p>', unsafe_allow_html=True)
