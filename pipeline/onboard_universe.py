"""
Universe onboarding gate — brings a chunk of new tickers fully up to data
parity BEFORE they enter scoring. No stock is scored half-fed.

Usage:
    python -m pipeline.onboard_universe config/midcap_chunk1.txt          # backfill + report
    python -m pipeline.onboard_universe config/midcap_chunk1.txt --apply  # also append READY
                                                                          # tickers to tickers.txt

Order matters (each phase feeds the next):
  1. validate     — EDGAR CIK + Yahoo price exist (catches renamed/delisted)
  2. fundamentals — ratios, sector, company name
  3. prices       — ~7 months of EOD closes (gap score silently defaults to
                    0.425 without ≥6 months of history — the week-one bug)
  4. filings      — 10-K/10-Q from EDGAR, 8-Ks
  5. themes       — narrative extraction over new filings
  6. transcripts  — earnings calls (requires themes to exist first)
  7. embeddings   — filing-theme vectors
  8. exposures    — LLM-judged narrative exposure
  9. readiness    — per-ticker report; only all-green tickers go live
"""
import sys
import time
from datetime import date, timedelta
from pathlib import Path

root = Path(__file__).parent.parent
sys.path.insert(0, str(root))
from dotenv import load_dotenv
load_dotenv(root / ".env", override=True)

from sqlalchemy import text


def _load_chunk(path: str) -> list[str]:
    p = Path(path)
    if not p.exists():
        p = root / path   # queue stores repo-relative paths; cwd may differ on Railway
    return [l.strip().upper() for l in open(p) if l.strip()]


def _fmp_profile(symbol: str) -> dict | None:
    """Read-only FMP /profile for the isEtf/isFund gate. Fail-open."""
    import json
    import os
    import urllib.request
    key = os.environ.get("FMP_API_KEY", "")
    if not key:
        return None
    url = (f"https://financialmodelingprep.com/api/v3/profile/{symbol}"
           f"?apikey={key}")
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.loads(r.read())
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data[0]
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def phase_validate(symbols: list[str]) -> tuple[list[str], list[str]]:
    """Ticker must be an operating company, resolve on EDGAR (CIK),
    and have a recent Yahoo price.

    Edmund 2026-09-20: ETFs / grantor trusts are not in the universe.
    Known-list hits reject before any vendor call. Then Yahoo
    quoteType and (when the key is present) FMP isEtf/isFund.
    """
    from pipeline.universe import onboard_reject_reason

    valid, rejected = [], []
    candidates = []
    for s in symbols:
        s = (s or "").strip().upper()
        reason = onboard_reject_reason(s)
        if reason:
            rejected.append(f"{s}: {reason}")
            continue
        candidates.append(s)

    if not candidates:
        return valid, rejected

    import yfinance as yf
    from pipeline.ingestion import _build_cik_map
    cik_map = _build_cik_map(candidates)
    for s in candidates:
        if s not in cik_map:
            rejected.append(f"{s}: no EDGAR CIK")
            continue
        try:
            t = yf.Ticker(s)
            px = None
            quote_type = None
            try:
                px = t.fast_info.get("lastPrice")
            except Exception:
                px = None
            try:
                info = t.info or {}
            except Exception:
                info = {}
            quote_type = info.get("quoteType")
            if not px:
                px = info.get("regularMarketPrice") or info.get("currentPrice")
            if not px:
                rejected.append(f"{s}: no Yahoo price")
                continue
            reason = onboard_reject_reason(s, quote_type=quote_type)
            if reason:
                rejected.append(f"{s}: {reason}")
                continue
        except Exception as exc:
            rejected.append(f"{s}: yahoo error {exc}")
            continue
        reason = onboard_reject_reason(s, fmp_profile=_fmp_profile(s))
        if reason:
            rejected.append(f"{s}: {reason}")
            continue
        valid.append(s)
    return valid, rejected


def phase_prices(engine, symbols: list[str], days: int = 230):
    """Chunked history backfill straight into eod_prices."""
    import yfinance as yf
    start = date.today() - timedelta(days=days)
    total = 0
    for i in range(0, len(symbols), 25):
        batch = symbols[i:i + 25]
        data = yf.download(" ".join(batch), start=str(start), auto_adjust=True,
                           group_by="ticker", progress=False, threads=True)
        rows = []
        for s in batch:
            try:
                df = data[s].dropna(subset=["Close"])
            except Exception:
                continue
            for idx, r in df.iterrows():
                rows.append({"s": s, "d": idx.date(),
                             "o": float(r["Open"]), "h": float(r["High"]),
                             "l": float(r["Low"]), "c": float(r["Close"]),
                             "v": int(r["Volume"] or 0)})
        # Small chunks + retry: writes cross the Railway proxy from outside
        # the datacenter and occasionally time out mid-send.
        for j in range(0, len(rows), 150):
            piece = rows[j:j + 150]
            for attempt in range(3):
                try:
                    with engine.begin() as conn:
                        conn.execute(text("""
                            INSERT INTO eod_prices (symbol, date, open, high, low, close, volume)
                            VALUES (:s, :d, :o, :h, :l, :c, :v)
                            ON CONFLICT (symbol, date) DO NOTHING
                        """), piece)
                    break
                except Exception as exc:
                    if attempt == 2:
                        raise
                    print(f"    write retry {attempt+1} ({exc})", flush=True)
                    time.sleep(5)
        total += len(rows)
        print(f"    prices: {min(i+25, len(symbols))}/{len(symbols)} tickers, {total} rows", flush=True)
        time.sleep(1)
    return total


