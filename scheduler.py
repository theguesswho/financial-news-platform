"""
Automated Daily & Weekly Scheduler

All times UTC. US market hours = 13:30–20:00 UTC.

  06:00 daily        — prices, fundamentals, insiders, 8-K events, earnings
                       transcripts, synopsis generation, re-score, archive
  13:00 Mon–Fri      — mid-day: prices + re-score + earnings (pre-open signal)
  21:00 Mon–Fri      — after-close: prices + earnings transcripts + re-score
                       + synopsis (catches same-day calls & closing prices)
  Sunday 18:00       — weekly deep: embeddings, meta-themes, qual assessor,
                       deep dive batch, fundamentals history
"""

import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime

import yfinance as yf
yf.set_tz_cache_location("/tmp/yf_tz_cache")  # avoid SQLite lock conflicts on wake from sleep

from sqlalchemy import text

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# ── Paths & logging ───────────────────────────────────────────────────────────
root = Path(__file__).parent
sys.path.insert(0, str(root))

LOG_FILE = root / "scheduler.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ── Shared helpers ────────────────────────────────────────────────────────────

def _load_tickers() -> list[str]:
    path = root / "config" / "tickers.txt"
    with open(path) as f:
        return [line.strip().upper() for line in f if line.strip()]


def _banner(title: str):
    logger.info("=" * 72)
    logger.info(f"  {title}")
    logger.info("=" * 72)


def _step(n: int, label: str):
    logger.info(f"  Step {n}: {label}…")


def _ok(msg: str):
    logger.info(f"    ✓  {msg}")


def _err(msg: str, exc: Exception):
    logger.error(f"    ✗  {msg}: {exc}", exc_info=True)


# ── Daily task: 6 AM ─────────────────────────────────────────────────────────

def _wait_for_network(timeout=60):
    """Wait until network is reachable — handles post-sleep DNS lag."""
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


