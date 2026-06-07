import json
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

root = Path(__file__).parent.parent
sys.path.insert(0, str(root))
load_dotenv(root / ".env", override=True)

from db.session import get_session
from db.models import Filing, EodPrice
from sqlalchemy import desc

# ---------------------------------------------------------------------------
# Page config & CSS
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Financial Intelligence", page_icon="📈", layout="wide")

st.markdown("""
<style>
/* Constrain main content width */
.block-container { max-width: 960px; padding: 2rem 2rem 4rem; }

/* Filing cards */
.card {
    background: #f8f9fa;
    border: 1px solid #e0e0e0;
    border-radius: 10px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1.25rem;
}
.card-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 0.5rem;
}
.filing-type { font-size: 0.8rem; font-weight: 600; color: #666; text-transform: uppercase; letter-spacing: 0.05em; }
.filing-date { font-size: 1.05rem; font-weight: 700; color: #1a1a1a; }
.badge {
    font-size: 0.85rem;
    font-weight: 600;
    padding: 0.25rem 0.75rem;
    border-radius: 20px;
    white-space: nowrap;
}
.badge-bull  { background: #d4edda; color: #155724; }
.badge-bear  { background: #f8d7da; color: #721c24; }
.badge-neut  { background: #fff3cd; color: #856404; }
.badge-none  { background: #e2e3e5; color: #383d41; }
.section-label { font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: #888; margin: 0.75rem 0 0.25rem; }
.summary-text { font-size: 0.95rem; line-height: 1.6; color: #2c2c2c; }
.bullet-item { font-size: 0.9rem; color: #3c3c3c; margin: 0.15rem 0; }
.health-box { background: #eef2ff; border-left: 3px solid #4f46e5; padding: 0.5rem 0.75rem; border-radius: 0 6px 6px 0; font-size: 0.9rem; color: #2c2c2c; margin-top: 0.75rem; }
.source-link { font-size: 0.8rem; color: #888; margin-top: 0.75rem; }
</style>
""", unsafe_allow_html=True)


def safe_md(text: str) -> None:
    """Render text as markdown with dollar signs escaped so they aren't treated as LaTeX."""
    st.markdown(text.replace("$", r"\$"))


def sentiment_badge(score) -> str:
    if score is None:
        return '<span class="badge badge-none">Unscored</span>'
    if score >= 4:
        return f'<span class="badge badge-bull">🟢 Bullish ({score:+d})</span>'
    if score <= -4:
        return f'<span class="badge badge-bear">🔴 Bearish ({score:+d})</span>'
    return f'<span class="badge badge-neut">🟡 Neutral ({score:+d})</span>'


# ---------------------------------------------------------------------------
# DB session
# ---------------------------------------------------------------------------
@st.cache_resource
def get_db():
    return get_session()

session = get_db()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 📈 Financial Intelligence")
    st.markdown("---")

    all_symbols = [
        row[0]
        for row in session.query(Filing.symbol).distinct().order_by(Filing.symbol).all()
    ]

    if not all_symbols:
        st.warning("No filings yet. Run `python run.py ingest` first.")
        st.stop()

    selected = st.selectbox("Company", all_symbols)
    filing_types = st.multiselect("Filing types", ["10-K", "10-Q", "8-K"], default=["10-K", "10-Q"])
    n = st.slider("Show last N filings", 1, 20, 5)
    st.markdown("---")
    if st.button("🔄 Refresh"):
        st.cache_resource.clear()
        st.rerun()

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
q = session.query(Filing).filter(Filing.symbol == selected).order_by(desc(Filing.filing_date))
if filing_types:
    q = q.filter(Filing.filing_type.in_(filing_types))
filings = q.limit(n).all()

prices = (
    session.query(EodPrice)
    .filter(EodPrice.symbol == selected)
    .order_by(EodPrice.date)
    .limit(90)
    .all()
)

# ---------------------------------------------------------------------------
# Header metrics
# ---------------------------------------------------------------------------
st.markdown(f"## {selected}")

if prices:
    latest, prev = prices[-1], prices[-2] if len(prices) > 1 else prices[-1]
    pct = (float(latest.close) - float(prev.close)) / float(prev.close) * 100 if prev.close else 0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Price", f"${float(latest.close):.2f}", f"{pct:+.2f}%")
    c2.metric("As of", str(latest.date))
    c3.metric("Filings shown", len(filings))
    c4.metric("Analyzed", sum(1 for f in filings if f.master_analysis))

# ---------------------------------------------------------------------------
# Price chart — constrained width
# ---------------------------------------------------------------------------
if prices:
    df = pd.DataFrame(
        {"Close ($)": [float(p.close) for p in prices]},
        index=[p.date for p in prices],
    )
    with st.expander("Price chart (last 90 days)", expanded=True):
        st.line_chart(df, height=220)

st.markdown("---")

# ---------------------------------------------------------------------------
# Filing cards
# ---------------------------------------------------------------------------
if not filings:
    st.info(f"No {' / '.join(filing_types)} filings found for {selected}.")
    st.stop()

for filing in filings:
    date_str = filing.filing_date.strftime("%Y-%m-%d") if filing.filing_date else "—"
    badge = sentiment_badge(filing.sentiment_score)

    # Parse structured analysis
    analysis = {}
    if filing.llm_analysis:
        try:
            analysis = json.loads(filing.llm_analysis)
        except (json.JSONDecodeError, TypeError):
            pass

    # Build card HTML header
    st.markdown(f"""
<div class="card">
  <div class="card-header">
    <div>
      <div class="filing-type">{filing.filing_type}</div>
      <div class="filing-date">{date_str}</div>
    </div>
    {badge}
  </div>
</div>
""", unsafe_allow_html=True)

    # Summary (plain write — avoids markdown misinterpretation entirely)
    if analysis.get("summary"):
        st.markdown('<div class="section-label">Summary</div>', unsafe_allow_html=True)
        safe_md(analysis["summary"])

    # Risks & Opportunities
    risks = analysis.get("key_risks", [])
    opps = analysis.get("key_opportunities", [])
    if risks or opps:
        col_r, col_o = st.columns(2)
        with col_r:
            if risks:
                st.markdown('<div class="section-label">Key Risks</div>', unsafe_allow_html=True)
                for r in risks:
                    safe_md(f"• {r}")
        with col_o:
            if opps:
                st.markdown('<div class="section-label">Key Opportunities</div>', unsafe_allow_html=True)
                for o in opps:
                    safe_md(f"• {o}")

    # Financial health
    if analysis.get("financial_health"):
        st.markdown(
            f'<div class="health-box">💼 {analysis["financial_health"]}</div>',
            unsafe_allow_html=True,
        )

    # Master investment brief
    if filing.master_analysis:
        with st.expander("Full investment brief"):
            # Strip the trailing "Sentiment Score: X" line before displaying
            lines = [
                l for l in filing.master_analysis.splitlines()
                if "sentiment score:" not in l.lower()
            ]
            safe_md("\n".join(lines).strip())

    st.markdown(
        f'<div class="source-link"><a href="{filing.url}" target="_blank">View original filing ↗</a></div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