def readiness_report(engine, symbols: list[str]) -> dict:
    with engine.connect() as conn:
        fund = {r[0]: r[1] for r in conn.execute(text(
            "SELECT symbol, company_name FROM fundamentals WHERE symbol = ANY(:s)"),
            {"s": symbols}).fetchall()}
        px = {r[0]: r[1] for r in conn.execute(text("""
            SELECT symbol, COUNT(*) FROM eod_prices WHERE symbol = ANY(:s)
            GROUP BY symbol"""), {"s": symbols}).fetchall()}
        filings = {r[0]: r[1] for r in conn.execute(text("""
            SELECT symbol, COUNT(*) FROM filings
            WHERE symbol = ANY(:s) AND content IS NOT NULL GROUP BY symbol"""),
            {"s": symbols}).fetchall()}
        themes = {r[0]: r[1] for r in conn.execute(text("""
            SELECT symbol, COUNT(*) FROM filing_themes WHERE symbol = ANY(:s)
            GROUP BY symbol"""), {"s": symbols}).fetchall()}
        embedded = {r[0]: r[1] for r in conn.execute(text("""
            SELECT symbol, COUNT(*) FROM filing_themes
            WHERE symbol = ANY(:s) AND embedding IS NOT NULL GROUP BY symbol"""),
            {"s": symbols}).fetchall()}
        exposed = {r[0] for r in conn.execute(text(
            "SELECT DISTINCT symbol FROM narrative_exposures WHERE symbol = ANY(:s)"),
            {"s": symbols}).fetchall()}

    ready, partial = [], []
    for s in symbols:
        checks = {
            "fundamentals": s in fund,
            "name":         bool(fund.get(s)),
            "prices>=120d": px.get(s, 0) >= 120,
            "filings":      filings.get(s, 0) >= 1,
            "themes":       themes.get(s, 0) >= 1,
            "embedded":     embedded.get(s, 0) >= 1,
            # exposures: "judged, none found" is valid — only require the
            # judging ran, which we approximate by themes+embeddings existing
        }
        missing = [k for k, ok in checks.items() if not ok]
        if missing:
            partial.append((s, missing))
        else:
            ready.append(s)
    return {"ready": ready, "partial": partial,
            "exposed_count": len([s for s in ready if s in exposed])}


def onboard(chunk_path: str, apply: bool = False):
    from pipeline.hidden_gem_scorer import get_engine
    from db.session import get_session

    symbols = _load_chunk(chunk_path)
    engine = get_engine()
    print(f"═══ ONBOARDING {len(symbols)} tickers from {chunk_path} ═══")

    print("\n[1/8] Validating against EDGAR + Yahoo...")
    valid, rejected = phase_validate(symbols)
    for r in rejected:
        print(f"    ✗ {r}")
    print(f"    ✓ {len(valid)} valid, {len(rejected)} rejected")

    print("\n[2/8] Fundamentals + company names...")
    from pipeline.fundamentals import fetch_fundamentals
    s = get_session()
    fetch_fundamentals(s, valid)
    s.close()

    print("\n[3/8] Price history (~7 months)...")
    phase_prices(engine, valid)

    print("\n[4/8] SEC filings (10-K/10-Q) + 8-Ks...")
    from pipeline.ingestion import run_ingestion
    from pipeline.events import run_events
    s = get_session()
    run_ingestion(s, valid)
    run_events(s, valid)
    s.close()

    print("\n[5/8] Narrative theme extraction...")
    from pipeline.narrative_extractor import run_extraction
    run_extraction()          # picks up every unthemed filing

    print("\n[6/8] Earnings transcripts (now that themes exist)...")
    from pipeline.earnings_ingestion import run_earnings_ingestion
    run_earnings_ingestion(quarters=4, force=False)
    run_extraction()          # theme the new transcripts too

    print("\n[7/8] Embeddings...")
    try:
        # sentence_transformers is deliberately absent from the Railway image
        # (heavy ML dep). On Railway this phase is skipped with a loud note —
        # run `python -m pipeline.embedding_builder` locally to backfill.
        # This exact import crashed chunk 2's onboarding on 2026-07-28.
        from pipeline.embedding_builder import run_embedding_build
        run_embedding_build()
    except ModuleNotFoundError:
        print("  ⚠ sentence_transformers not installed here — embeddings SKIPPED; "
              "backfill locally with: python -m pipeline.embedding_builder")

    print("\n[8/8] Narrative exposures (stateful ledger establishment)...")
    # v2 ledger (2026-07-27): establishment goes through verify_universe —
    # Sonnet-grade, two-vote union — never the Haiku from-scratch coin flip.
    from pipeline.exposure_ledger import verify_universe
    verify_universe(engine, symbols=valid)

    print("\n═══ READINESS REPORT ═══")
    rep = readiness_report(engine, valid)
    print(f"READY: {len(rep['ready'])}/{len(valid)} "
          f"({rep['exposed_count']} with narrative exposure)")
    for s_, missing in rep["partial"]:
        print(f"  PARTIAL {s_}: missing {', '.join(missing)}")

    if apply and rep["ready"]:
        tickers_path = root / "config" / "tickers.txt"
        current = {l.strip().upper() for l in open(tickers_path) if l.strip()}
        add = [s_ for s_ in rep["ready"] if s_ not in current]
        with open(tickers_path, "a") as f:
            f.write("\n".join(add) + "\n")
        print(f"\n✅ APPLIED: {len(add)} tickers appended to tickers.txt — live at next scheduled run")
    elif apply:
        print("\n⚠️  Nothing ready — tickers.txt untouched")
    else:
        print("\n(dry run — rerun with --apply to append READY tickers to tickers.txt)")
    return rep


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    onboard(sys.argv[1], apply="--apply" in sys.argv)