def daily_data_update():
    """
    Runs at 6 AM every day.
    1. Fetch latest EOD prices            (yfinance, fast)
    2. Refresh fundamentals               (yfinance, ~10 min for 500 stocks)
    3. Check for new insider trades       (SEC EDGAR Form 4)
    4. Re-score all stocks (hidden gem)   (pure SQL, seconds)
    5. Archive today's scores             (daily_scores table)
    """
    _banner(f"DAILY UPDATE  {datetime.now():%Y-%m-%d %H:%M}")

    from dotenv import load_dotenv
    load_dotenv(override=True)
    _wait_for_network()

    symbols = _load_tickers()
    logger.info(f"  Symbols: {len(symbols)}")

    # ── 1. Prices ─────────────────────────────────────────────────────────────
    _step(1, "EOD prices")
    try:
        from db.session import get_session
        from pipeline.prices import fetch_prices
        session = get_session()
        result = fetch_prices(session, symbols, days=5)   # last 5 trading days is enough daily
        session.close()
        _ok(f"{result.get('added', 0)} price records added")
    except Exception as exc:
        _err("Prices failed", exc)

    # ── 2. Fundamentals ───────────────────────────────────────────────────────
    _step(2, "Fundamentals (Yahoo Finance)")
    try:
        from db.session import get_session
        from pipeline.fundamentals import fetch_fundamentals
        session = get_session()
        result = fetch_fundamentals(session, symbols)
        session.close()
        _ok(f"{result.get('done', 0)} stocks updated, {result.get('errors', 0)} errors")
    except Exception as exc:
        _err("Fundamentals failed", exc)

    # ── 3. Insider trades ─────────────────────────────────────────────────────
    _step(3, "Insider trades (SEC EDGAR Form 4)")
    try:
        from db.session import get_session
        from pipeline.insider import run_insiders
        session = get_session()
        result = run_insiders(session, symbols)
        session.close()
        _ok(f"{result.get('added', 0)} new trades stored")
    except Exception as exc:
        _err("Insider trades failed", exc)

    # ── 3b. Earnings call transcripts (FMP) ──────────────────────────────────
    _step("3b", "Earnings call transcripts (FMP)")
    try:
        from pipeline.earnings_ingestion import run_earnings_ingestion
        result = run_earnings_ingestion(quarters=1, force=False)
        _ok(f"Earnings ingestion done: {result}")
    except Exception as exc:
        _err("Earnings ingestion failed", exc)

    # ── 3c. Material events (8-K filings) ────────────────────────────────────
    _step("3c", "Material events (SEC EDGAR 8-K)")
    try:
        from db.session import get_session
        from pipeline.events import run_events
        session = get_session()
        result = run_events(session, symbols)
        session.close()
        _ok(f"{result.get('added', 0)} new events stored")
    except Exception as exc:
        _err("Events failed", exc)

    # ── 3d. Generate synopses for any new filings lacking one ─────────────────
    _step("3d", "Generate filing synopses (Haiku)")
    try:
        from pipeline.synopsis import get_or_generate_synopsis
        from pipeline.hidden_gem_scorer import get_engine as _ge_s
        import json as _json
        from datetime import timedelta as _td
        _eng_s = _ge_s()
        _cutoff = datetime.now() - _td(days=14)
        with _eng_s.connect() as _conn:
            _rows = _conn.execute(text("""
                SELECT f.id, f.symbol, f.filing_type, f.title, f.llm_analysis,
                       ft.trajectory, ft.management_tone, ft.catalysts, ft.risks
                FROM filings f
                JOIN filing_themes ft ON ft.filing_id = f.id
                WHERE f.filing_date >= :c AND ft.narrative_strength >= 0.60
                  AND (f.llm_analysis IS NULL
                       OR (f.llm_analysis::jsonb->>'synopsis') IS NULL)
            """), {"c": _cutoff}).fetchall()
        _generated = 0
        for _r in _rows:
            try:
                _cats = _r[7] if isinstance(_r[7], list) else (_json.loads(_r[7]) if _r[7] else [])
                _rsks = _r[8] if isinstance(_r[8], list) else (_json.loads(_r[8]) if _r[8] else [])
                get_or_generate_synopsis(_eng_s, _r[0], _r[1], _r[2], _r[3], _r[4], _r[5], _r[6], _cats, _rsks)
                _generated += 1
            except Exception:
                pass
        _eng_s.dispose()
        _ok(f"{_generated} new synopses generated")
    except Exception as exc:
        _err("Synopsis generation failed", exc)

    # ── 4. Re-score + archive leaderboard (single scoring pass) ──────────────
    _step(4, "Re-score hidden gem scores + archive leaderboard")
    _gems = None
    _score_engine = None
    try:
        from pipeline.hidden_gem_scorer import get_engine, score_all_stocks
        from pipeline.leaderboard_archiver import create_table, archive_leaderboard, apply_qual_tiers
        _score_engine = get_engine()
        _gems = score_all_stocks(_score_engine)
        create_table(_score_engine)
        result = archive_leaderboard(_score_engine, gems=_gems)
        updated = apply_qual_tiers(_score_engine)
        _score_engine.dispose()
        _ok(f"{len(_gems)} scored, {result.get('on_board', 0)} on-board, {updated} qual tiers applied")
    except Exception as exc:
        if _score_engine:
            _score_engine.dispose()
        _err("Scoring/leaderboard failed", exc)

    # ── 5. Archive daily scores ───────────────────────────────────────────────
    _step(5, "Archive daily scores")
    try:
        from pipeline.daily_score_archiver import archive_daily_scores
        result = archive_daily_scores()
        _ok(f"{result.get('archived', 0)} scores archived")
    except Exception as exc:
        _err("Score archiving failed", exc)

    _banner("DAILY UPDATE COMPLETE")


