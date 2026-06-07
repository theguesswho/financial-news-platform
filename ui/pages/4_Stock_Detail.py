"""
Stock Detail — unified signal timeline for a single stock.
All filings, insider trades, and events in one chronological view.
"""
import json
import os
import sys
from pathlib import Path
from datetime import datetime, date

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root))
load_dotenv(root / ".env", override=True)

from db.session import get_session
from db.models import Filing, InsiderTrade, EodPrice, ScreenerResult, WatchlistEntry, Fundamentals
from sqlalchemy import desc

st.set_page_config(page_title="Stock Detail", page_icon="📊", layout="wide")

st.markdown("""
<style>
.block-container { max-width: 920px; padding: 1.5rem 2rem 4rem; }

/* Signal timeline */
.tl-item {
    display: flex; gap: 1rem; margin-bottom: 1rem;
    padding-bottom: 1rem; border-bottom: 1px solid #f1f5f9;
}
.tl-date  { min-width: 80px; font-size: 0.78rem; color: #94a3b8;
             font-weight: 600; padding-top: 0.15rem; text-align: right; }
.tl-icon  { font-size: 1.1rem; min-width: 24px; text-align: center; padding-top: 0.05rem; }
.tl-body  { flex: 1; }
.tl-title { font-size: 0.95rem; font-weight: 700; color: #0f172a; margin-bottom: 0.15rem; }
.tl-sub   { font-size: 0.83rem; color: #64748b; line-height: 1.5; }
.tl-badge {
    display: inline-block; font-size: 0.7rem; font-weight: 700;
    padding: 0.1rem 0.45rem; border-radius: 4px; margin-left: 0.4rem;
    vertical-align: middle;
}
.badge-pos { background: #dcfce7; color: #166534; }
.badge-neg { background: #fee2e2; color: #991b1b; }
.badge-neu { background: #f1f5f9; color: #475569; }
.badge-buy  { background: #dbeafe; color: #1e40af; }
.badge-sell { background: #fef9c3; color: #854d0e; }

/* Stat cards */
.stat-card {
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px;
    padding: 1rem 1.25rem; text-align: center;
}
.stat-label { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.07em;
              text-transform: uppercase; color: #94a3b8; margin-bottom: 0.3rem; }
.stat-value { font-size: 1.5rem; font-weight: 800; color: #0f172a; }
.stat-sub   { font-size: 0.78rem; color: #64748b; margin-top: 0.1rem; }
</style>
""", unsafe_allow_html=True)


def safe_text(t: str) -> str:
    return t.replace("$", "USD ") if t else ""


@st.cache_resource
def get_db():
    return get_session()

session = get_db()

# ---------------------------------------------------------------------------
# Symbol selection
# ---------------------------------------------------------------------------
all_symbols = sorted(set(
    [r[0] for r in session.query(Filing.symbol).distinct().all()] +
    [r[0] for r in session.query(InsiderTrade.symbol).distinct().all()]
))

default = st.session_state.get("detail_symbol", all_symbols[0] if all_symbols else "AAPL")
if default not in all_symbols and all_symbols:
    default = all_symbols[0]

with st.sidebar:
    # Navigation
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("← Back to Screener", use_container_width=True, key="back_btn"):
            st.switch_page("pages/1_Screener.py")
    with col2:
        st.write("")  # spacer

    st.markdown("---")
    st.markdown("### 📊 View Stock")
    symbol = st.selectbox("Company", all_symbols, index=all_symbols.index(default) if default in all_symbols else 0, label_visibility="collapsed")

    # Watchlist toggle
    in_wl = session.query(WatchlistEntry).filter_by(symbol=symbol).first()
    if in_wl:
        if st.button("★ Remove from Watchlist", use_container_width=True):
            session.delete(in_wl)
            session.commit()
            st.rerun()
    else:
        if st.button("☆ Add to Watchlist", use_container_width=True):
            session.add(WatchlistEntry(symbol=symbol))
            session.commit()
            st.rerun()

    st.markdown("---")
    st.caption("Signal timeline combines 10-K/10-Q filings, 8-K events, and Form 4 insider trades.")

