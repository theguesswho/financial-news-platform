"""
EarningsCall.biz fast-path transcript source (user-approved 2026-08-01).

Transcripts arrive ~15 minutes after a call ends — versus 1-3+ days for
FMP's finalized versions. This module is the PRIMARY transcript source;
FMP's earnings_ingestion remains the FALLBACK and covers the ~7 symbols
EarningsCall lacks (share-class ticker quirks: BRK, GOOGL, FOXA...).

DEDUPE BY CONSTRUCTION: rows are stored in `filings` with the SAME url key
convention FMP uses — EARN_CALL:{symbol}:Q{q}:{year} — so whichever source
lands first owns the row and the other skips on the unique constraint.
Nothing is ever deleted or overwritten; the transition is purely additive.

Rate limit: Starter tier = 10 calls/min → hard 6.5s throttle between calls.
API key: EARNINGSCALL_API_KEY env var (never committed).
"""
import json
import os
import time
import urllib.request

from sqlalchemy import text

BASE = "https://v2.api.earningscall.biz"
THROTTLE_S = 6.5   # Starter tier: 10 calls/min
EXCHANGES_IN_ORDER = ["NYSE", "NASDAQ", "AMEX", "TSX", "TSXV", "OTC", "LSE", "CBOE", "STO"]

_symbol_exchange_cache: dict[str, str] = {}


def _api_key() -> str | None:
    return os.environ.get("EARNINGSCALL_API_KEY")