# ── Mid-day task: 1 PM UTC (Mon–Fri) ─────────────────────────────────────────

def midday_price_refresh():
    """
    Runs at 1 PM UTC (~9 AM ET, market open) Mon–Fri.
    Lightweight: prices only + re-score + leaderboard snapshot.
    Catches intraday price moves that change gem scores.
    """
    _banner(f"MID-DAY REFRESH  {datetime.now():%Y-%m-%d %H:%M}")

    from dotenv import load_dotenv
    load_dotenv(override=True)
    _wait_for_network()

    symbols = _load_tickers()

    # ── Prices ────────────────────────────────────────────────────────────────
    _step(1, "Intraday prices")
    try:
        from db.session import get_session
        from pipeline.prices import fetch_prices
        session = get_session()
        result = fetch_prices(session, symbols, days=2)
        session.close()
        _ok(f"{result.get('added', 0)} price records added")
    except Exception as exc:
        _err("Prices failed", exc)

    # ── Re-score ──────────────────────────────────────────────────────────────
    _step(2, "Re-score hidden gem scores + archive leaderboard")
    try:
        from pipeline.hidden_gem_scorer import get_engine, score_all_stocks
        from pipeline.leaderboard_archiver import create_table, archive_leaderboard, apply_qual_tiers
        _eng_mid = get_engine()
        _gems_mid = score_all_stocks(_eng_mid)
        create_table(_eng_mid)
        _res_mid = archive_leaderboard(_eng_mid, gems=_gems_mid)
        apply_qual_tiers(_eng_mid)
        _eng_mid.dispose()
        _ok(f"{len(_gems_mid)} scored, {_res_mid.get('on_board', 0)} on-board")
    except Exception as exc:
        _err("Hidden gem scoring failed", exc)

    # ── Earnings (same-day transcripts) ───────────────────────────────────────
    _step(3, "Earnings transcripts (same-day)")
    try:
        from pipeline.earnings_ingestion import run_earnings_ingestion
        result = run_earnings_ingestion(quarters=1, force=False)
        _ok(f"Earnings ingestion done: {result}")
    except Exception as exc:
        _err("Earnings ingestion failed", exc)

    _banner("MID-DAY REFRESH COMPLETE")


# ── After-close task: 9 PM UTC (Mon–Fri) ─────────────────────────────────────

