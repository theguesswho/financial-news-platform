#!/usr/bin/env python3
"""
CLI entry point for the financial news platform.

Commands:
  ingest    — Pull new 10-K/10-Q filings and EOD prices for all tickers
  analyze   — Run Claude Sonnet detailed analysis on unprocessed filings
  screen    — Run Claude Haiku screener across all tickers (~$4 for 500 stocks)
  events    — Fetch and classify recent 8-K material events (earnings, M&A, exec changes)
  insiders  — Fetch and parse Form 4 insider trades (open-market buys/sells)
  pipeline  — Run ingest + analyze + events + insiders
  ui        — Launch the Streamlit dashboard
"""
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "ingest":
        from pipeline.runner import pipeline_ingest
        pipeline_ingest()

    elif cmd == "analyze":
        from pipeline.runner import pipeline_analyze
        pipeline_analyze()

    elif cmd == "screen":
        import json
        from pathlib import Path
        from db.session import get_session
        from pipeline.screener import run_screener
        tickers = [l.strip().upper() for l in open("config/tickers.txt") if l.strip()]
        force = "--force" in sys.argv
        session = get_session()
        try:
            run_screener(session, tickers, force=force)
        finally:
            session.close()

    elif cmd == "events":
        tickers = [l.strip().upper() for l in open("config/tickers.txt") if l.strip()]
        from db.session import get_session
        from pipeline.events import run_events
        session = get_session()
        try:
            run_events(session, tickers)
        finally:
            session.close()

    elif cmd == "insiders":
        tickers = [l.strip().upper() for l in open("config/tickers.txt") if l.strip()]
        from db.session import get_session
        from pipeline.insider import run_insiders
        session = get_session()
        try:
            run_insiders(session, tickers)
        finally:
            session.close()

    elif cmd == "pipeline":
        from pipeline.runner import pipeline_full
        pipeline_full()

    elif cmd == "brief":
        from db.session import get_session
        from pipeline.brief import get_or_generate_brief
        session = get_session()
        try:
            brief = get_or_generate_brief(session, force=True)
            import json; print(json.dumps(brief, indent=2))
        finally:
            session.close()

    elif cmd == "themes-screener":
        from db.session import get_session
        from pipeline.themes import run_theme_extraction_from_screener
        session = get_session()
        try:
            result = run_theme_extraction_from_screener(session)
            print(f"\nResult: {result}")
        finally:
            session.close()

    elif cmd == "ui":
        from pathlib import Path
        subprocess.run(
            ["streamlit", "run", "ui/Home.py"],
            cwd=Path(__file__).parent,
        )

    else:
        print(f"Unknown command: {cmd!r}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
