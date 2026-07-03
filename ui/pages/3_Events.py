"""
Material Events feed — recent 8-K filings classified by type and impact.
"""
import json
import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root))
load_dotenv(root / ".env", override=True)

from db.session import get_session
from db.models import Filing
from sqlalchemy import desc

st.set_page_config(page_title="Material Events", page_icon="⚡", layout="wide")

st.markdown("""
<style>
.block-container { max-width: 960px; padding: 3.5rem 2rem 4rem; }
header[data-testid="stHeader"] { display: none; }
.event-card { border-radius: 10px; padding: 1rem 1.25rem; margin-bottom: 1rem; border-left: 5px solid #ccc; background: #fafafa; }
.event-positive { border-left-color: #28a745; background: #f6fff8; }
.event-negative { border-left-color: #dc3545; background: #fff6f6; }
.event-neutral  { border-left-color: #6c757d; background: #fafafa; }
.event-meta { font-size: 0.8rem; color: #888; margin-bottom: 0.25rem; }
.event-headline { font-size: 1.05rem; font-weight: 700; margin-bottom: 0.4rem; }
.event-summary { font-size: 0.92rem; line-height: 1.6; color: #2c2c2c; }
.badge { display: inline-block; font-size: 0.72rem; font-weight: 700; padding: 0.15rem 0.5rem; border-radius: 4px; margin-right: 0.4rem; text-transform: uppercase; letter-spacing: 0.04em; }
.badge-EARNINGS     { background: #cfe2ff; color: #084298; }
.badge-MA           { background: #d1e7dd; color: #0a3622; }
.badge-EXEC_CHANGE  { background: #fff3cd; color: #664d03; }
.badge-GUIDANCE     { background: #e2d9f3; color: #432874; }
.badge-RESTRUCTURING{ background: #f8d7da; color: #842029; }
.badge-LEGAL        { background: #fde8d4; color: #7a3000; }
.badge-OTHER        { background: #e2e3e5; color: #383d41; }
</style>
""", unsafe_allow_html=True)

EVENT_LABELS = {
    "EARNINGS": "Earnings",
    "M&A": "M&A",
    "EXEC_CHANGE": "Exec Change",
    "GUIDANCE": "Guidance",
    "RESTRUCTURING": "Restructuring",
    "LEGAL": "Legal",
    "OTHER": "Other",
}

IMPACT_ICONS = {"POSITIVE": "🟢", "NEGATIVE": "🔴", "NEUTRAL": "⚪"}


def get_db():
    return get_session()

session = get_db()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## ⚡ Material Events")
    st.markdown("---")

    event_type_filter = st.multiselect(
        "Event type",
        list(EVENT_LABELS.keys()),
        default=list(EVENT_LABELS.keys()),
        format_func=lambda x: EVENT_LABELS[x],
    )

    impact_filter = st.multiselect(
        "Impact",
        ["POSITIVE", "NEGATIVE", "NEUTRAL"],
        default=["POSITIVE", "NEGATIVE", "NEUTRAL"],
    )

    symbol_search = st.text_input("Filter by symbol", "").strip().upper()
    n_events = st.slider("Show last N events", 10, 100, 30)
    st.markdown("---")
    st.caption("8-K filings analysed by Claude Haiku.\nNot financial advice.")

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
q = (
    session.query(Filing)
    .filter(Filing.filing_type.in_(["8-K", "8-K/A"]))
    .order_by(desc(Filing.filing_date))
)
if symbol_search:
    q = q.filter(Filing.symbol == symbol_search)

filings = q.limit(200).all()

# Filter in Python (event_type / impact stored in llm_analysis JSON)
def get_analysis(f):
    try:
        return json.loads(f.llm_analysis) if f.llm_analysis else {}
    except Exception:
        return {}

def matches_filters(f, analysis):
    et = f.event_type or "OTHER"
    impact = analysis.get("impact", "NEUTRAL")
    if event_type_filter and et not in event_type_filter:
        return False
    if impact_filter and impact not in impact_filter:
        return False
    return True

filtered = []
for f in filings:
    a = get_analysis(f)
    if matches_filters(f, a):
        filtered.append((f, a))
    if len(filtered) >= n_events:
        break

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("⚡ Material Events")

if not filtered:
    st.info("No 8-K events yet. Run `python run.py events` to fetch recent filings.")
    st.stop()

total = len(filtered)
pos = sum(1 for _, a in filtered if a.get("impact") == "POSITIVE")
neg = sum(1 for _, a in filtered if a.get("impact") == "NEGATIVE")

c1, c2, c3 = st.columns(3)
c1.metric("Events shown", total)
c2.metric("🟢 Positive", pos)
c3.metric("🔴 Negative", neg)
st.markdown("---")

# ---------------------------------------------------------------------------
# Event feed
# ---------------------------------------------------------------------------
for filing, analysis in filtered:
    impact = analysis.get("impact", "NEUTRAL")
    event_type = filing.event_type or "OTHER"
    headline = analysis.get("headline") or filing.title or "8-K Filing"
    summary = analysis.get("summary", "")
    icon = IMPACT_ICONS.get(impact, "⚪")
    css_class = f"event-{impact.lower()}"
    badge_class = f"badge-{event_type.replace('&', 'A').replace('/', '_')}"
    label = EVENT_LABELS.get(event_type, event_type)
    date_str = filing.filing_date.strftime("%b %d, %Y") if filing.filing_date else "—"

    st.markdown(f"""
<div class="event-card {css_class}">
  <div class="event-meta">
    <strong>{filing.symbol}</strong> &nbsp;·&nbsp; {date_str} &nbsp;·&nbsp;
    <span class="badge {badge_class}">{label}</span>
    {icon}
  </div>
  <div class="event-headline">{headline}</div>
  <div class="event-summary">{summary.replace("$", "USD ")}</div>
</div>
""", unsafe_allow_html=True)

    with st.expander("View full filing ↗"):
        st.markdown(f"[Open on SEC EDGAR]({filing.url})")
        if filing.content:
            st.text(filing.content[:3000])
