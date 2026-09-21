"""Offline checks for sitting 1 — no ETFs in the universe.

No database, no Railway, no secrets. Run:

    python scripts/test_universe_hygiene.py
"""
from __future__ import annotations

import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from pipeline.universe import (
    BUCKET_ETF,
    BUCKET_HOLE,
    BUCKET_QUOTA,
    BUCKET_TRANSPORT,
    ETF_SYMBOLS,
    classify_fmp_empty,
    empty_kpi,
    excluded_from,
    filter_universe,
    format_empty_kpi,
    is_etf_fmp_profile,
    is_etf_quote_type,
    is_universe_symbol,
    onboard_reject_reason,
)
# freshness_sentinel / fmp_quarterly import sqlalchemy — check the
# alias and helper from source when the dep is missing, else import.


OPERATING_EXTRAS = ("ASND", "CHKP", "GTLS", "OZK")
BENCHMARKS = ("SPY", "MDY")


def check(name, cond, detail=""):
    if not cond:
        raise AssertionError(f"FAIL {name}: {detail}")
    print(f"  ok  {name}")


def main():
    print("universe hygiene")

    check("GLD is the confirmed ETF", ETF_SYMBOLS == frozenset({"GLD"}))
    sent = (root / "pipeline" / "freshness_sentinel.py").read_text()
    check("sentinel imports shared list",
          "from pipeline.universe import ETF_SYMBOLS" in sent)
    check("sentinel alias is the shared list",
          "NON_FILER_SYMBOLS = ETF_SYMBOLS" in sent)
    try:
        from pipeline.freshness_sentinel import NON_FILER_SYMBOLS
        check("sentinel alias equals ETF_SYMBOLS",
              NON_FILER_SYMBOLS == ETF_SYMBOLS)
    except ModuleNotFoundError as exc:
        print(f"  skip sentinel import ({exc.name})")
    check("GLD not universe", not is_universe_symbol("gld"))
    check("AAPL is universe", is_universe_symbol("AAPL"))

    for sym in OPERATING_EXTRAS:
        check(f"{sym} is not an ETF", not is_etf_symbol_safe(sym),
              "operating-company extra — do not delete as ETF")
        check(f"{sym} stays in filter",
              filter_universe(["AAPL", sym, "GLD"]) == ["AAPL", sym])

    for sym in BENCHMARKS:
        check(f"{sym} is not in ETF_SYMBOLS (benchmark)",
              sym not in ETF_SYMBOLS)

    mixed = ["AAPL", "gld", "GLD", "LW", "MAS", "EA"]
    check("filter drops GLD only, keeps order",
          filter_universe(mixed) == ["AAPL", "LW", "MAS", "EA"])
    check("excluded_from finds GLD once", excluded_from(mixed) == ["GLD"])

    check("known-list onboard reject",
          onboard_reject_reason("GLD") is not None)
    check("equity not rejected without vendor",
          onboard_reject_reason("AAPL") is None)
    check("quoteType ETF rejected",
          onboard_reject_reason("XYZ", quote_type="ETF") is not None)
    check("quoteType MUTUALFUND rejected",
          onboard_reject_reason("XYZ", quote_type="MUTUALFUND") is not None)
    check("quoteType EQUITY accepted",
          onboard_reject_reason("XYZ", quote_type="EQUITY") is None)
    check("is_etf_quote_type ETF", is_etf_quote_type("ETF"))
    check("is_etf_quote_type EQUITY", not is_etf_quote_type("EQUITY"))
    check("FMP isEtf", is_etf_fmp_profile({"isEtf": True}))
    check("FMP isFund", is_etf_fmp_profile({"isFund": True}))
    check("FMP operating", not is_etf_fmp_profile({"isEtf": False, "isFund": False}))
    check("FMP reject reason",
          onboard_reject_reason("XYZ", fmp_profile={"isEtf": True}) is not None)

    # phase_validate known-list short-circuit: no vendor I/O
    try:
        from pipeline.onboard_universe import phase_validate
        valid, rejected = phase_validate(["GLD"])
        check("phase_validate rejects GLD with no vendor",
              valid == [] and any(r.startswith("GLD:") for r in rejected),
              f"valid={valid} rejected={rejected}")
        check("phase_validate reason names ETF",
              any("ETF" in r for r in rejected), rejected)
    except ModuleNotFoundError as exc:
        print(f"  skip phase_validate import ({exc.name})")
        check("onboard_reject_reason stands in for the gate",
              onboard_reject_reason("GLD") is not None)

    empty = [f"S{i:02d}" for i in range(25)] + ["GLD", "LW"]
    kinds = {"GLD": "empty", "LW": "empty", "S00": "429", "S01": "transport"}
    kpi = empty_kpi(empty, kinds, n_symbols=100)
    check("empty_count is full length", kpi["empty_count"] == 27)
    check("empty list not truncated", len(kpi["empty"]) == 27)
    check("GLD bucketed etf even if empty",
          classify_fmp_empty("GLD", "empty") == BUCKET_ETF)
    check("429 bucket", classify_fmp_empty("LW", "429") == BUCKET_QUOTA)
    check("true hole", classify_fmp_empty("LW", "empty") == BUCKET_HOLE)
    check("transport bucket", classify_fmp_empty("MAS", "transport") == BUCKET_TRANSPORT)
    check("empty_rate", kpi["empty_rate"] == 0.27)
    line = format_empty_kpi(kpi)
    check("log line keeps S24 (would be cut by [:20])", "S24" in line)
    check("log line keeps GLD", "GLD" in line)
    check("no slice leftover in growth module",
          "stats[\"empty\"] = stats[\"empty\"][:20]" not in
          (root / "pipeline" / "fmp_quarterly.py").read_text())
    check("no slice leftover in canonical module",
          "stats[\"empty\"] = stats[\"empty\"][:20]" not in
          (root / "pipeline" / "fmp_canonical.py").read_text())

    try:
        from pipeline.fmp_quarterly import _worse_kind
        check("worse_kind prefers 429", _worse_kind("empty", "429") == "429")
        check("worse_kind prefers transport over empty",
              _worse_kind("empty", "transport") == "transport")
    except ModuleNotFoundError as exc:
        print(f"  skip _worse_kind import ({exc.name})")

    # tickers.txt must not contain the confirmed ETF (fetch universe)
    tickers = [l.strip().upper() for l in
               (root / "config" / "tickers.txt").read_text().splitlines()
               if l.strip()]
    check("GLD not in tickers.txt", "GLD" not in tickers)
    from pipeline.universe import filter_universe as fu
    check("_load_tickers shape would drop GLD if present",
          "GLD" not in fu(tickers + ["GLD"]))

    print("ALL PASS")
    return 0


def is_etf_symbol_safe(sym):
    from pipeline.universe import is_etf_symbol
    return is_etf_symbol(sym)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(exc)
        sys.exit(1)
