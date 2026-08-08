"""
Portfolio — migrated from the standalone portfolio-tracker (React/Firebase)
2026-08-08, user-approved route B. Feature-exact replica minus the cashflow
tab: stat cards, Live Portfolio, Portfolio News, Day Movers, Realized
Trades, All Transactions with add/remove. Trades entered HERE from cutover
day; the React app is a frozen reference. Accounting engine:
pipeline/portfolio.py (verified penny-exact against the original JS).
"""
import os
from datetime import datetime

import requests
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv(override=True)
st.set_page_config(page_title="Portfolio | FinResearch", page_icon="💼", layout="wide")

FMP_KEY = os.environ.get("FMP_API_KEY", "")
FMP = "https://financialmodelingprep.com/api/v3"


@st.cache_resource
def get_engine():
    from pipeline.hidden_gem_scorer import get_engine as _ge
    return _ge()


engine = get_engine()


def fmt_ccy(v, ccy="GBP"):
    sym = {"GBP": "£", "USD": "$", "EUR": "€"}.get(ccy, ccy + " ")
    try:
        return f"-{sym}{abs(v):,.2f}" if v < 0 else f"{sym}{v:,.2f}"
    except Exception:
        return f"{sym}0.00"


@st.cache_data(ttl=180)
def live_quotes(tickers: tuple, currencies: tuple, base: str):
    prices, rates = {}, {base: 1.0}
    if tickers:
        try:
            r = requests.get(f"{FMP}/quote/{','.join(tickers)}",
                             params={"apikey": FMP_KEY}, timeout=20)
            for item in r.json() if r.ok else []:
                if item.get("symbol"):
                    prices[item["symbol"]] = {
                        "price": item.get("price") or 0,
                        "changesPercentage": item.get("changesPercentage") or 0}
        except Exception:
            pass
    fx_needed = [c for c in currencies if c and c not in (base, "GBX")]
    if fx_needed:
        try:
            pairs = ",".join(c + base for c in fx_needed)
            r = requests.get(f"{FMP}/fx/{pairs}", params={"apikey": FMP_KEY}, timeout=20)
            for item in r.json() if r.ok else []:
                tk = item.get("ticker") or ""
                rate = item.get("bid") or item.get("ask") or item.get("price")
                if tk and rate:
                    rates[tk[:3]] = float(rate)
        except Exception:
            pass
    # GBX = pence: price/100 is GBP, then GBP->base (base is GBP so rate 1)
    rates.setdefault("GBX", 1.0)
    return prices, rates


@st.cache_data(ttl=300)
def day_movers():
    out = {}
    for kind in ("gainers", "losers"):
        try:
            r = requests.get(f"{FMP}/stock_market/{kind}",
                             params={"apikey": FMP_KEY}, timeout=20)
            out[kind] = (r.json() if r.ok else [])[:30]
        except Exception:
            out[kind] = []
    return out


@st.cache_data(ttl=900)
def portfolio_news(tickers: tuple):
    try:
        r = requests.get(f"{FMP}/stock_news",
                         params={"tickers": ",".join(tickers), "limit": 40,
                                 "apikey": FMP_KEY}, timeout=20)
        return r.json() if r.ok else []
    except Exception:
        return []


@st.cache_data(ttl=60)
def fx_rate(frm: str, to: str) -> float:
    if not frm or not to or frm == to:
        return 1.0
    try:
        r = requests.get(f"{FMP}/fx/{frm}{to}", params={"apikey": FMP_KEY}, timeout=15)
        d = r.json() if r.ok else []
        rate = (d[0].get("bid") or d[0].get("price")) if d else None
        return float(rate) if rate else 1.0
    except Exception:
        return 1.0


from pipeline.portfolio import (add_transaction, delete_transaction,
                                process_portfolio)

state = process_portfolio(engine)
base = state.base_currency
tickers = tuple(sorted({h["ticker"] for h in state.holdings}))
currencies = tuple(sorted({h["currency"] for h in state.holdings if h["currency"]}))
prices, rates = live_quotes(tickers, currencies, base)

# ── derived values (App.js derivedPortfolio, verbatim semantics) ─────────────
total_stock = 0.0
rows = []
for h in state.holdings:
    live = prices.get(h["ticker"], {})
    px = live.get("price", 0) or 0
    rate = rates.get(h["currency"], 1.0)
    px_calc = px / 100 if h["currency"] == "GBX" else px
    value = h["quantity"] * px_calc * rate
    total_stock += value
    rows.append({**h, "value": value, "day_pct": live.get("changesPercentage", 0) or 0,
                 "unrealized": value - h["cost_basis_base"]})
total_value = state.cash + total_stock
day_pct = sum((r["value"] / total_stock) * r["day_pct"] for r in rows) if total_stock else 0.0
unrealized = total_stock - sum(r["cost_basis_base"] for r in rows)

# ── header + stat cards ──────────────────────────────────────────────────────
st.title("Portfolio")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Portfolio Value", fmt_ccy(total_value, base))
c2.metric("Day's Performance", f"{day_pct:+.2f}%")
c3.metric("Unrealized P/L", fmt_ccy(unrealized, base))
c4.metric("Realized P/L", fmt_ccy(state.realized, base))
c5.metric("Cash Position", fmt_ccy(state.cash, base))

tab_live, tab_news, tab_movers, tab_realized, tab_all = st.tabs(
    ["Live Portfolio", "Portfolio News", "Day Movers", "Realized Trades",
     "All Transactions"])

