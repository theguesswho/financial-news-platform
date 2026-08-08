"""
Portfolio engine — exact Python port of portfolio-tracker's
processedPortfolio logic (App.js, FIFO lot accounting). Migrated from
Firebase 2026-08-08 (user-approved route B); the React app remains
untouched as the reference implementation.

Semantics preserved verbatim:
  - Transactions sorted by date ascending; FIFO lots per ticker.
  - DEPOSIT/WITHDRAW move cash; BUY/SELL move cash ONLY for app-entered
    transactions (CSV-imported ones predate cash tracking — the app skips
    them via the 'csv-' id prefix; we use the source column).
  - SELL consumes lots FIFO; realized P/L = sale value minus consumed cost
    basis, each consumption logged.
  - Holdings = remaining lots aggregated per ticker (quantity, cost basis
    in base currency, currency from first remaining lot).
  - GBX prices are pence: divide live price by 100 before valuing.
"""
from dataclasses import dataclass, field

from sqlalchemy import text


@dataclass
class PortfolioState:
    holdings: list = field(default_factory=list)
    realized: float = 0.0
    cash: float = 0.0
    realized_log: list = field(default_factory=list)
    base_currency: str = "GBP"
    transactions: list = field(default_factory=list)


def load_transactions(engine) -> list:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, date, type, ticker, quantity, price, currency,
                   value_gbp, source
            FROM portfolio_transactions ORDER BY date, id
        """)).fetchall()
    return [dict(id=r[0], date=r[1], type=r[2], ticker=r[3],
                 quantity=float(r[4]) if r[4] is not None else None,
                 price=float(r[5]) if r[5] is not None else None,
                 currency=r[6],
                 value_gbp=float(r[7]) if r[7] is not None else None,
                 source=r[8]) for r in rows]


def process_portfolio(engine) -> PortfolioState:
    txs = load_transactions(engine)
    with engine.connect() as conn:
        base = conn.execute(text(
            "SELECT v FROM portfolio_settings WHERE k='base_currency'")).scalar() or "GBP"

    buy_lots: dict[str, list] = {}
    realized = 0.0
    cash = 0.0
    log = []
    for t in txs:
        if t["type"] == "DEPOSIT":
            cash += t["value_gbp"] or 0.0
            continue
        if t["type"] == "WITHDRAW":
            cash -= t["value_gbp"] or 0.0
            continue
        if t["type"] == "BUY":
            lots = buy_lots.setdefault(t["ticker"], [])
            q = t["quantity"] or 0.0
            cps = (t["value_gbp"] / q) if q > 0 else 0.0
            lots.append({**t, "cost_per_share_base": cps})
            if t["source"] != "csv":
                cash -= t["value_gbp"] or 0.0
            continue
        if t["type"] == "SELL":
            shares = t["quantity"] or 0.0
            sale_per_share = (t["value_gbp"] / shares) if shares > 0 else 0.0
            if t["source"] != "csv":
                cash += t["value_gbp"] or 0.0
            lots = buy_lots.get(t["ticker"])
            if not lots:
                continue
            while shares > 0 and lots:
                lot = lots[0]
                sold = min(shares, lot["quantity"])
                cost = lot["cost_per_share_base"] * sold
                revenue = sale_per_share * sold
                pnl = revenue - cost
                realized += pnl
                log.append({"sale_date": t["date"], "buy_date": lot["date"],
                            "ticker": t["ticker"], "quantity": sold,
                            "sale_value": revenue, "cost_basis": cost,
                            "pnl": pnl,
                            "key": f'{t["id"]}-{lot["id"]}-{sold}'})
                lot["quantity"] -= sold
                shares -= sold
                if lot["quantity"] < 1e-9:
                    lots.pop(0)

    holdings = []
    for ticker, lots in buy_lots.items():
        if not lots:
            continue
        qty = sum(l["quantity"] for l in lots)
        cost = sum(l["quantity"] * l["cost_per_share_base"] for l in lots)
        if qty > 1e-9:
            holdings.append({"ticker": ticker, "quantity": qty,
                             "currency": lots[0]["currency"],
                             "cost_basis_base": cost})
    return PortfolioState(holdings=holdings, realized=realized, cash=cash,
                          realized_log=log, base_currency=base,
                          transactions=txs)


def add_transaction(engine, *, type: str, ticker: str | None, quantity,
                    price, currency: str, value_gbp: float) -> str:
    """Platform-entered transaction (source='platform'). Mirrors the app's
    TransactionModal semantics: value_gbp = quantity*price*fx for trades,
    or the raw amount for cash movements."""
    import uuid
    from datetime import datetime, timezone
    tid = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO portfolio_transactions
                (id, date, type, ticker, quantity, price, currency, value_gbp, source)
            VALUES (:id, :d, :t, :tk, :q, :p, :c, :v, 'platform')"""),
            {"id": tid, "d": datetime.now(timezone.utc), "t": type,
             "tk": (ticker or None), "q": quantity, "p": price,
             "c": currency, "v": value_gbp})
    return tid


def delete_transaction(engine, tid: str) -> bool:
    """Soft delete: the row moves to portfolio_transactions_deleted (the
    app hard-deletes from the array; we keep an audit trail instead)."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS portfolio_transactions_deleted
            (LIKE portfolio_transactions INCLUDING ALL)"""))
        moved = conn.execute(text("""
            WITH d AS (DELETE FROM portfolio_transactions WHERE id = :i RETURNING *)
            INSERT INTO portfolio_transactions_deleted SELECT * FROM d
            ON CONFLICT (id) DO NOTHING
            RETURNING id"""), {"i": tid}).fetchone()
    return moved is not None


def spy_comparison(transactions: list, spy_hist: dict, fx_hist: dict,
                   spy_now: float, fx_now: float) -> dict | None:
    """SPY twin for the REAL portfolio (user 2026-08-08): every BUY mirrors
    into SPY units bought with the same pounds on the same day (via that
    day's GBPUSD); every SELL removes the same notional. Cash movements
    are excluded — cash earns nothing in both worlds. Returns the shadow
    value and the relative result. spy_hist/fx_hist: {date_iso: close}.
    """
    def _lookup(hist, d):
        # walk back up to 7 days for weekends/holidays
        from datetime import timedelta
        for i in range(8):
            k = (d - timedelta(days=i)).strftime("%Y-%m-%d")
            if k in hist:
                return hist[k]
        return None

    units = 0.0
    invested_gbp = 0.0
    matched = skipped = 0
    for t in transactions:
        if t["type"] not in ("BUY", "SELL") or not t.get("value_gbp"):
            continue
        d = t["date"].date() if hasattr(t["date"], "date") else t["date"]
        spy = _lookup(spy_hist, d)
        fx = _lookup(fx_hist, d)   # GBPUSD: dollars per pound
        if not spy or not fx:
            skipped += 1
            continue
        usd = t["value_gbp"] * fx
        if t["type"] == "BUY":
            units += usd / spy
            invested_gbp += t["value_gbp"]
            matched += 1
        else:
            units -= usd / spy
            invested_gbp -= t["value_gbp"]
            matched += 1
    if units <= 0 or not spy_now or not fx_now:
        return None
    shadow_gbp = units * spy_now / fx_now
    return {"shadow_value_gbp": shadow_gbp, "net_invested_gbp": invested_gbp,
            "matched": matched, "skipped": skipped}
