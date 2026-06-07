"""
Ingestion pipeline: pulls new SEC filings for tracked tickers and EOD prices from FMP.
"""
import os
import re
import time
import warnings
from datetime import datetime

from bs4 import XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from db.models import EodPrice, Filing

EDGAR_HEADERS = {"User-Agent": "Financial Research Platform admin@example.com"}
FMP_API_KEY = os.getenv("FMP_API_KEY", "")
MAX_CONTENT_CHARS = 50_000
FILING_TYPES = ("10-K", "10-Q")


# ---------------------------------------------------------------------------
# EDGAR helpers
# ---------------------------------------------------------------------------

def _build_cik_map(tickers: list[str]) -> dict[str, str]:
    """Return {ticker: cik_str} for every ticker we track, using EDGAR's index."""
    print("Fetching EDGAR company tickers index...")
    resp = requests.get(
        "https://www.sec.gov/files/company_tickers.json",
        headers=EDGAR_HEADERS,
        timeout=20,
    )
    resp.raise_for_status()
    ticker_set = {t.upper() for t in tickers}
    cik_map: dict[str, str] = {}
    for entry in resp.json().values():
        t = entry["ticker"].upper()
        if t in ticker_set:
            cik_map[t] = str(entry["cik_str"])
    print(f"Mapped {len(cik_map)}/{len(tickers)} tickers to CIKs.")
    return cik_map


def _get_edgar_filings(ticker: str, cik: str, n: int = 5) -> list[dict]:
    """Return up to n recent 10-K/10-Q filings for this CIK."""
    url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
    resp = requests.get(url, headers=EDGAR_HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    results = []

    for i, form in enumerate(forms):
        if form not in FILING_TYPES:
            continue
        acc = recent["accessionNumber"][i]
        acc_clean = acc.replace("-", "")
        primary = recent["primaryDocument"][i]
        filing_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}"
            f"/{acc_clean}/{primary}"
        )
        results.append(
            {
                "type": form,
                "date": recent["filingDate"][i],
                "url": filing_url,
                "title": f"{form} — {data.get('name', ticker)} ({recent['filingDate'][i]})",
            }
        )
        if len(results) >= n:
            break

    return results


def _find_html_url(xml_url: str) -> str:
    """
    When EDGAR's primaryDocument is an XBRL XML file, find the actual HTML
    report by parsing the filing index page.
    """
    # Index lives at the directory level: .../data/{cik}/{acc}/
    base = xml_url.rsplit("/", 1)[0] + "/"
    resp = requests.get(base, headers=EDGAR_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "lxml")

    # The index table lists docs with their SEC type. Prefer the row whose
    # type matches 10-K / 10-Q and whose document is an htm/html file.
    for row in soup.select("table tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        doc_type = cells[3].get_text(strip=True)
        doc_link = cells[2].find("a")
        if doc_link and doc_type in ("10-K", "10-Q", "10-K/A", "10-Q/A"):
            href = doc_link["href"]
            if href.lower().endswith((".htm", ".html")):
                return "https://www.sec.gov" + href

    # Fallback: any .htm link that isn't the index itself
    for a in soup.select("a[href]"):
        href = a["href"]
        if href.lower().endswith((".htm", ".html")) and "index" not in href.lower():
            return "https://www.sec.gov" + href

    return xml_url  # give up and use original


_XBRL_LINE = re.compile(
    r"^("
    r"https?://\S+"           # namespace URLs
    r"|/\S+"                  # root-relative paths
    r"|[PpYyQqMmDd\d\-\.:TZ]+$"  # XBRL duration codes e.g. P1Y, PT10M
    r"|0{6,}\d*"              # padded CIK numbers
    r")$"
)


def _is_readable(line: str) -> bool:
    """Return True if the line looks like human-readable report text."""
    if len(line) < 8:
        return False
    if _XBRL_LINE.match(line):
        return False
    # Keep lines that have at least a few letters (not pure numbers/symbols)
    if sum(c.isalpha() for c in line) < 4:
        return False
    return True


def _scrape_filing_content(url: str) -> str:
    # XBRL XML files contain no readable text — swap for the HTML document
    if url.lower().endswith((".xml", ".xsd")):
        url = _find_html_url(url)

    resp = requests.get(url, headers=EDGAR_HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "lxml")

    # Remove non-content elements including hidden XBRL context blocks
    for tag in soup(["script", "style"]):
        tag.decompose()
    for tag in soup.find_all(style=re.compile(r"display\s*:\s*none", re.I)):
        tag.decompose()

    raw_lines = soup.get_text(separator="\n").splitlines()
    lines = [ln.strip() for ln in raw_lines if _is_readable(ln.strip())]
    return "\n".join(lines)[:MAX_CONTENT_CHARS]


# ---------------------------------------------------------------------------
# EOD prices
# ---------------------------------------------------------------------------

def _fetch_eod_prices(session: Session, symbols: list[str]) -> int:
    added = 0
    for symbol in symbols:
        try:
            url = (
                f"https://financialmodelingprep.com/api/v3/historical-price-full"
                f"/{symbol}?timeseries=60&apikey={FMP_API_KEY}"
            )
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            for day in data.get("historical", []):
                date = datetime.strptime(day["date"], "%Y-%m-%d").date()
                exists = (
                    session.query(EodPrice)
                    .filter_by(symbol=symbol, date=date)
                    .first()
                )
                if not exists:
                    session.add(
                        EodPrice(
                            symbol=symbol,
                            date=date,
                            open=day.get("open"),
                            high=day.get("high"),
                            low=day.get("low"),
                            close=day.get("close"),
                            volume=day.get("volume"),
                        )
                    )
                    added += 1

            session.commit()
            time.sleep(0.3)  # FMP free tier rate limit
        except Exception as exc:
            print(f"  [prices] {symbol}: {exc}")
            session.rollback()

    return added


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_ingestion(session: Session, tickers: list[str]) -> dict:
    """
    Fetch new SEC filings and EOD prices for all tracked tickers.
    Returns a summary dict.
    """
    cik_map = _build_cik_map(tickers)
    filings_added = 0

    for ticker, cik in cik_map.items():
        try:
            edgar_filings = _get_edgar_filings(ticker, cik)
            for f in edgar_filings:
                if session.query(Filing).filter_by(url=f["url"]).first():
                    continue  # already ingested

                print(f"  [ingest] {ticker}: {f['title']}")
                try:
                    content = _scrape_filing_content(f["url"])
                except Exception as exc:
                    print(f"    scrape failed: {exc}")
                    content = ""

                session.add(
                    Filing(
                        symbol=ticker,
                        cik=cik,
                        filing_type=f["type"],
                        title=f["title"],
                        url=f["url"],
                        filing_date=datetime.fromisoformat(f["date"]),
                        content=content,
                    )
                )
                session.commit()
                filings_added += 1
                time.sleep(0.15)  # be polite to EDGAR

        except Exception as exc:
            print(f"  [ingest] {ticker} error: {exc}")
            session.rollback()

    print(f"\nFetching EOD prices for {len(tickers)} tickers...")
    prices_added = _fetch_eod_prices(session, tickers)

    return {"filings_added": filings_added, "prices_added": prices_added}