def after_close_refresh():
    """
    Runs at 9 PM UTC (~5 PM ET, after US market close) Mon–Fri.
    Fetches closing prices, pulls any same-day earnings transcripts,
    re-scores, and generates synopses for new filings.
    """
    _banner(f"AFTER-CLOSE REFRESH  {datetime.now():%Y-%m-%d %H:%M}")

    from dotenv import load_dotenv
    load_dotenv(override=True)
    _wait_for_network()

    symbols = _load_tickers()

    # ── Closing prices ────────────────────────────────────────────────────────
    _step(1, "Closing prices")
    try:
        from db.session import get_session
        from pipeline.prices import fetch_prices
        session = get_session()
        result = fetch_prices(session, symbols, days=2)
        session.close()
        _ok(f"{result.get('added', 0)} price records added")
    except Exception as exc:
        _err("Prices failed", exc)

    # ── Same-day earnings transcripts ─────────────────────────────────────────
    _step(2, "Earnings transcripts (same-day)")
    try:
        from pipeline.earnings_ingestion import run_earnings_ingestion
        result = run_earnings_ingestion(quarters=1, force=False)
        _ok(f"Earnings ingestion done: {result}")
    except Exception as exc:
        _err("Earnings ingestion failed", exc)

    # ── 8-K material events ───────────────────────────────────────────────────
    _step(3, "Material events (SEC EDGAR 8-K)")
    try:
        from db.session import get_session
        from pipeline.events import run_events
        session = get_session()
        result = run_events(session, symbols)
        session.close()
        _ok(f"{result.get('added', 0)} new events stored")
    except Exception as exc:
        _err("Events failed", exc)

    # ── Re-score + archive leaderboard (single scoring pass) ─────────────────
    _step(4, "Re-score hidden gem scores + archive leaderboard")
    _gems_ac = None
    _eng_ac  = None
    try:
        from pipeline.hidden_gem_scorer import get_engine, score_all_stocks
        from pipeline.leaderboard_archiver import create_table, archive_leaderboard, apply_qual_tiers
        _eng_ac  = get_engine()
        _gems_ac = score_all_stocks(_eng_ac)
        create_table(_eng_ac)
        _res_ac  = archive_leaderboard(_eng_ac, gems=_gems_ac)
        apply_qual_tiers(_eng_ac)
        _eng_ac.dispose()
        _ok(f"{len(_gems_ac)} scored, {_res_ac.get('on_board', 0)} on-board")
    except Exception as exc:
        if _eng_ac: _eng_ac.dispose()
        _err("Hidden gem scoring failed", exc)

    # ── Synopsis for new filings ──────────────────────────────────────────────
    _step(5, "Generate filing synopses (Haiku)")
    try:
        from pipeline.synopsis import get_or_generate_synopsis
        from pipeline.hidden_gem_scorer import get_engine as _ge_s
        import json as _json
        from datetime import timedelta as _td
        _eng_s = _ge_s()
        _cutoff = datetime.now() - _td(days=14)
        with _eng_s.connect() as _conn:
            _rows = _conn.execute(text("""
                SELECT f.id, f.symbol, f.filing_type, f.title, f.llm_analysis,
                       ft.trajectory, ft.management_tone, ft.catalysts, ft.risks
                FROM filings f
                JOIN filing_themes ft ON ft.filing_id = f.id
                WHERE f.filing_date >= :c AND ft.narrative_strength >= 0.60
                  AND (f.llm_analysis IS NULL
                       OR (f.llm_analysis::jsonb->>'synopsis') IS NULL)
            """), {"c": _cutoff}).fetchall()
        _generated = 0
        for _r in _rows:
            try:
                _cats = _r[7] if isinstance(_r[7], list) else (_json.loads(_r[7]) if _r[7] else [])
                _rsks = _r[8] if isinstance(_r[8], list) else (_json.loads(_r[8]) if _r[8] else [])
                get_or_generate_synopsis(_eng_s, _r[0], _r[1], _r[2], _r[3], _r[4], _r[5], _r[6], _cats, _rsks)
                _generated += 1
            except Exception:
                pass
        _eng_s.dispose()
        _ok(f"{_generated} new synopses generated")
    except Exception as exc:
        _err("Synopsis generation failed", exc)

    # ── Targeted qual assessment — new entrants + tier movers ────────────────
    # Uses pre-computed _gems_ac from step 4 — no redundant re-score.
    _step(6, "Qual assessment (new entrants + tier movers)")
    try:
        from pipeline.qual_assessor import run_qual_assessment
        from pipeline.leaderboard_archiver import apply_qual_tiers, create_table as _ct_qa
        from pipeline.hidden_gem_scorer import get_engine as _ge_qa
        _eng_qa = _ge_qa()

        # Stocks newly on the leaderboard or whose raw tier changed since yesterday
        with _eng_qa.connect() as _conn:
            _movers = _conn.execute(text("""
                SELECT today.symbol
                FROM leaderboard_history today
                LEFT JOIN leaderboard_history yest
                    ON yest.symbol = today.symbol
                    AND yest.date = (
                        SELECT MAX(date) FROM leaderboard_history
                        WHERE date < CURRENT_DATE
                    )
                WHERE today.date = CURRENT_DATE
                  AND today.tier IS NOT NULL
                  AND (
                      yest.symbol IS NULL
                      OR yest.tier IS DISTINCT FROM today.tier
                      OR yest.tier IS NULL
                  )
                ORDER BY today.gem_score DESC
            """)).fetchall()
        _mover_syms = [r[0] for r in _movers]

        if _mover_syms:
            _ok(f"{len(_mover_syms)} movers to assess: {', '.join(_mover_syms)}")
            # Pass pre-computed gems — single scoring pass for the whole day
            run_qual_assessment(symbols=_mover_syms, gems=_gems_ac or [])
            _ct_qa(_eng_qa)
            _updated_qa = apply_qual_tiers(_eng_qa)
            _ok(f"Qual tiers stamped for {_updated_qa} rows")
        else:
            _ok("No tier movers today — qual assessment skipped")

        _eng_qa.dispose()
    except Exception as exc:
        _err("Daily qual assessment failed", exc)

    _banner("AFTER-CLOSE REFRESH COMPLETE")


