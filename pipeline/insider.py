"""
Form 4 insider trading pipeline.

Form 4 is filed whenever a director, officer, or >10% owner buys or sells stock.
Open-market purchases (code P) by executives are one of the strongest free signals
in investing. This pipeline fetches, parses, and stores all transactions.

No LLM needed — Form 4s are structured XML.
"""
import time
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

import requests
from bs4 import BeautifulSoup
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models import InsiderTrade
from pipeline.ingestion import EDGAR_HEADERS, _build_cik_map

LOOKBACK_DAYS = 90

# Maps SEC transaction codes to readable types
# P = open-market purchase (most bullish), S = open-market sale, A = award/grant
TRANSACTION_MAP = {
    "P": "BUY",    # open-market purchase — most meaningful
    "S": "SELL",   # open-market sale
    "A": "AWARD",  # grant/award (compensation, not a signal)
    "D": "OTHER",  # disposition to issuer — routine/non-discretionary, NOT a
                   # sell signal (was mapped to SELL; part of the 40:1 skew,
                   # fixed 2026-08-04)
    "F": "OTHER",  # tax withholding on vesting (neutral)
    "M": "OTHER",  # option exercise
    "G": "OTHER",  # gift
    "J": "OTHER",  # other acquisition/disposition
    "C": "OTHER",  # conversion
    "E": "OTHER",  # expiration
    "X": "OTHER",  # exercise of in-the-money expired derivative
}


# ---------------------------------------------------------------------------
# EDGAR helpers
# ---------------------------------------------------------------------------

def _get_form4_urls(cik: str, lookback_days: int = LOOKBACK_DAYS) -> list[dict]:
    url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
    resp = requests.get(url, headers=EDGAR_HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    cutoff = datetime.utcnow() - timedelta(days=lookback_days)
    recent = data.get("filings", {}).get("recent", {})
    results = []

    for i, form in enumerate(recent.get("form", [])):
        if form != "4":
            continue
        filing_date = datetime.strptime(recent["filingDate"][i], "%Y-%m-%d")
        if filing_date < cutoff:
            break

        acc = recent["accessionNumber"][i]
        acc_clean = acc.replace("-", "")
        primary = recent["primaryDocument"][i]
        # primaryDocument may point to an XSLT viewer subdirectory —
        # strip it to get the raw XML at the accession root.
        doc = primary.split("/")[-1] if "/" in primary else primary
        results.append({
            "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{doc}",
            "filed": recent["filingDate"][i],
        })

    return results


def _safe_decimal(val: str | None) -> Decimal | None:
    if not val:
        return None
    try:
        return Decimal(str(val).strip().replace(",", ""))
    except InvalidOperation:
        return None


def _parse_form4(url: str, symbol: str) -> list[dict]:
    """Parse a Form 4 XML and return a list of transaction dicts."""
    resp = requests.get(url, headers=EDGAR_HEADERS, timeout=15)
    resp.raise_for_status()

    # Form 4s are XML — use lxml-xml parser for correctness
    soup = BeautifulSoup(resp.content, "lxml-xml")

    # Reporting person
    person_name = ""
    person_title = ""
    owner = soup.find("reportingOwner")
    if owner:
        name_tag = owner.find("rptOwnerName")
        person_name = name_tag.get_text(strip=True).title() if name_tag else ""
        title_tag = owner.find("officerTitle")
        person_title = title_tag.get_text(strip=True).title() if title_tag else ""
        if not person_title:
            if owner.find("isDirector") and owner.find("isDirector").get_text(strip=True) == "1":
                person_title = "Director"

    trades = []

    for tx in soup.find_all("nonDerivativeTransaction"):
        code_tag = tx.find("transactionCode")
        if not code_tag:
            continue
        raw_code = code_tag.get_text(strip=True)
        tx_type = TRANSACTION_MAP.get(raw_code, "OTHER")

        date_tag = tx.find("transactionDate")
        date_val = date_tag.find("value").get_text(strip=True) if date_tag and date_tag.find("value") else None
        if not date_val:
            continue

        shares_tag = tx.find("transactionShares")
        shares = _safe_decimal(shares_tag.find("value").get_text() if shares_tag and shares_tag.find("value") else None)

        price_tag = tx.find("transactionPricePerShare")
        price = _safe_decimal(price_tag.find("value").get_text() if price_tag and price_tag.find("value") else None)

        owned_tag = tx.find("sharesOwnedFollowingTransaction")
        owned_after = _safe_decimal(owned_tag.find("value").get_text() if owned_tag and owned_tag.find("value") else None)

        total_value = (shares * price) if shares and price else None

        trades.append({
            "symbol": symbol,
            "person_name": person_name,
            "person_title": person_title,
            "transaction_date": datetime.strptime(date_val, "%Y-%m-%d").date(),
            "transaction_type": tx_type,
            "shares": shares,
            "price_per_share": price,
            "total_value": total_value,
            "shares_owned_after": owned_after,
            "form4_url": url,
        })

    return trades


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_insiders(session: Session, tickers: list[str]) -> dict:
    """
    Fetch and parse recent Form 4 filings for all tracked tickers.
    Only stores BUY and SELL transactions (skips awards/option exercises).
    """
    print(f"Building CIK map for {len(tickers)} tickers...")
    cik_map = _build_cik_map(tickers)

    added = 0
    errors = 0

    for symbol, cik in cik_map.items():
        try:
            form4_filings = _get_form4_urls(cik)
            if not form4_filings:
                continue

            print(f"  [Form4] {symbol}: {len(form4_filings)} filing(s)")

            for filing in form4_filings:
                try:
                    trades = _parse_form4(filing["url"], symbol)
                    for trade in trades:
                        # Only store meaningful transactions
                        _nm = (trade.get("person_name") or "").upper()
                        if any(t in _nm for t in (" L.P", " LP", " LLC", " FUND",
                                                  " PARTNERS", " CAPITAL", " HOLDINGS",
                                                  " TRUST", " MANAGEMENT", " SPV")):
                            # Institutional 10%-owner filers (e.g. Silver Lake's
                            # entities: 15,700 DELL rows in 6 weeks) are share-
                            # distribution plumbing, not insider sentiment —
                            # they drowned the real signal 40:1 and bloated the
                            # table to 117MB. Individuals only (2026-08-04).
                            continue
                        if trade["transaction_type"] not in ("BUY", "SELL"):
                            continue
                        try:
                            session.add(InsiderTrade(**trade))
                            session.commit()
                            added += 1
                        except IntegrityError:
                            session.rollback()  # duplicate — already stored
                    time.sleep(0.1)
                except Exception as exc:
                    print(f"    parse error: {exc}")
                    session.rollback()

        except Exception as exc:
            errors += 1
            print(f"  [Form4] {symbol} error: {exc}")
            session.rollback()

    print(f"\nInsider ingest complete: {added} new transactions, {errors} errors.")
    return {"added": added, "errors": errors}
