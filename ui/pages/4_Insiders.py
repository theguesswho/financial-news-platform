"""
Insider Trading feed — Form 4 open-market buys and sells by executives.
"""
import os
import sys
from pathlib import Path
from datetime import date, timedelta

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root))
load_dotenv(root / ".env", override=True)

from db.session import get_session
from db.models import InsiderTrade
from sqlalchemy import desc, func

st.set_page_config(page_title="Insider Trading", page_icon="👁", layout="wide")

st.markdown("""
<style>
.block-container { max-width: 1100px; padding: 3.5rem 2rem 4rem; }
header[data-testid="stHeader"] { display: none; }
.cluster-box { background: #fff8e1; border: 1px solid #ffc107; border-radius: 8px; padding: 0.75rem 1rem; margin-bottom: 1rem; }
.cluster-title { font-weight: 700; margin-bottom: 0.25rem; }
</style>
""", unsafe_allow_html=True)


def get_db():
    return get_session()

session = get_db()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 👁 Insider Trades")
    st.markdown("---")

    tx_type = st.radio("Transaction type", ["All", "Buys only", "Sells only"])
    min_value = st.selectbox(
        "Minimum trade value",
        [0, 50_000, 100_000, 500_000, 1_000_000],
        index=2,
        format_func=lambda x: "Any size" if x == 0 else f"USD {x:,.0f}+",
    )
    days_back = st.slider("Lookback (days)", 7, 90, 30)
    symbol_search = st.text_input("Filter by symbol", "").strip().upper()
    st.markdown("---")
    st.caption("Source: SEC Form 4 filings.\nAwards and option exercises excluded.\nNot financial advice.")

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
cutoff = date.today() - timedelta(days=days_back)

q = (
    session.query(InsiderTrade)
    .filter(InsiderTrade.transaction_date >= cutoff)
    .order_by(desc(InsiderTrade.transaction_date), desc(InsiderTrade.total_value))
)

if tx_type == "Buys only":
    q = q.filter(InsiderTrade.transaction_type == "BUY")
elif tx_type == "Sells only":
    q = q.filter(InsiderTrade.transaction_type == "SELL")

if min_value > 0:
    q = q.filter(InsiderTrade.total_value >= min_value)

if symbol_search:
    q = q.filter(InsiderTrade.symbol == symbol_search)

trades = q.limit(500).all()

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("👁 Insider Trading")

if not trades:
    st.info("No insider trades yet. Run `python run.py insiders` to fetch Form 4 filings.")
    st.stop()

total_buys = sum(1 for t in trades if t.transaction_type == "BUY")
total_sells = sum(1 for t in trades if t.transaction_type == "SELL")
buy_value = sum(float(t.total_value) for t in trades if t.transaction_type == "BUY" and t.total_value)
sell_value = sum(float(t.total_value) for t in trades if t.transaction_type == "SELL" and t.total_value)

c1, c2, c3, c4 = st.columns(4)
c1.metric("🟢 Open-market buys", total_buys)
c2.metric("Buy value", f"USD {buy_value/1e6:.1f}M" if buy_value >= 1e6 else f"USD {buy_value:,.0f}")
c3.metric("🔴 Open-market sells", total_sells)
c4.metric("Sell value", f"USD {sell_value/1e6:.1f}M" if sell_value >= 1e6 else f"USD {sell_value:,.0f}")

st.markdown("---")

# ---------------------------------------------------------------------------
# Cluster buying alert — multiple insiders buying same stock
# ---------------------------------------------------------------------------
buy_trades = [t for t in trades if t.transaction_type == "BUY"]
cluster: dict[str, list] = {}
for t in buy_trades:
    cluster.setdefault(t.symbol, []).append(t)

clusters = {sym: ts for sym, ts in cluster.items() if len(ts) >= 2}
if clusters:
    st.markdown("### 🔔 Cluster Buying — Multiple Insiders")
    st.caption("When 2+ insiders buy the same stock, it's a historically strong signal.")
    for sym, ts in sorted(clusters.items(), key=lambda x: -len(x[1])):
        total = sum(float(t.total_value) for t in ts if t.total_value)
        names = ", ".join(set(t.person_name for t in ts if t.person_name))
        st.markdown(f"""
<div class="cluster-box">
  <div class="cluster-title">🟢 {sym} — {len(ts)} insiders buying</div>
  <div>{names}</div>
  <div style="color:#666;font-size:0.85rem;">Combined value: USD {total:,.0f}</div>
</div>
""", unsafe_allow_html=True)
    st.markdown("---")

# ---------------------------------------------------------------------------
# Trades table
# ---------------------------------------------------------------------------
st.markdown("### All Transactions")

rows = []
for t in trades:
    rows.append({
        "Symbol": t.symbol,
        "Person": t.person_name or "—",
        "Title": t.person_title or "—",
        "Type": "🟢 BUY" if t.transaction_type == "BUY" else "🔴 SELL",
        "Date": str(t.transaction_date),
        "Shares": f"{float(t.shares):,.0f}" if t.shares else "—",
        "Price": f"USD {float(t.price_per_share):.2f}" if t.price_per_share else "—",
        "Value": f"USD {float(t.total_value):,.0f}" if t.total_value else "—",
        "Owned after": f"{float(t.shares_owned_after):,.0f}" if t.shares_owned_after else "—",
    })

df = pd.DataFrame(rows)

st.dataframe(
    df,
    use_container_width=True,
    height=500,
    column_config={
        "Symbol":      st.column_config.TextColumn(width=70),
        "Person":      st.column_config.TextColumn(width=160),
        "Title":       st.column_config.TextColumn(width=150),
        "Type":        st.column_config.TextColumn(width=80),
        "Date":        st.column_config.TextColumn(width=90),
        "Shares":      st.column_config.TextColumn(width=90),
        "Price":       st.column_config.TextColumn(width=90),
        "Value":       st.column_config.TextColumn("Total Value", width=110),
        "Owned after": st.column_config.TextColumn(width=110),
    },
    hide_index=True,
)
