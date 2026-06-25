"""
Cloud Scheduler — runs 24/7 on Railway.

Handles all time-sensitive data jobs:
  06:00 UTC daily      — prices, fundamentals, insiders, scoring, archive
  13:00 UTC Mon–Fri    — mid-day prices + rescore
  21:00 UTC Mon–Fri    — after-close prices + earnings + rescore + qual assessment

Heavy Claude jobs (embeddings, deep dives, full qual pass) stay on the
laptop scheduler (scheduler.py) and run weekly on Sunday evenings.
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime
from sqlalchemy import text

import yfinance as yf
yf.set_tz_cache_location("/tmp/yf_tz_cache")

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

load_dotenv(override=True)

root = Path(__file__).parent
sys.path.insert(0, str(root))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.StreamHandler()],  # Railway captures stdout
)
logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_tickers():
    with open(root / "config" / "tickers.txt") as f:
        return [l.strip().upper() for l in f if l.strip()]

def _banner(t): logger.info("=" * 72 + f"\n  {t}\n" + "=" * 72)
def _step(n, l): logger.info(f"  Step {n}: {l}…")
def _ok(m):      logger.info(f"    ✓  {m}")
def _err(m, e):  logger.error(f"    ✗  {m}: {e}", exc_info=True)

def _wait_for_network(timeout=60):
    import socket, time
    for _ in range(timeout // 5):
        try:
            socket.setdefaulttimeout(3)
            socket.getaddrinfo("query2.finance.yahoo.com", 443)
            return True
        except OSError:
            time.sleep(5)
    logger.warning("Network not reachable after %ds — proceeding anyway", timeout)
    return False


# ── Score + archive helper (used by all three jobs) ───────────────────────────

def _score_and_archive():
    """Single scoring pass — returns (engine, gems) for downstream use."""
    from pipeline.hidden_gem_scorer import get_engine, score_all_stocks
    from pipeline.leaderboard_archiver import create_table, archive_leaderboard, apply_qual_tiers
    engine = get_engine()
    gems = score_all_stocks(engine)
    create_table(engine)
    result = archive_leaderboard(engine, gems=gems)
    apply_qual_tiers(engine)
    _ok(f"{len(gems)} scored, {result.get('on_board', 0)} on-board")
    return engine, gems


# ── Daily 6 AM UTC ───────────────────────────────────────────────────────────

def daily_data_update():
    _banner(f"DAILY UPDATE  {datetime.now():%Y-%m-%d %H:%M}")
    _wait_for_network()
    symbols = _load_tickers()

    _step(1, "EOD prices")
    try:
        from db.session import get_session
        from pipeline.prices import fetch_prices
        s = get_session()
        r = fetch_prices(s, symbols, days=2)
        s.close()
        _ok(f"{r.get('added', 0)} price records added")
    except Exception as e:
        _err("Prices failed", e)

    _step(2, "Fundamentals refresh")
    try:
        from pipeline.fundamentals import refresh_fundamentals
        from db.session import get_session
        s = get_session()
        r = refresh_fundamentals(s, symbols)
        s.close()
        _ok(f"{r.get('updated', 0)} updated")
    except Exception as e:
        _err("Fundamentals failed", e)

    _step(3, "Insider trades (SEC Form 4)")
    try:
        from db.session import get_session
        from pipeline.insiders import fetch_insiders
        s = get_session()
        r = fetch_insiders(s, symbols)
        s.close()
        _ok(f"{r.get('added', 0)} insider records added")
    except Exception as e:
        _err("Insiders failed", e)

    _step(4, "Earnings transcripts")
    try:
        from pipeline.earnings_ingestion import run_earnings_ingestion
        r = run_earnings_ingestion(quarters=1, force=False)
        _ok(f"Earnings ingestion done: {r}")
    except Exception as e:
        _err("Earnings ingestion failed", e)

    _step(5, "Re-score + archive leaderboard")
    engine = None
    gems = None
    try:
        engine, gems = _score_and_archive()
    except Exception as e:
        _err("Scoring failed", e)

    _step(6, "Archive daily scores")
    try:
        from pipeline.daily_score_archiver import archive_daily_scores
        r = archive_daily_scores()
        _ok(f"{r.get('archived', 0)} scores archived")
    except Exception as e:
        _err("Daily score archive failed", e)

    _step(7, "Filing synopses")
    try:
        from pipeline.synopsis import get_or_generate_synopsis
        from pipeline.hidden_gem_scorer import get_engine as _ge
        import json
        from datetime import timedelta
        eng = _ge()
        cutoff = datetime.now() - timedelta(days=14)
        with eng.connect() as conn:
            rows = conn.execute(text("""
                SELECT f.id, f.symbol, f.filing_type, f.title, f.llm_analysis,
                       ft.trajectory, ft.management_tone, ft.catalysts, ft.risks
                FROM filings f
                JOIN filing_themes ft ON ft.filing_id = f.id
                WHERE f.filing_date >= :c AND ft.narrative_strength >= 0.60
                  AND (f.llm_analysis IS NULL
                       OR (f.llm_analysis::jsonb->>'synopsis') IS NULL)
            """), {"c": cutoff}).fetchall()
        generated = 0
        for r in rows:
            try:
                cats = r[7] if isinstance(r[7], list) else (json.loads(r[7]) if r[7] else [])
                rsks = r[8] if isinstance(r[8], list) else (json.loads(r[8]) if r[8] else [])
                get_or_generate_synopsis(eng, r[0], r[1], r[2], r[3], r[4], r[5], r[6], cats, rsks)
                generated += 1
            except Exception:
                pass
        eng.dispose()
        _ok(f"{generated} synopses generated")
    except Exception as e:
        _err("Synopsis generation failed", e)

    if engine:
        engine.dispose()
    _banner("DAILY UPDATE COMPLETE")


# ── Mid-day 1 PM UTC Mon–Fri ─────────────────────────────────────────────────

def midday_refresh():
    _banner(f"MID-DAY REFRESH  {datetime.now():%Y-%m-%d %H:%M}")
    _wait_for_network()
    symbols = _load_tickers()

    _step(1, "Intraday prices")
    try:
        from db.session import get_session
        from pipeline.prices import fetch_prices
        s = get_session()
        r = fetch_prices(s, symbols, days=2)
        s.close()
        _ok(f"{r.get('added', 0)} price records added")
    except Exception as e:
        _err("Prices failed", e)

    _step(2, "Re-score + archive leaderboard")
    try:
        _score_and_archive()
    except Exception as e:
        _err("Scoring failed", e)

    _step(3, "Earnings transcripts")
    try:
        from pipeline.earnings_ingestion import run_earnings_ingestion
        r = run_earnings_ingestion(quarters=1, force=False)
        _ok(f"Earnings ingestion done: {r}")
    except Exception as e:
        _err("Earnings ingestion failed", e)

    _banner("MID-DAY REFRESH COMPLETE")


# ── After-close 9 PM UTC Mon–Fri ─────────────────────────────────────────────

def after_close_refresh():
    _banner(f"AFTER-CLOSE REFRESH  {datetime.now():%Y-%m-%d %H:%M}")
    _wait_for_network()
    symbols = _load_tickers()

    _step(1, "Closing prices")
    try:
        from db.session import get_session
        from pipeline.prices import fetch_prices
        s = get_session()
        r = fetch_prices(s, symbols, days=2)
        s.close()
        _ok(f"{r.get('added', 0)} price records added")
    except Exception as e:
        _err("Prices failed", e)

    _step(2, "Earnings transcripts")
    try:
        from pipeline.earnings_ingestion import run_earnings_ingestion
        r = run_earnings_ingestion(quarters=1, force=False)
        _ok(f"Earnings ingestion done: {r}")
    except Exception as e:
        _err("Earnings ingestion failed", e)

    _step(3, "Material events (8-K)")
    try:
        from db.session import get_session
        from pipeline.events import run_events
        s = get_session()
        r = run_events(s, symbols)
        s.close()
        _ok(f"{r.get('added', 0)} events stored")
    except Exception as e:
        _err("Events failed", e)

    _step(4, "Re-score + archive leaderboard")
    gems = None
    try:
        from pipeline.hidden_gem_scorer import get_engine, score_all_stocks
        from pipeline.leaderboard_archiver import create_table, archive_leaderboard, apply_qual_tiers
        eng = get_engine()
        gems = score_all_stocks(eng)
        create_table(eng)
        result = archive_leaderboard(eng, gems=gems)
        apply_qual_tiers(eng)
        eng.dispose()
        _ok(f"{len(gems)} scored, {result.get('on_board', 0)} on-board")
    except Exception as e:
        _err("Scoring failed", e)

    _step(5, "Filing synopses")
    try:
        from pipeline.synopsis import get_or_generate_synopsis
        from pipeline.hidden_gem_scorer import get_engine as _ge
        import json
        from datetime import timedelta
        eng = _ge()
        cutoff = datetime.now() - timedelta(days=14)
        with eng.connect() as conn:
            rows = conn.execute(text("""
                SELECT f.id, f.symbol, f.filing_type, f.title, f.llm_analysis,
                       ft.trajectory, ft.management_tone, ft.catalysts, ft.risks
                FROM filings f
                JOIN filing_themes ft ON ft.filing_id = f.id
                WHERE f.filing_date >= :c AND ft.narrative_strength >= 0.60
                  AND (f.llm_analysis IS NULL
                       OR (f.llm_analysis::jsonb->>'synopsis') IS NULL)
            """), {"c": cutoff}).fetchall()
        generated = 0
        for r in rows:
            try:
                cats = r[7] if isinstance(r[7], list) else (json.loads(r[7]) if r[7] else [])
                rsks = r[8] if isinstance(r[8], list) else (json.loads(r[8]) if r[8] else [])
                get_or_generate_synopsis(eng, r[0], r[1], r[2], r[3], r[4], r[5], r[6], cats, rsks)
                generated += 1
            except Exception:
                pass
        eng.dispose()
        _ok(f"{generated} synopses generated")
    except Exception as e:
        _err("Synopsis generation failed", e)

    _step(6, "Qual assessment (tier movers)")
    try:
        from pipeline.qual_assessor import run_qual_assessment
        from pipeline.leaderboard_archiver import apply_qual_tiers, create_table as ct
        from pipeline.hidden_gem_scorer import get_engine as _ge
        eng = _ge()
        with eng.connect() as conn:
            movers = conn.execute(text("""
                SELECT today.symbol
                FROM leaderboard_history today
                LEFT JOIN leaderboard_history yest
                    ON yest.symbol = today.symbol
                    AND yest.date = (SELECT MAX(date) FROM leaderboard_history WHERE date < CURRENT_DATE)
                WHERE today.date = CURRENT_DATE
                  AND today.tier IS NOT NULL
                  AND (yest.symbol IS NULL OR yest.tier IS DISTINCT FROM today.tier OR yest.tier IS NULL)
                ORDER BY today.gem_score DESC
            """)).fetchall()
        mover_syms = [r[0] for r in movers]
        if mover_syms:
            _ok(f"Assessing {len(mover_syms)} movers: {', '.join(mover_syms)}")
            run_qual_assessment(symbols=mover_syms, gems=gems or [])
            ct(eng)
            updated = apply_qual_tiers(eng)
            _ok(f"Qual tiers stamped: {updated} rows")
        else:
            _ok("No tier movers — qual assessment skipped")
        eng.dispose()
    except Exception as e:
        _err("Qual assessment failed", e)

    _banner("AFTER-CLOSE REFRESH COMPLETE")


# ── Scheduler setup ───────────────────────────────────────────────────────────

def start_scheduler():
    scheduler = BackgroundScheduler(timezone="UTC")

    scheduler.add_job(
        daily_data_update,
        trigger=CronTrigger(hour=6, minute=0, timezone="UTC"),
        id="daily", name="Daily data update",
        replace_existing=True, misfire_grace_time=3600,
    )
    scheduler.add_job(
        midday_refresh,
        trigger=CronTrigger(day_of_week="0-4", hour=13, minute=0, timezone="UTC"),
        id="midday", name="Mid-day refresh (Mon–Fri)",
        replace_existing=True, misfire_grace_time=1800,
    )
    scheduler.add_job(
        after_close_refresh,
        trigger=CronTrigger(day_of_week="0-4", hour=21, minute=0, timezone="UTC"),
        id="after_close", name="After-close refresh (Mon–Fri)",
        replace_existing=True, misfire_grace_time=1800,
    )

    scheduler.start()
    _banner("CLOUD SCHEDULER STARTED")
    for job in scheduler.get_jobs():
        logger.info(f"  • {job.name} — next run: {job.next_run_time}")
    logger.info("=" * 72)
    return scheduler


if __name__ == "__main__":
    scheduler = start_scheduler()
    import time
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("Scheduler stopped.")
