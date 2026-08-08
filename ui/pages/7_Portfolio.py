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
    """US-domiciled, non-ADR names only (user 2026-08-08): candidates are
    profile-checked in one batch call per list."""
    out = {}
    for kind in ("gainers", "losers"):
        try:
            r = requests.get(f"{FMP}/stock_market/{kind}",
                             params={"apikey": FMP_KEY}, timeout=20)
            cand = [m for m in (r.json() if r.ok else [])
                    if m.get("symbol") and "." not in m["symbol"]][:60]
            syms = ",".join(m["symbol"] for m in cand)
            ok = set()
            if syms:
                pr = requests.get(f"{FMP}/profile/{syms}",
                                  params={"apikey": FMP_KEY}, timeout=20)
                for p in pr.json() if pr.ok else []:
                    if (p.get("country") == "US" and not p.get("isAdr")
                            and p.get("exchangeShortName") in ("NYSE", "NASDAQ", "AMEX")):
                        ok.add(p.get("symbol"))
            out[kind] = [m for m in cand if m["symbol"] in ok][:30]
        except Exception:
            out[kind] = []
    return out


@st.cache_data(ttl=3600 * 6)
def benchmark_history():
    """SPY + GBPUSD daily closes since the first trade (Aug 2022)."""
    out = {}
    for sym in ("SPY", "GBPUSD"):
        try:
            r = requests.get(f"{FMP}/historical-price-full/{sym}",
                             params={"serietype": "line", "from": "2022-08-01",
                                     "apikey": FMP_KEY}, timeout=30)
            hist = (r.json() or {}).get("historical", []) if r.ok else []
            out[sym] = {h["date"]: float(h["close"]) for h in hist if h.get("close")}
        except Exception:
            out[sym] = {}
    return out


@st.cache_data(ttl=180)
def spy_day_change():
    try:
        r = requests.get(f"{FMP}/quote/SPY", params={"apikey": FMP_KEY}, timeout=15)
        d = r.json() if r.ok else []
        return float(d[0].get("changesPercentage") or 0) if d else None
    except Exception:
        return None


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

# ── add-transaction modal (mirrors the React app's header Add button) ────────
@st.dialog("Add Transaction")
def add_dialog():
    ttype = st.selectbox("Transaction type",
                         ["BUY", "SELL", "DEPOSIT", "WITHDRAW"],
                         format_func=lambda t: {"BUY": "Buy stock",
                                                "SELL": "Sell stock",
                                                "DEPOSIT": "Deposit cash",
                                                "WITHDRAW": "Withdraw cash"}[t])
    if ttype in ("BUY", "SELL"):
        fc1, fc2 = st.columns(2)
        tk = fc1.text_input("Stock ticker", placeholder="e.g. AAPL").strip().upper()
        qty = fc2.number_input("Quantity", min_value=0.0, step=1.0, format="%.4f")
        fc3, fc4 = st.columns(2)
        px = fc3.number_input("Price per share", min_value=0.0, format="%.4f")
        ccy = fc4.selectbox("Currency", ["USD", "EUR", "GBP", "GBX"])
        auto = fx_rate("GBP" if ccy == "GBX" else ccy, base)
        rate = st.number_input(f"Exchange rate ({ccy} → {base})",
                               value=float(auto), format="%.6f",
                               help="Fetched live; override if needed")
        if st.button("Add", type="primary", use_container_width=True):
            if tk and qty > 0 and px > 0:
                px_units = px / 100 if ccy == "GBX" else px
                value = qty * px_units * rate
                add_transaction(engine, type=ttype, ticker=tk, quantity=qty,
                                price=px, currency=ccy, value_gbp=value)
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("Ticker, quantity, and price are all required.")
    else:
        amt = st.number_input(f"Amount ({base})", min_value=0.0, format="%.2f")
        if st.button("Add", type="primary", use_container_width=True):
            if amt > 0:
                add_transaction(engine, type=ttype, ticker=None, quantity=None,
                                price=None, currency=base, value_gbp=amt)
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("Enter an amount.")


