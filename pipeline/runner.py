"""
Orchestrates the full ingestion + analysis pipeline.
"""
import json
import os
from pathlib import Path

from db.session import get_session
from pipeline.ingestion import run_ingestion
from pipeline.analyzer import run_analysis

CONFIG_DIR = Path(__file__).parent.parent / "config"


def _load_tickers() -> list[str]:
    path = CONFIG_DIR / "tickers.txt"
    with open(path) as f:
        return [line.strip().upper() for line in f if line.strip()]


def _load_company_names() -> dict[str, str]:
    path = CONFIG_DIR / "company_map.json"
    with open(path) as f:
        return json.load(f)


def pipeline_ingest():
    tickers = _load_tickers()
    print(f"Starting ingestion for {len(tickers)} tickers...\n")
    session = get_session()
    try:
        result = run_ingestion(session, tickers)
        print(f"\nIngestion complete: {result['filings_added']} filings, {result['prices_added']} price records added.")
    finally:
        session.close()


def pipeline_analyze():
    print("Starting analysis pass...\n")
    session = get_session()
    try:
        result = run_analysis(session)
        print(f"\nAnalysis complete: {result['analyzed']} filing(s) processed.")
    finally:
        session.close()


def pipeline_full():
    pipeline_ingest()
    print()
    pipeline_analyze()
