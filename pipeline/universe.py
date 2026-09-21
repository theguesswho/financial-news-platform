"""Live scoring universe.

Edmund ruling 2026-09-20: do not include ETFs at all. That is an
exclusion from score / fetch / onboard / growth / theming / assessor
— not a freshness-sentinel mute on one name.

R1 added NON_FILER_SYMBOLS = {GLD} in freshness_sentinel. Wrong shape.
This module is the single list. Every consumer imports it.

Prod inventory (Grok, 2026-09-20 — do not invent beyond this):
  growth_source: 830 fmp / 1 null (FMP cutover held)
  fundamentals n=831 vs tickers.txt 827
  Extra vs tickers: GLD (Spdr Gold Trust, sector/industry NULL,
    growth_source NULL) = ETF. Soft-exclude; history row stays.
  Other extras ASND, CHKP, GTLS, OZK = operating companies, NOT ETFs.
    Leave in place (separate hygiene).
  SPY / MDY are benchmarks only (pipeline/track_record.py); not in
    fundamentals. Keep. They are not in ETF_SYMBOLS.
  Only null-sector row was GLD.

Add a name to ETF_SYMBOLS only after a vendor check (Yahoo quoteType
or FMP isEtf) says it is an ETF / fund. Do not guess from the ticker
string.
"""
from __future__ import annotations

# Confirmed ETFs / grantor trusts. History rows stay in fundamentals;
# these names are skipped going forward.
ETF_SYMBOLS: frozenset[str] = frozenset({
    "GLD",  # SPDR Gold Trust — grantor trust; confirmed 2026-09-20
})

# Yahoo quoteType values that are not operating companies.
# Commodity grantor trusts (GLD) report as ETF.
NON_EQUITY_QUOTE_TYPES: frozenset[str] = frozenset({
    "ETF",
    "MUTUALFUND",
    "MONEYMARKET",
    "INDEX",
    "CURRENCY",
    "CRYPTOCURRENCY",
    "FUTURE",
    "OPTION",
})

# FMP-empty KPI buckets (DATA_SCORECARD). Three stories, not one alarm.
BUCKET_ETF = "etf"
BUCKET_QUOTA = "quota_429"
BUCKET_TRANSPORT = "transport"
BUCKET_HOLE = "true_hole"
EMPTY_BUCKETS = (BUCKET_ETF, BUCKET_QUOTA, BUCKET_TRANSPORT, BUCKET_HOLE)


def norm_symbol(symbol: str | None) -> str:
    return (symbol or "").strip().upper()


def is_etf_symbol(symbol: str | None) -> bool:
    return norm_symbol(symbol) in ETF_SYMBOLS


def is_universe_symbol(symbol: str | None) -> bool:
    """True iff the symbol may be scored, fetched, grown, themed, assessed."""
    s = norm_symbol(symbol)
    return bool(s) and s not in ETF_SYMBOLS


def filter_universe(symbols) -> list[str]:
    """Preserve order, drop blanks and ETFs."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in symbols or []:
        s = norm_symbol(raw)
        if not s or s in seen or s in ETF_SYMBOLS:
            continue
        seen.add(s)
        out.append(s)
    return out


def excluded_from(symbols) -> list[str]:
    """ETF names present in `symbols`, original order, de-duplicated."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in symbols or []:
        s = norm_symbol(raw)
        if s in ETF_SYMBOLS and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def is_etf_quote_type(quote_type: str | None) -> bool:
    if not quote_type:
        return False
    return str(quote_type).strip().upper() in NON_EQUITY_QUOTE_TYPES


def is_etf_fmp_profile(profile: dict | None) -> bool:
    """True when FMP /profile marks the name as an ETF or fund."""
    if not isinstance(profile, dict):
        return False
    for key in ("isEtf", "isFund", "is_etf", "is_fund"):
        v = profile.get(key)
        if v is True or v == 1 or v == "true":
            return True
    return False


def onboard_reject_reason(
    symbol: str,
    *,
    quote_type: str | None = None,
    fmp_profile: dict | None = None,
) -> str | None:
    """Reject reason if this name is an ETF / grantor trust / fund.

    None means 'not rejected on ETF grounds' — CIK and price still apply.
    Known-list hits do not need a vendor call.
    """
    s = norm_symbol(symbol)
    if s in ETF_SYMBOLS:
        return "ETF / non-filer (excluded from universe)"
    if is_etf_quote_type(quote_type):
        return (f"Yahoo quoteType={quote_type} "
                "(ETF/fund, not an operating company)")
    if is_etf_fmp_profile(fmp_profile):
        return "FMP profile isEtf/isFund=true"
    return None


def classify_fmp_empty(symbol: str, failure_kind: str | None = None) -> str:
    """Bucket one FMP-empty symbol.

    failure_kind: '429' | 'transport' | 'empty' | None
    ETF membership wins — a gold trust with an empty income statement
    is not a vendor hole and is not a 429.
    """
    if is_etf_symbol(symbol):
        return BUCKET_ETF
    if failure_kind == "429":
        return BUCKET_QUOTA
    if failure_kind == "transport":
        return BUCKET_TRANSPORT
    return BUCKET_HOLE


def classify_empty_list(symbols, failure_kinds: dict | None = None) -> dict:
    """{bucket: [symbols]} — every input name, no truncation."""
    kinds = failure_kinds or {}
    buckets = {b: [] for b in EMPTY_BUCKETS}
    for raw in symbols or []:
        s = norm_symbol(raw)
        kind = kinds.get(s) or kinds.get(raw)
        buckets[classify_fmp_empty(s, kind)].append(s)
    return buckets


def empty_kpi(empty_symbols, failure_kinds=None, n_symbols=0) -> dict:
    """Structured FMP-empty stat for logs / scorecard.

    Keeps the FULL empty list. Callers must not slice it.
    """
    empty = [norm_symbol(s) for s in (empty_symbols or [])]
    buckets = classify_empty_list(empty, failure_kinds)
    n = int(n_symbols or 0)
    return {
        "empty_count": len(empty),
        "empty": empty,
        "empty_rate": (round(len(empty) / n, 4) if n else None),
        "empty_buckets": {k: v for k, v in buckets.items() if v},
        "empty_bucket_counts": {k: len(v) for k, v in buckets.items()},
    }


def format_empty_kpi(kpi: dict) -> str:
    """One log line: counts + full list. Never truncates."""
    counts = kpi.get("empty_bucket_counts") or {}
    bits = [f"{k}={counts.get(k, 0)}" for k in EMPTY_BUCKETS]
    rate = kpi.get("empty_rate")
    rate_s = f"{rate:.4f}" if isinstance(rate, float) else "n/a"
    return (f"empty_count={kpi.get('empty_count', 0)} empty_rate={rate_s} "
            f"buckets[{', '.join(bits)}] empty={kpi.get('empty') or []}")