# ── header + stat cards ──────────────────────────────────────────────────────
h1, h2 = st.columns([5, 1])
h1.title("Portfolio")
with h2:
    st.write("")
    if st.button("➕  Add", type="primary", use_container_width=True):
        add_dialog()
spy_day = spy_day_change()
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Portfolio Value", fmt_ccy(total_value, base))
c2.metric("Day's Performance", f"{day_pct:+.2f}%",
          delta=(f"{day_pct - spy_day:+.2f}% vs S&P 500 ({spy_day:+.2f}%)"
                 if spy_day is not None else None))
c3.metric("Unrealized P/L", fmt_ccy(unrealized, base))
c4.metric("Realized P/L", fmt_ccy(state.realized, base))
c5.metric("Cash Position", fmt_ccy(state.cash, base))

# ── SPY twin since day one (same discipline as the platform's track record) ──
bh = benchmark_history()
spy_now_px = prices.get("SPY", {}).get("price") or (
    sorted(bh["SPY"].items())[-1][1] if bh["SPY"] else None)
fx_now = (sorted(bh["GBPUSD"].items())[-1][1] if bh["GBPUSD"] else None)
from pipeline.portfolio import spy_comparison
cmp_ = spy_comparison(state.transactions, bh["SPY"], bh["GBPUSD"],
                      spy_now_px, fx_now) if bh["SPY"] and bh["GBPUSD"] else None
if cmp_:
    shadow = cmp_["shadow_value_gbp"]
    rel = (total_stock / shadow - 1) * 100 if shadow else 0
    tone = "#16a34a" if rel >= 0 else "#dc2626"
    st.markdown(
        f"<div style='background:rgba(128,128,128,.07);border:1px solid "
        f"rgba(128,128,128,.25);border-radius:10px;padding:12px 16px;margin:6px 0 2px'>"
        f"<b>vs the S&amp;P 500 since day one</b> &nbsp;·&nbsp; "
        f"Your invested holdings (cash excluded): <b>{fmt_ccy(total_stock, base)}</b> &nbsp;·&nbsp; "
        f"Same pounds, same days, in SPY: <b>{fmt_ccy(shadow, base)}</b> &nbsp;·&nbsp; "
        f"<b style='color:{tone}'>{rel:+.1f}% vs the index</b>"
        f"<span style='opacity:.55;font-size:12px'> &nbsp;— deposits never count as gains: "
        f"money enters this race only when invested, and the identical amount buys SPY "
        f"in the twin the same day (sells leave both sides the same day too). "
        f"{cmp_['matched']} trades mirrored at daily prices and GBP/USD rates"
        + (f"; {cmp_['skipped']} skipped for missing history" if cmp_["skipped"] else "")
        + ".</span></div>", unsafe_allow_html=True)

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
    st.caption("Add trades and cash movements with the **➕ Add** button at "
               "the top of the page.")
    txs = sorted(state.transactions, key=lambda t: t["date"], reverse=True)
    st.caption("Click a row to select it — a delete option appears below.")
    tx_rows = [{"Date": t["date"].strftime("%d %b %Y"),
                "Type": t["type"], "Ticker": t["ticker"] or "CASH",
                "Quantity": f'{t["quantity"]:,.4f}' if t["quantity"] else "—",
                f"Value ({base})": fmt_ccy(t["value_gbp"] or 0, base),
                "Source": t["source"]} for t in txs]
    sel = st.dataframe(tx_rows, use_container_width=True, hide_index=True,
                       height=520, on_select="rerun", selection_mode="single-row")
    picked = (sel.selection.rows or [None])[0] if sel and sel.selection else None
    if picked is not None:
        t = txs[picked]
        dc1, dc2 = st.columns([4, 1])
        dc1.info(f'Selected: {t["date"]:%d %b %Y} · {t["type"]} · '
                 f'{t["ticker"] or "CASH"} · {fmt_ccy(t["value_gbp"] or 0, base)}')
        if dc2.button("🗑 Delete", type="primary", use_container_width=True):
            if delete_transaction(engine, t["id"]):
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("Not found.")