# ── Weekly task: Sunday 6 PM UTC ──────────────────────────────────────────────

def weekly_deep_refresh():
    """
    Runs at 6 PM every Sunday.
    1. Rebuild filing-theme embeddings        (sentence-transformers)
    2. Rebuild meta-theme taxonomy            (Claude)
    3. Re-score stock-theme alignments        (Claude)
    4. Re-run qual assessor on top 25 stocks  (Claude)
    5. Snapshot fundamentals history          (yfinance, free)
    Note: earnings ingestion now runs daily — no need to repeat here.
    """
    _banner(f"WEEKLY DEEP REFRESH  {datetime.now():%Y-%m-%d %H:%M}")

    from dotenv import load_dotenv
    load_dotenv(override=True)

    # ── 1. Rebuild embeddings ─────────────────────────────────────────────────
    _step(1, "Rebuild filing-theme embeddings")
    try:
        from pipeline.embedding_builder import run_embedding_build
        run_embedding_build(force=False)   # skips already-embedded filings
        _ok("Embeddings rebuilt")
    except Exception as exc:
        _err("Embedding build failed", exc)

    # ── 3. Rebuild meta-theme taxonomy ────────────────────────────────────────
    _step(3, "Rebuild meta-theme taxonomy (Claude)")
    try:
        from pipeline.meta_theme_builder import run_meta_theme_build
        run_meta_theme_build()
        _ok("Meta-themes rebuilt")
    except Exception as exc:
        _err("Meta-theme build failed", exc)

    # ── 4. Re-score stock-theme alignments ────────────────────────────────────
    # alignment scoring is part of the meta_theme_builder run above;
    # log separately so it's visible in the schedule output
    _ok("Stock-theme alignments re-scored (part of Step 3)")

    # ── 5. Qual assessor ─────────────────────────────────────────────────────
    _step(4, "Qual assessor — all leaderboard stocks (Claude)")
    try:
        from pipeline.qual_assessor import run_qual_assessment
        from pipeline.leaderboard_archiver import create_table as _ct_w, archive_leaderboard as _al_w, apply_qual_tiers as _aqt_w
        from pipeline.hidden_gem_scorer import get_engine as _ge_w
        _eng_w = _ge_w()
        _ct_w(_eng_w)
        _al_w(_eng_w)
        run_qual_assessment(top_n=25)
        updated_w = _aqt_w(_eng_w)
        _eng_w.dispose()
        _ok(f"Qual assessment complete, {updated_w} qual tiers applied to leaderboard")
    except Exception as exc:
        _err("Qual assessment failed", exc)

    # ── 5b. Deep dive batch (Buffett tiers) ──────────────────────────────────
    _step("5b", "Deep dive batch — Buffett tier for all leaderboard stocks")
    try:
        from pipeline.deep_dive_batch import run_batch
        from pipeline.hidden_gem_scorer import get_engine as _ge2
        _eng2 = _ge2()
        result = run_batch(_eng2, force=False)
        _eng2.dispose()
        _ok(f"{result.get('generated',0)} memos, Buffett Stocks: {result.get('buffett',[])}")
    except Exception as exc:
        _err("Deep dive batch failed", exc)

    # ── 6. Snapshot fundamentals history ─────────────────────────────────────
    _step(5, "Snapshot fundamentals history (yfinance)")
    try:
        from pipeline.fundamentals_history import (
            backfill_from_existing_quarterly_trends,
            backfill_annual_from_yfinance,
            create_table,
        )
        from pathlib import Path
        engine_h = __import__("pipeline.hidden_gem_scorer", fromlist=["get_engine"]).get_engine()
        tickers_path = Path(__file__).parent / "config" / "tickers.txt"
        with open(tickers_path) as fh:
            syms = [l.strip().upper() for l in fh if l.strip()]
        create_table(engine_h)
        backfill_from_existing_quarterly_trends(engine_h)
        backfill_annual_from_yfinance(engine_h, syms)
        _ok("Fundamentals history updated")
    except Exception as exc:
        _err("Fundamentals history failed", exc)

    _banner("WEEKLY DEEP REFRESH COMPLETE")