if not all_symbols:
    st.warning("No data yet. Run `python run.py pipeline` first.")
    st.stop()

# ---------------------------------------------------------------------------
# Load all data for this symbol
# ---------------------------------------------------------------------------
filings = (
    session.query(Filing)
    .filter(Filing.symbol == symbol)
    .order_by(desc(Filing.filing_date))
    .limit(30)
    .all()
)
trades = (
    session.query(InsiderTrade)
    .filter(InsiderTrade.symbol == symbol)
    .order_by(desc(InsiderTrade.transaction_date))
    .limit(50)
    .all()
)
prices = (
    session.query(EodPrice)
    .filter(EodPrice.symbol == symbol)
    .order_by(EodPrice.date)
    .limit(90)
    .all()
)
screener = session.query(ScreenerResult).filter_by(symbol=symbol).first()
fund = session.query(Fundamentals).filter_by(symbol=symbol).first()

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
company_name = screener.company_name if screener and screener.company_name else symbol
header_text = f"{symbol} - {company_name}" if company_name != symbol else symbol
st.markdown(f"# {header_text}")
st.info(f"**Workflow:** Back to screener to find more → Details (you are here) → Add to watchlist if interested")
st.markdown("---")

# Quick stats
c1, c2, c3, c4 = st.columns(4)
with c1:
    if prices:
        latest = float(prices[-1].close)
        prev = float(prices[-2].close) if len(prices) > 1 else latest
        pct = (latest - prev) / prev * 100
        arrow = "▲" if pct >= 0 else "▼"
        color = "green" if pct >= 0 else "red"
        st.markdown(f"""<div class="stat-card">
            <div class="stat-label">Price</div>
            <div class="stat-value">USD {latest:.2f}</div>
            <div class="stat-sub" style="color:{color}">{arrow} {abs(pct):.2f}%</div>
        </div>""", unsafe_allow_html=True)
    else:
        st.markdown('<div class="stat-card"><div class="stat-label">Price</div><div class="stat-value">—</div></div>', unsafe_allow_html=True)

with c2:
    v2_score = float(screener.v2_mismatch_score) if screener and screener.v2_mismatch_score else None
    v2_str = f"{v2_score:.3f}" if v2_score else "—"
    v2_color = "#22c55e" if v2_score and v2_score >= 0.60 else ("#ef4444" if v2_score and v2_score < 0.40 else "#64748b")
    st.markdown(f"""<div class="stat-card">
        <div class="stat-label">V2 Mismatch Score</div>
        <div class="stat-value" style="color:{v2_color}">{v2_str}</div>
        <div class="stat-sub">out of ±10</div>
    </div>""", unsafe_allow_html=True)

with c3:
    buy_count = sum(1 for t in trades if t.transaction_type == "BUY")
    buy_val = sum(float(t.total_value or 0) for t in trades if t.transaction_type == "BUY")
    buy_str = f"USD {buy_val/1e6:.1f}M" if buy_val >= 1e6 else f"USD {buy_val:,.0f}"
    st.markdown(f"""<div class="stat-card">
        <div class="stat-label">Insider Buys (90d)</div>
        <div class="stat-value">{buy_count}</div>
        <div class="stat-sub">{buy_str}</div>
    </div>""", unsafe_allow_html=True)