def _get(path: str, params: dict) -> tuple[int, bytes]:
    qs = "&".join(f"{k}={v}" for k, v in {**params, "apikey": _api_key()}.items())
    req = urllib.request.Request(f"{BASE}/{path}?{qs}",
                                 headers={"User-Agent": "hidden-gems-platform"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                time.sleep(35)   # rate-limited: wait out the window, retry
                continue
            return e.code, b""
        except Exception:
            if attempt < 2:
                time.sleep(5)
                continue
            return 0, b""
    return 0, b""


def _load_symbol_exchanges():
    """Map our tickers to their exchange via symbols-v2.txt (1 API call, cached)."""
    if _symbol_exchange_cache:
        return _symbol_exchange_cache
    status, body = _get("symbols-v2.txt", {})
    if status != 200:
        print(f"  earningscall symbols fetch failed ({status})")
        return {}
    for line in body.decode("utf-8", "replace").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            try:
                ex = EXCHANGES_IN_ORDER[int(parts[0])]
            except (ValueError, IndexError):
                continue
            _symbol_exchange_cache.setdefault(parts[1].strip().upper(), ex)
    return _symbol_exchange_cache


def fetch_fast_transcripts(engine, lookback_days: int = 7) -> dict:
    """
    For universe symbols with a recent earnings 8-K but NO stored transcript
    for that quarter yet: try EarningsCall. Self-limiting — the 8-K signal
    plus the url-key existence check means we only ever call for stocks that
    actually reported and are actually missing their transcript.
    """
    if not _api_key():
        print("  EARNINGSCALL_API_KEY not set — fast-path skipped (FMP fallback only)")
        return {"fetched": 0, "skipped_no_key": True}

    with engine.connect() as conn:
        # Stocks with a recent earnings event whose current-quarter transcript
        # is missing. Quarter guessed from the 8-K date (calendar quarter).
        candidates = conn.execute(text("""
            SELECT DISTINCT f.symbol, f.filing_date::date
            FROM filings f
            WHERE f.filing_type = '8-K' AND f.event_type = 'EARNINGS'
              AND f.filing_date > NOW() - (:d || ' days')::interval
              AND NOT EXISTS (
                  SELECT 1 FROM filings t
                  WHERE t.filing_type = 'EARN_CALL' AND t.symbol = f.symbol
                    AND t.filing_date > f.filing_date - INTERVAL '10 days'
              )
            ORDER BY f.symbol
        """), {"d": lookback_days}).fetchall()

    if not candidates:
        print("  earningscall fast-path: no missing transcripts")
        return {"fetched": 0, "checked": 0}

    exch = _load_symbol_exchanges()
    time.sleep(THROTTLE_S)
    stats = {"fetched": 0, "checked": 0, "not_yet": 0, "no_coverage": 0, "errors": 0}

    # FYE month per symbol — the vendor (like FMP) labels transcripts by
    # FISCAL quarter, so the request must be fiscal too. The old calendar
    # guess + blind q-1 fallback fetched ACM's PRIOR call under a colliding
    # key (2026-08-11, CLAUDE.md Evidence integrity rule 3). 172 symbols
    # have offset fiscal years.
    with engine.connect() as conn:
        fye = dict(conn.execute(text("""
            SELECT symbol, EXTRACT(MONTH FROM MAX(fiscal_year::date))::int
            FROM fundamentals_annual GROUP BY symbol""")).fetchall())

    def _fiscal_label(sym, event_date):
        """(year, quarter) of the reported fiscal quarter, FMP convention
        (fiscal year labeled by the calendar year its FYE falls in).
        The reported quarter = most recent fiscal quarter-end at least
        20 days before the call (Q4/annual calls lag year-end 60-90d,
        so a fixed-offset anchor mislabels them)."""
        import calendar as _cal
        import datetime as _dt
        m = fye.get(sym) or 12
        end_months = {(m - 3 * k - 1) % 12 + 1 for k in range(4)}
        for back in range(15):
            idx = event_date.year * 12 + (event_date.month - 1) - back
            yy, mm = idx // 12, idx % 12 + 1
            if mm not in end_months:
                continue
            qend = _dt.date(yy, mm, _cal.monthrange(yy, mm)[1])
            if (event_date - qend).days >= 20:
                quarter = ((mm - m + 12) % 12) // 3 or 4
                year = yy if mm <= m else yy + 1
                return year, quarter
        return event_date.year, (event_date.month - 1) // 3 + 1

    for sym, event_date in candidates:
        stats["checked"] += 1
        ex = exch.get(sym)
        if not ex:
            stats["no_coverage"] += 1
            continue
        year, quarter = _fiscal_label(sym, event_date)
        status, body = _get("transcript", {
            "exchange": ex, "symbol": sym, "year": year, "quarter": quarter, "level": 1})
        time.sleep(THROTTLE_S)
        # NO adjacent-quarter fallback: a 404 means not yet published.
        # Guessing neighbors is how a prior call gets fetched under a
        # wrong label; the FMP fallback path covers stragglers instead.
        if status != 200 or not body:
            stats["not_yet" if status == 404 else "errors"] += 1
            continue
        try:
            payload = json.loads(body)
            content = (payload.get("text") or "").strip()
        except Exception:
            stats["errors"] += 1
            continue
        if len(content) < 2000:      # a real call transcript is never this short
            stats["not_yet"] += 1
            continue

        url_key = f"EARN_CALL:{sym}:Q{quarter}:{year}"
        with engine.begin() as conn:
            r = conn.execute(text("""
                INSERT INTO filings (symbol, filing_type, title, url, filing_date,
                                     content, created_at)
                VALUES (:s, 'EARN_CALL', :t, :u, :fd, :c, NOW())
                ON CONFLICT (url) DO NOTHING
            """), {"s": sym, "t": f"{sym} Q{quarter} {year} Earnings Call "
                                   f"(earningscall.biz fast transcript)",
                   "u": url_key, "fd": event_date,
                   "c": content[:150000]})
            if r.rowcount:
                stats["fetched"] += 1
                print(f"  ⚡ fast transcript: {sym} Q{quarter} {year} "
                      f"({len(content):,} chars, ~15-min-latency source)")

    print(f"  earningscall fast-path: {stats}")
    return stats


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    from pipeline.hidden_gem_scorer import get_engine
    fetch_fast_transcripts(get_engine(), lookback_days=int(
        sys.argv[1]) if len(sys.argv) > 1 else 7)


def fetch_calendar(engine, days: int = 7, dates: list | None = None) -> list[dict]:
    """Earnings dates for OUR universe — either the next `days` days or an
    explicit `dates` list (the report's Mon-Fri week). One /calendar call
    per day, well under the 10/min limit. Fail-open: [] on any trouble —
    the report's week section falls back to prediction deadlines only."""
    import json as _json
    from datetime import date, timedelta

    from sqlalchemy import text as _text
    if not _api_key():
        return []
    with engine.connect() as conn:
        universe = {r[0] for r in conn.execute(
            _text("SELECT symbol FROM fundamentals")).fetchall()}
    out = []
    span = dates or [date.today() + timedelta(days=i) for i in range(days)]
    for d in span:
        status, body = _get("calendar", {"year": d.year, "month": d.month, "day": d.day})
        if status != 200:
            continue
        try:
            events = _json.loads(body)
        except Exception:
            continue
        for e in events or []:
            sym = (e.get("symbol") or "").upper()
            if sym in universe:
                out.append({"symbol": sym, "date": str(d),
                            "quarter": f"Q{e.get('quarter')}" if e.get("quarter") else ""})
        time.sleep(1.0)
    return out
