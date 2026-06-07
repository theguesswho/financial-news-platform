"""
Screener page — ranked view of all analyzed stocks by AI sentiment.
"""
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root))
load_dotenv(root / ".env", override=True)

from db.session import get_session
from db.models import ScreenerResult

st.set_page_config(page_title="Stock Screener", page_icon="🔍", layout="wide")

st.markdown("""
<style>
.block-container { max-width: 1100px; padding: 2rem 2rem 4rem; }
.metric-row { display: flex; gap: 1rem; margin-bottom: 1.5rem; }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_db():
    return get_session()

session = get_db()

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🔍 Screener")
    st.markdown("---")

    score_filter = st.selectbox(
        "V2 Mismatch Score",
        ["All", "High (≥ 0.60)", "Medium (0.40-0.60)", "Low (< 0.40)"],
    )

    filing_filter = st.multiselect("Filing type", ["10-K", "10-Q"], default=["10-K", "10-Q"])

    sort_by = st.selectbox(
        "Sort by",
        ["V2 Score (high → low)", "V2 Score (low → high)", "Symbol A→Z", "Most recent filing"],
    )

    search = st.text_input("Search symbol or company", "").strip().upper()
    st.markdown("---")
    st.caption("V2 Mismatch Score: identifies quality companies where fundamentals are improving but market hasn't repriced.\nClick a row for full analysis.")

# ---------------------------------------------------------------------------
# Load & filter data
# ---------------------------------------------------------------------------
rows = session.query(ScreenerResult).all()

if not rows:
    st.title("🔍 Stock Screener")
    st.info("No screener results yet. Run `python run.py screen` to score all tickers.")
    st.stop()

data = [
    {
        "Symbol": r.symbol,
        "Company": r.company_name or r.symbol,
        "Type": r.filing_type or "—",
        "Filed": r.filing_date.strftime("%Y-%m-%d") if r.filing_date else "—",
        "V2 Score": float(r.v2_mismatch_score) if r.v2_mismatch_score else 0.0,
        "Sentiment": int(r.sentiment_score) if r.sentiment_score else 0,
        "Summary": r.one_liner or "—",
        "Price": float(r.latest_close) if r.latest_close else None,
        "Chg %": float(r.price_change_pct) if r.price_change_pct else None,
    }
    for r in rows
]
df = pd.DataFrame(data)

# Apply filters
if search:
    df = df[df["Symbol"].str.contains(search) | df["Company"].str.upper().str.contains(search)]

if filing_filter:
    df = df[df["Type"].isin(filing_filter)]

if score_filter == "High (≥ 0.60)":
    df = df[df["V2 Score"] >= 0.60]
elif score_filter == "Medium (0.40-0.60)":
    df = df[df["V2 Score"].between(0.40, 0.60)]
elif score_filter == "Low (< 0.40)":
    df = df[df["V2 Score"] < 0.40]

# Sort
if sort_by == "V2 Score (high → low)":
    df = df.sort_values("V2 Score", ascending=False)
elif sort_by == "V2 Score (low → high)":
    df = df.sort_values("V2 Score", ascending=True)
elif sort_by == "Symbol A→Z":
    df = df.sort_values("Symbol")
elif sort_by == "Most recent filing":
    df = df.sort_values("Filed", ascending=False)

df = df.reset_index(drop=True)

# ---------------------------------------------------------------------------
# Header metrics
# ---------------------------------------------------------------------------
st.title("🔍 Stock Screener")

total = len(rows)
high = sum(1 for r in rows if r.v2_mismatch_score and r.v2_mismatch_score >= 0.60)
medium = sum(1 for r in rows if r.v2_mismatch_score and 0.40 <= r.v2_mismatch_score < 0.60)
low = sum(1 for r in rows if r.v2_mismatch_score and r.v2_mismatch_score < 0.40)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Stocks scored", total)
c2.metric("🟢 High (≥0.60)", high)
c3.metric("🟡 Medium", medium)
c4.metric("🔴 Low", low)

st.markdown(f"*Showing {len(df)} of {total} stocks*")

# Workflow indicator
st.info("**Workflow:** 1️⃣ Sort/filter stocks below → 2️⃣ Select one to view full analysis")

st.markdown("---")

# ---------------------------------------------------------------------------
# Styled table
# ---------------------------------------------------------------------------
def v2_to_label(s):
    if s >= 0.60:   return f"🟢 {s:.3f}"
    if s >= 0.40:   return f"🟡 {s:.3f}"
    return f"🔴 {s:.3f}"

def sentiment_to_label(s):
    if s >= 4:   return f"↑ {s:+d}"
    if s <= -4:  return f"↓ {s:+d}"
    return f"— {s:+d}"

def fmt_price(p):
    return f"${p:.2f}" if p else "—"

def fmt_chg(c):
    if c is None: return "—"
    arrow = "▲" if c >= 0 else "▼"
    return f"{arrow} {abs(c):.2f}%"

display = df.copy()
display["V2"] = display["V2 Score"].apply(v2_to_label)
display["Filing Sentiment"] = display["Sentiment"].apply(sentiment_to_label)
display["Price"] = display["Price"].apply(fmt_price)
display["Chg %"] = display["Chg %"].apply(fmt_chg)
display["Summary"] = display["Summary"].apply(
    lambda s: s[:90] + "…" if isinstance(s, str) and len(s) > 90 else s
)

st.dataframe(
    display[["Symbol", "Company", "Type", "V2", "Price", "Chg %"]],
    use_container_width=True,
    height=600,
    column_config={
        "Symbol":    st.column_config.TextColumn("Symbol", width=70),
        "Company":   st.column_config.TextColumn("Company", width=280),
        "Type":      st.column_config.TextColumn("Type", width=60),
        "V2":        st.column_config.TextColumn("V2 Score", width=80),
        "Price":     st.column_config.TextColumn("Price", width=80),
        "Chg %":     st.column_config.TextColumn("1d Chg", width=80),
    },
    hide_index=True,
)

st.markdown("---")
st.caption("💡 **Next step:** Go to Stock Detail page (sidebar) to view full analysis for a stock you're interested in.")

st.caption("**V2 Mismatch Score** (primary): Identifies quality companies the market is underpricing relative to fundamentals and trajectory. "
           "**Filing Sentiment** (secondary): Haiku sentiment from the most recent 10-K/10-Q. Not financial advice.")
