"""
Today — Daily Intelligence Brief.
The home page: what matters right now, synthesised from SEC filings and insider trades.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

root = Path(__file__).parent.parent
sys.path.insert(0, str(root))
load_dotenv(root / ".env", override=True)

from db.session import get_session
from db.models import WatchlistEntry, ScreenerResult
from pipeline.brief import get_or_generate_brief

st.set_page_config(page_title="Today — Financial Intelligence", page_icon="🏠", layout="wide")

st.markdown("""
<style>
/* ── Layout ── */
.block-container { max-width: 860px; padding: 1.5rem 2rem 4rem; }
[data-testid="stSidebar"] { min-width: 240px; }

/* ── Top signal ── */
.top-signal {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    border-radius: 14px;
    padding: 1.75rem 2rem;
    margin-bottom: 1.5rem;
    color: white;
}
.top-signal-label {
    font-size: 0.7rem; font-weight: 700; letter-spacing: 0.12em;
    text-transform: uppercase; color: #94a3b8; margin-bottom: 0.5rem;
}
.top-signal-symbol {
    display: inline-block; background: #3b82f6; color: white;
    font-size: 0.8rem; font-weight: 800; padding: 0.2rem 0.6rem;
    border-radius: 5px; margin-bottom: 0.6rem; letter-spacing: 0.04em;
}
.top-signal-title { font-size: 1.4rem; font-weight: 800; line-height: 1.3; margin-bottom: 0.75rem; }
.top-signal-body  { font-size: 0.95rem; line-height: 1.65; color: #cbd5e1; margin-bottom: 0.75rem; }
.top-signal-why   { font-size: 0.9rem; line-height: 1.55; color: #7dd3fc;
                    border-left: 3px solid #3b82f6; padding-left: 0.75rem; font-style: italic; }

/* ── Section header ── */
.section-header {
    font-size: 0.72rem; font-weight: 800; letter-spacing: 0.1em;
    text-transform: uppercase; color: #64748b;
    margin: 1.75rem 0 0.75rem; padding-bottom: 0.4rem;
    border-bottom: 1px solid #e2e8f0;
}

/* ── Watch card ── */
.watch-card {
    border: 1px solid #e2e8f0; border-radius: 10px;
    padding: 1rem 1.25rem; margin-bottom: 0.75rem;
    border-left: 4px solid #94a3b8;
}
.watch-card.pos { border-left-color: #22c55e; }
.watch-card.neg { border-left-color: #ef4444; }
.watch-card.neu { border-left-color: #94a3b8; }
.watch-symbol { font-size: 0.75rem; font-weight: 800; letter-spacing: 0.06em; color: #475569; }
.watch-headline { font-size: 1rem; font-weight: 700; margin: 0.2rem 0 0.4rem; color: #0f172a; }
.watch-detail   { font-size: 0.88rem; line-height: 1.55; color: #475569; }
.watch-action   { font-size: 0.8rem; color: #6366f1; margin-top: 0.5rem; font-weight: 600; }

/* ── Radar card ── */
.radar-card {
    background: #f8fafc; border: 1px solid #e2e8f0;
    border-radius: 10px; padding: 0.9rem 1.25rem; margin-bottom: 0.6rem;
}
.radar-pattern { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em;
                 text-transform: uppercase; color: #8b5cf6; margin-bottom: 0.3rem; }
.radar-symbol  { font-weight: 800; color: #0f172a; margin-right: 0.4rem; }
.radar-detail  { font-size: 0.88rem; color: #475569; line-height: 1.5; }
.radar-watch   { font-size: 0.8rem; color: #64748b; margin-top: 0.35rem; }

/* ── Watchlist pill ── */
.wl-pill {
    display: inline-block; background: #f1f5f9; border: 1px solid #e2e8f0;
    border-radius: 20px; padding: 0.25rem 0.7rem;
    font-size: 0.8rem; font-weight: 700; margin: 0.2rem;
}

/* ── Meta ── */
.brief-meta { font-size: 0.75rem; color: #94a3b8; margin-top: 1.5rem; }
</style>
""", unsafe_allow_html=True)

STANCE_CSS = {"POSITIVE": "pos", "NEGATIVE": "neg", "NEUTRAL": "neu"}
STANCE_ICON = {"POSITIVE": "🟢", "NEGATIVE": "🔴", "NEUTRAL": "⚪"}


@st.cache_resource
def get_db():
    return get_session()

session = get_db()

# ---------------------------------------------------------------------------
# Sidebar — watchlist + controls
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🏠 Today")
    st.markdown("---")

    # Watchlist
    st.markdown("**Your Watchlist**")
    watchlist = [w.symbol for w in session.query(WatchlistEntry).all()]

    if watchlist:
        for sym in watchlist:
            col_s, col_x = st.columns([4, 1])
            col_s.markdown(f"**{sym}**")
            if col_x.button("×", key=f"rm_{sym}"):
                session.query(WatchlistEntry).filter_by(symbol=sym).delete()
                session.commit()
                st.rerun()
    else:
        st.caption("No stocks added yet.")

    new_sym = st.text_input("Add symbol", placeholder="e.g. AAPL", label_visibility="collapsed")
    if st.button("＋ Add", use_container_width=True) and new_sym:
        sym_clean = new_sym.strip().upper()
        if not session.query(WatchlistEntry).filter_by(symbol=sym_clean).first():
            session.add(WatchlistEntry(symbol=sym_clean))
            session.commit()
        st.rerun()

    st.markdown("---")

    if st.button("🔄 Regenerate brief", use_container_width=True):
        st.cache_data.clear()
        with st.spinner("Generating…"):
            get_or_generate_brief(session, force=True)
        st.rerun()

    st.caption("Brief generated once daily.\nData from SEC EDGAR + Form 4 filings.")

# ---------------------------------------------------------------------------
# Load brief
# ---------------------------------------------------------------------------
with st.spinner("Loading today's brief…"):
    try:
        brief = get_or_generate_brief(session)
    except Exception as e:
        st.error(f"Could not generate brief: {e}")
        st.stop()

today_str = datetime.utcnow().strftime("%A, %B %d, %Y")
st.markdown(f"## {today_str}")

# Quick start workflow
col1, col2 = st.columns([3, 1])
with col1:
    st.caption("Daily intelligence brief — synthesised from SEC filings and Form 4 insider trades")
with col2:
    if st.button("📊 Go to Screener →", use_container_width=True, key="home_to_screener"):
        st.switch_page("pages/1_Screener.py")

st.info("**New here?** Go to the Screener to find undervalued quality companies by V2 Mismatch Score.")

# ---------------------------------------------------------------------------
# Top Signal
# ---------------------------------------------------------------------------
ts = brief.get("top_signal", {})
if ts:
    symbol_html = (
        f'<div class="top-signal-symbol">{ts["symbol"]}</div>' if ts.get("symbol") else ""
    )
    st.markdown(f"""
<div class="top-signal">
  <div class="top-signal-label">🔔 Top Signal</div>
  {symbol_html}
  <div class="top-signal-title">{ts.get("title", "")}</div>
  <div class="top-signal-body">{ts.get("body", "")}</div>
  <div class="top-signal-why">{ts.get("why_it_matters", "")}</div>
</div>
""", unsafe_allow_html=True)

    if ts.get("symbol"):
        if st.button(f"→ Full analysis for {ts['symbol']}", key="ts_detail"):
            st.session_state["detail_symbol"] = ts["symbol"]
            st.switch_page("pages/4_Stock_Detail.py")

# ---------------------------------------------------------------------------
# 3 Things to Watch
# ---------------------------------------------------------------------------
watch_list = brief.get("watch_list", [])
if watch_list:
    st.markdown('<div class="section-header">📋 Things to Watch</div>', unsafe_allow_html=True)
    for item in watch_list:
        stance = item.get("stance", "NEUTRAL")
        css = STANCE_CSS.get(stance, "neu")
        icon = STANCE_ICON.get(stance, "⚪")
        sym = item.get("symbol", "")
        st.markdown(f"""
<div class="watch-card {css}">
  <div class="watch-symbol">{icon} {sym}</div>
  <div class="watch-headline">{item.get("headline", "")}</div>
  <div class="watch-detail">{item.get("detail", "")}</div>
  <div class="watch-action">▸ Watch for: {item.get("action", "")}</div>
</div>
""", unsafe_allow_html=True)
        if sym:
            if st.button(f"Analyse {sym}", key=f"watch_{sym}"):
                st.session_state["detail_symbol"] = sym
                st.switch_page("pages/4_Stock_Detail.py")

# ---------------------------------------------------------------------------
# On the Radar
# ---------------------------------------------------------------------------
on_radar = brief.get("on_radar", [])
if on_radar:
    st.markdown('<div class="section-header">📡 On the Radar</div>', unsafe_allow_html=True)
    for item in on_radar:
        sym = item.get("symbol", "")
        st.markdown(f"""
<div class="radar-card">
  <div class="radar-pattern">{item.get("pattern", "")}</div>
  <span class="radar-symbol">{sym}</span>
  <span class="radar-detail">{item.get("detail", "")}</span>
  <div class="radar-watch">👀 Watch for: {item.get("watch_for", "")}</div>
</div>
""", unsafe_allow_html=True)
        if sym:
            if st.button(f"Analyse {sym}", key=f"radar_{sym}"):
                st.session_state["detail_symbol"] = sym
                st.switch_page("pages/4_Stock_Detail.py")

# ---------------------------------------------------------------------------
# Watchlist quick-view
# ---------------------------------------------------------------------------
if watchlist:
    st.markdown('<div class="section-header">👁 Your Watchlist</div>', unsafe_allow_html=True)
    cols = st.columns(min(len(watchlist), 5))
    for i, sym in enumerate(watchlist):
        sr = session.query(ScreenerResult).filter_by(symbol=sym).first()
        with cols[i % len(cols)]:
            score_str = f"{sr.score:+d}" if sr and sr.score is not None else "—"
            label = f"{sym}\n{score_str}"
            if st.button(label, key=f"wl_{sym}", use_container_width=True):
                st.session_state["detail_symbol"] = sym
                st.switch_page("pages/4_Stock_Detail.py")

st.markdown('<div class="brief-meta">Powered by SEC EDGAR public data and Claude AI. Not financial advice.</div>', unsafe_allow_html=True)