with tab_live:
    display = sorted(rows, key=lambda r: -r["value"])
    table = [{"Ticker": f'{r["ticker"]}  ({r["currency"]})',
              "Day's Change": f'{r["day_pct"]:+.2f}%',
              "Quantity": f'{r["quantity"]:,.4f}',
              f"Market Value ({base})": fmt_ccy(r["value"], base),
              "% of Portfolio": f'{(r["value"]/total_value*100 if total_value else 0):.2f}%',
              "Unrealized P/L": fmt_ccy(r["unrealized"], base)} for r in display]
    table.insert(0, {"Ticker": "Cash", "Day's Change": "—", "Quantity": "—",
                     f"Market Value ({base})": fmt_ccy(state.cash, base),
                     "% of Portfolio": f'{(state.cash/total_value*100 if total_value else 0):.2f}%',
                     "Unrealized P/L": "—"})
    st.dataframe(table, use_container_width=True, hide_index=True)

with tab_news:
    news = portfolio_news(tickers)
    if not news:
        st.caption("No recent news found for your holdings.")
    by_tk = {}
    for a in news:
        by_tk.setdefault(a.get("symbol", "?"), []).append(a)
    for tk in sorted(by_tk):
        st.subheader(tk)
        for a in by_tk[tk][:4]:
            st.markdown(f"**[{a.get('title','(untitled)')}]({a.get('url','#')})**  \n"
                        f"{(a.get('text') or '')[:220]}…  \n"
                        f"*{a.get('site','')} · {(a.get('publishedDate') or '')[:10]}*")

with tab_movers:
    mv = day_movers()
    mc1, mc2 = st.columns(2)
    for col, kind, label in ((mc1, "gainers", "Top 30 Gainers"),
                             (mc2, "losers", "Top 30 Losers")):
        with col:
            st.subheader(label)
            st.dataframe([{"Ticker": m.get("symbol"), "Name": m.get("name"),
                           "Price": f"${m.get('price', 0):,.2f}",
                           "% Change": f"{m.get('changesPercentage', 0):+.2f}%"}
                          for m in mv[kind]],
                         use_container_width=True, hide_index=True, height=560)

with tab_realized:
    logs = sorted(state.realized_log, key=lambda l: l["sale_date"], reverse=True)
    st.dataframe([{"Ticker": l["ticker"],
                   "Sale Date": l["sale_date"].strftime("%d %b %Y"),
                   "Quantity": f'{l["quantity"]:,.4f}',
                   "Sale Value": fmt_ccy(l["sale_value"], base),
                   "Cost Basis": fmt_ccy(l["cost_basis"], base),
                   "Realized P/L": fmt_ccy(l["pnl"], base)} for l in logs],
                 use_container_width=True, hide_index=True, height=600)

with tab_all:
    with st.expander("➕ Add transaction"):
        ttype = st.selectbox("Type", ["BUY", "SELL", "DEPOSIT", "WITHDRAW"])
        with st.form("add_tx", clear_on_submit=True):
            if ttype in ("BUY", "SELL"):
                fc1, fc2 = st.columns(2)
                tk = fc1.text_input("Stock ticker", placeholder="e.g. AAPL").strip().upper()
                qty = fc2.number_input("Quantity", min_value=0.0, step=1.0, format="%.4f")
                fc3, fc4 = st.columns(2)
                px = fc3.number_input("Price per share", min_value=0.0, format="%.4f")
                ccy = fc4.selectbox("Currency", ["USD", "EUR", "GBP", "GBX"])
                auto_rate = fx_rate("GBP" if ccy == "GBX" else ccy, base)
                rate_in = st.number_input(f"Exchange rate ({ccy} → {base})",
                                          value=float(auto_rate), format="%.6f")
                submitted = st.form_submit_button("Add")
                if submitted and tk and qty > 0 and px > 0:
                    px_base_units = px / 100 if ccy == "GBX" else px
                    value = qty * px_base_units * rate_in
                    add_transaction(engine, type=ttype, ticker=tk, quantity=qty,
                                    price=px, currency=ccy, value_gbp=value)
                    st.success(f"{ttype} {qty:g} {tk} recorded ({fmt_ccy(value, base)}).")
                    st.cache_data.clear()
                    st.rerun()
            else:
                amt = st.number_input(f"Amount ({base})", min_value=0.0, format="%.2f")
                submitted = st.form_submit_button("Add")
                if submitted and amt > 0:
                    add_transaction(engine, type=ttype, ticker=None, quantity=None,
                                    price=None, currency=base, value_gbp=amt)
                    st.success(f"{ttype} of {fmt_ccy(amt, base)} recorded.")
                    st.cache_data.clear()
                    st.rerun()

    txs = sorted(state.transactions, key=lambda t: t["date"], reverse=True)
    st.dataframe([{"Date": t["date"].strftime("%d %b %Y"),
                   "Type": t["type"], "Ticker": t["ticker"] or "CASH",
                   "Quantity": f'{t["quantity"]:,.4f}' if t["quantity"] else "—",
                   f"Value ({base})": fmt_ccy(t["value_gbp"] or 0, base),
                   "Source": t["source"], "ID": t["id"]} for t in txs],
                 use_container_width=True, hide_index=True, height=520)

    with st.expander("🗑 Remove a transaction"):
        recent = txs[:80]
        label = {f'{t["date"]:%d %b %Y} · {t["type"]} · {t["ticker"] or "CASH"} · '
                 f'{fmt_ccy(t["value_gbp"] or 0, base)} · {t["id"][:8]}': t["id"]
                 for t in recent}
        pick = st.selectbox("Select (most recent 80 shown)", list(label))
        if st.button("Remove selected", type="secondary"):
            if delete_transaction(engine, label[pick]):
                st.success("Removed (kept in the audit archive).")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("Not found.")