# ── Scheduler setup ───────────────────────────────────────────────────────────

def start_scheduler():
    scheduler = BackgroundScheduler(timezone="UTC")

    # 6 AM UTC daily
    scheduler.add_job(
        daily_data_update,
        trigger=CronTrigger(hour=6, minute=0, timezone="UTC"),
        id="daily_data_update",
        name="Daily data update (prices, fundamentals, insiders, scores)",
        replace_existing=True,
        misfire_grace_time=3600,   # run up to 1 h late if the process was down
    )

    # 1 PM UTC Mon–Fri — mid-day price refresh + re-score (~9 AM ET)
    scheduler.add_job(
        midday_price_refresh,
        trigger=CronTrigger(day_of_week="0-4", hour=13, minute=0, timezone="UTC"),
        id="midday_price_refresh",
        name="Mid-day price refresh + re-score (Mon–Fri)",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    # 9 PM UTC Mon–Fri — after US market close
    scheduler.add_job(
        after_close_refresh,
        trigger=CronTrigger(day_of_week="0-4", hour=21, minute=0, timezone="UTC"),
        id="after_close_refresh",
        name="After-close refresh (prices, earnings, events, re-score)",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    # 6 PM UTC every Sunday (day_of_week=6) — evening so laptop is likely on
    scheduler.add_job(
        weekly_deep_refresh,
        trigger=CronTrigger(day_of_week=6, hour=18, minute=0, timezone="UTC"),
        id="weekly_deep_refresh",
        name="Weekly deep refresh (transcripts, embeddings, themes, qual)",
        replace_existing=True,
        misfire_grace_time=14400,  # run up to 4 h late if machine woke after schedule
    )

    scheduler.start()

    _banner("SCHEDULER STARTED")
    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        logger.info(f"  • {job.name}")
        logger.info(f"    next run: {next_run}")
    logger.info("=" * 72)

    return scheduler


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Financial News Platform Scheduler")
    parser.add_argument(
        "--run-now",
        choices=["daily", "midday", "close", "weekly"],
        help="Immediately run a task instead of starting the scheduler",
    )
    args = parser.parse_args()

    if args.run_now == "daily":
        logger.info("Running daily task now (--run-now daily)…")
        daily_data_update()
    elif args.run_now == "midday":
        logger.info("Running mid-day refresh now (--run-now midday)…")
        midday_price_refresh()
    elif args.run_now == "close":
        logger.info("Running after-close refresh now (--run-now close)…")
        after_close_refresh()
    elif args.run_now == "weekly":
        logger.info("Running weekly task now (--run-now weekly)…")
        weekly_deep_refresh()
    else:
        scheduler = start_scheduler()
        try:
            logger.info("Scheduler running. Press Ctrl+C to exit.")
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Shutting down scheduler…")
            scheduler.shutdown()
            logger.info("Done.")