with c4:
    events_8k = [f for f in filings if f.filing_type in ("8-K", "8-K/A")]
    st.markdown(f"""<div class="stat-card">
        <div class="stat-label">Events (90d)</div>
        <div class="stat-value">{len(events_8k)}</div>
        <div class="stat-sub">material 8-K filings</div>
    </div>""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Score Breakdown
# ---------------------------------------------------------------------------
if screener and screener.v2_mismatch_score:
    from pipeline.score import compute_v2_score_with_breakdown

    breakdown = compute_v2_score_with_breakdown(fund, session) if fund else None

    if breakdown:
        st.markdown("### Score Breakdown")
        st.markdown(f"**How we arrived at {breakdown['final_score']:.3f}** (V2 = Quality × Value × Trajectory)^(1/3)")

        col1, col2, col3 = st.columns(3)

        with col1:
            q_pct = breakdown['quality_score'] * 100
            st.metric("Quality Score", f"{breakdown['quality_score']:.3f}", delta=f"{q_pct:.0f}%")
            with st.expander("Quality details"):
                bd = breakdown['breakdown']['quality']
                roic = bd.get('roic', {}).get('value')
                gm = bd.get('gross_margin', {}).get('value')
                om = bd.get('operating_margin', {}).get('value')
                de = bd.get('debt_to_equity', {}).get('value')
                st.write(f"**ROIC:** {roic*100:.1f}%" if roic else "ROIC: —")
                st.write(f"**Gross Margin:** {gm*100:.1f}%" if gm else "Gross Margin: —")
                st.write(f"**Operating Margin:** {om*100:.1f}%" if om else "Operating Margin: —")
                st.write(f"**Debt/Equity:** {de:.2f}x" if de else "Debt/Equity: —")

        with col2:
            v_pct = breakdown['value_score'] * 100
            st.metric("Value Score", f"{breakdown['value_score']:.3f}", delta=f"{v_pct:.0f}%")
            with st.expander("Value details"):
                bd = breakdown['breakdown']['value']
                pe = bd.get('pe_ratio', {}).get('value')
                pfcf = bd.get('pfcf_ratio', {}).get('value')
                pvh = bd.get('price_vs_52w', {}).get('value')
                st.write(f"**P/E Ratio:** {pe:.1f}x" if pe else "P/E: —")
                st.write(f"**P/FCF Ratio:** {pfcf:.1f}x" if pfcf else "P/FCF: —")
                st.write(f"**Price vs 52w High:** {pvh*100:.0f}%" if pvh else "Price vs 52w High: —")

        with col3:
            t_pct = breakdown['trajectory_score'] * 100
            st.metric("Trajectory Score", f"{breakdown['trajectory_score']:.3f}", delta=f"{t_pct:.0f}%")
            with st.expander("Trajectory details"):
                bd = breakdown['breakdown']['trajectory']
                rg = bd.get('revenue_growth_yoy', {}).get('value')
                fcf_g = bd.get('fcf_growth_yoy', {}).get('value')
                mt = bd.get('margin_trend', {})
                mt_score = mt.get('score')
                mt_change = mt.get('change_pp')
                st.write(f"**Revenue Growth YoY:** {rg*100:+.1f}%" if rg is not None else "Revenue Growth: —")
                st.write(f"**FCF Growth YoY:** {fcf_g*100:+.1f}%" if fcf_g is not None else "FCF Growth: —")
                if mt_score is not None:
                    arrow = "📈" if mt_change and mt_change > 0 else ("📉" if mt_change and mt_change < 0 else "➡️")
                    change_str = f"{mt_change*100:+.1f}pp" if mt_change is not None else "—"
                    st.write(f"**Margin Trend:** {arrow} {change_str} (5q)")

        st.markdown(f"**Business Type:** {breakdown['business_type'].replace('_', ' ').title()}")
        st.markdown("---")

# ---------------------------------------------------------------------------
# Price chart
# ---------------------------------------------------------------------------
if prices:
    with st.expander("Price chart (last 90 days)", expanded=True):
        df = pd.DataFrame(
            {"Close": [float(p.close) for p in prices]},
            index=[p.date for p in prices],
        )
        st.line_chart(df, height=200)

# Screener one-liner
if screener and screener.one_liner:
    st.info(f"**AI Summary:** {safe_text(screener.one_liner)}")

st.markdown("---")

# ---------------------------------------------------------------------------
# Signal timeline
# ---------------------------------------------------------------------------
st.markdown("### Signal Timeline")
st.caption("All filings, events, and insider trades in reverse chronological order.")

# Build unified timeline
timeline = []

for f in filings:
    analysis = {}
    if f.llm_analysis:
        try:
            analysis = json.loads(f.llm_analysis)
        except Exception:
            pass

    if f.filing_type in ("8-K", "8-K/A"):
        impact = analysis.get("impact", "NEUTRAL")
        badge_cls = {"POSITIVE": "pos", "NEGATIVE": "neg"}.get(impact, "neu")
        timeline.append({
            "date": f.filing_date,
            "sort_key": f.filing_date or datetime.min,
            "icon": "⚡",
            "title": analysis.get("headline") or f.title or "8-K Filing",
            "sub": safe_text(analysis.get("summary", "")),
            "badge": impact,
            "badge_cls": badge_cls,
            "type": "event",
            "filing": f,
            "analysis": analysis,
        })
    else:
        score = f.sentiment_score
        badge_cls = "pos" if score and score >= 4 else ("neg" if score and score <= -4 else "neu")
        badge = f"{score:+d}" if score is not None else "—"
        summary = analysis.get("summary", "") if analysis else ""
        timeline.append({
            "date": f.filing_date,
            "sort_key": f.filing_date or datetime.min,
            "icon": "📄",
            "title": f"{f.filing_type} Filing",
            "sub": safe_text(summary),
            "badge": badge,
            "badge_cls": badge_cls,
            "type": "filing",
            "filing": f,
            "analysis": analysis,
        })

for t in trades:
    val = float(t.total_value or 0)
    val_str = f"USD {val/1e6:.2f}M" if val >= 1e6 else f"USD {val:,.0f}"
    is_buy = t.transaction_type == "BUY"
    timeline.append({
        "date": datetime.combine(t.transaction_date, datetime.min.time()) if t.transaction_date else None,
        "sort_key": datetime.combine(t.transaction_date, datetime.min.time()) if t.transaction_date else datetime.min,
        "icon": "🟢" if is_buy else "🔴",
        "title": f"Insider {'Purchase' if is_buy else 'Sale'} — {t.person_name or 'Unknown'}",
        "sub": f"{t.person_title or 'Insider'} · {t.shares:,.0f} shares at USD {float(t.price_per_share or 0):.2f}" if t.shares else "",
        "badge": val_str,
        "badge_cls": "buy" if is_buy else "sell",
        "type": "trade",
        "trade": t,
    })

timeline.sort(key=lambda x: x["sort_key"], reverse=True)

if not timeline:
    st.info("No signals yet for this symbol. Run the pipeline to gather data.")
else:
    for item in timeline:
        date_str = item["date"].strftime("%b %d, %Y") if item.get("date") else "—"
        badge_html = f'<span class="tl-badge badge-{item["badge_cls"]}">{item["badge"]}</span>'

        st.markdown(f"""
<div class="tl-item">
  <div class="tl-date">{date_str}</div>
  <div class="tl-icon">{item["icon"]}</div>
  <div class="tl-body">
    <div class="tl-title">{item["title"]}{badge_html}</div>
    <div class="tl-sub">{item["sub"]}</div>
  </div>
</div>
""", unsafe_allow_html=True)

        # Expandable detail for filings
        if item["type"] in ("filing", "event") and item.get("filing"):
            f = item["filing"]
            analysis = item.get("analysis", {})
            with st.expander("Full analysis" if f.master_analysis else "View details"):
                if f.filing_type in ("8-K", "8-K/A"):
                    if f.master_analysis:
                        st.write(safe_text(f.master_analysis))
                    elif analysis.get("summary"):
                        st.write(safe_text(analysis["summary"]))
                else:
                    if f.master_analysis:
                        st.write(safe_text(f.master_analysis))
                    else:
                        risks = analysis.get("key_risks", [])
                        opps = analysis.get("key_opportunities", [])
                        if risks or opps:
                            col_r, col_o = st.columns(2)
                            with col_r:
                                if risks:
                                    st.markdown("**Key Risks**")
                                    for r in risks:
                                        st.write(f"• {safe_text(r)}")
                            with col_o:
                                if opps:
                                    st.markdown("**Key Opportunities**")
                                    for o in opps:
                                        st.write(f"• {safe_text(o)}")
                st.markdown(f"[View on SEC EDGAR ↗]({f.url})")
