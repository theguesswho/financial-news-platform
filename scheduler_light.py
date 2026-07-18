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


# ── Qual sweep (shared by daily + after-close jobs) ──────────────────────────

def _qual_sweep(gems=None):
    """
    Assess (a) tier movers since the previous snapshot and (b) any Buy/Strong Buy
    stock never assessed. Uses the latest leaderboard snapshot — not CURRENT_DATE —
    so missed runs self-heal on the next pass regardless of which day it fires.
    """
    from pipeline.qual_assessor import run_qual_assessment
    from pipeline.leaderboard_archiver import apply_qual_tiers, create_table
    from pipeline.hidden_gem_scorer import get_engine
    eng = get_engine()
    with eng.connect() as conn:
        # Tier movers — skip flaps (tier changed on a <0.015 score wiggle at a
        # boundary) and anything already assessed in the last 18h (the sweep
        # runs twice a day against the same prior snapshot).
        movers = conn.execute(text("""
            SELECT today.symbol
            FROM leaderboard_history today
            LEFT JOIN leaderboard_history yest
                ON yest.symbol = today.symbol
                AND yest.date = (SELECT MAX(date) FROM leaderboard_history
                                 WHERE date < (SELECT MAX(date) FROM leaderboard_history))
            WHERE today.date = (SELECT MAX(date) FROM leaderboard_history)
              AND today.tier IS NOT NULL
              AND (yest.symbol IS NULL
                   OR (yest.tier IS DISTINCT FROM today.tier
                       AND (yest.gem_score IS NULL
                            OR ABS(today.gem_score - yest.gem_score) >= 0.015)))
              AND NOT EXISTS (
                  SELECT 1 FROM qual_assessments qa
                  WHERE qa.symbol = today.symbol
                    AND qa.assessed_at > NOW() - INTERVAL '18 hours')
            ORDER BY today.gem_score DESC
        """)).fetchall()
        # Any stock on the board (incl. Watch) never assessed — one-time cost per stock
        unassessed = conn.execute(text("""
            SELECT lh.symbol
            FROM leaderboard_history lh
            LEFT JOIN qual_assessments qa ON qa.symbol = lh.symbol
            WHERE lh.date = (SELECT MAX(date) FROM leaderboard_history)
              AND lh.tier IS NOT NULL
              AND qa.symbol IS NULL
            ORDER BY lh.gem_score DESC
        """)).fetchall()

    to_assess = list(dict.fromkeys([r[0] for r in movers] + [r[0] for r in unassessed]))
    if to_assess:
        _ok(f"Assessing {len(to_assess)} stocks: {', '.join(to_assess)}")
        # gems=None makes the assessor re-score itself; never pass [] (matches nothing)
        run_qual_assessment(symbols=to_assess, gems=gems if gems else None)
        create_table(eng)
        updated = apply_qual_tiers(eng)
        _ok(f"Qual tiers stamped: {updated} rows")
    else:
        _ok("No stocks need qual assessment")
    eng.dispose()


# ── Universe onboarding queue ─────────────────────────────────────────────────
# Heavy backfills must run HERE, next to the DB — never from a laptop through
# the proxy. Enqueue a chunk by inserting into onboarding_queue; the next
# scheduled run picks it up (one per run) and stores the readiness report.

def _process_onboarding_queue():
    import json as _json
    from pipeline.hidden_gem_scorer import get_engine
    eng = get_engine()
    with eng.connect() as conn:
        row = conn.execute(text("""
            SELECT id, chunk_path FROM onboarding_queue
            WHERE status = 'pending' ORDER BY id LIMIT 1
        """)).fetchone()
    if not row:
        eng.dispose()
        return
    qid, chunk = row
    _banner(f"ONBOARDING QUEUE — {chunk}")
    with eng.begin() as conn:
        conn.execute(text("UPDATE onboarding_queue SET status='running' WHERE id=:i"), {"i": qid})
    try:
        from pipeline.onboard_universe import onboard
        rep = onboard(chunk, apply=False)
        with eng.begin() as conn:
            conn.execute(text("""
                UPDATE onboarding_queue SET status='done', finished_at=NOW(),
                    report=:r WHERE id=:i
            """), {"r": _json.dumps({"ready": rep["ready"], "partial": rep["partial"],
                                      "exposed": rep["exposed_count"]}), "i": qid})
        _ok(f"Onboarding done: {len(rep['ready'])} ready, {len(rep['partial'])} partial")
    except Exception as e:
        _err("Onboarding failed", e)
        with eng.begin() as conn:
            conn.execute(text(
                "UPDATE onboarding_queue SET status='failed', finished_at=NOW() WHERE id=:i"),
                {"i": qid})
    eng.dispose()


# ── Daily brief (self-healing: no-op if today's brief already exists) ────────

def _ensure_brief():
    from pipeline.brief import get_or_generate_brief
    from db.session import get_session
    s = get_session()
    try:
        brief = get_or_generate_brief(s)
        top = (brief.get("top_signal") or {}).get("title", "")
        _ok(f"Daily brief ready — top signal: {top}")
    finally:
        s.close()


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
        from pipeline.fundamentals import fetch_fundamentals
        from db.session import get_session
        s = get_session()
        r = fetch_fundamentals(s, symbols)
        s.close()
        _ok(f"{r.get('updated', 0)} updated")
    except Exception as e:
        _err("Fundamentals failed", e)

    _step(3, "Insider trades (SEC Form 4)")
    try:
        from db.session import get_session
        from pipeline.insider import run_insiders
        s = get_session()
        r = run_insiders(s, symbols)
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

    _step("4b", "Narrative theme extraction (catch-up)")
    try:
        from pipeline.narrative_extractor import run_extraction
        run_extraction(limit=30)
        _ok("Narrative extraction done")
    except Exception as e:
        _err("Narrative extraction failed", e)

    _step(5, "Re-score + archive leaderboard")
    engine = None
    gems = None
    try:
        engine, gems = _score_and_archive()
    except Exception as e:
        _err("Scoring failed", e)

    _step("5c", "Theme valuation gaps (Dell detector)")
    try:
        from pipeline.theme_valuation_gap import compute_theme_gaps
        from pipeline.hidden_gem_scorer import get_engine as _ge
        eng = _ge()
        r = compute_theme_gaps(eng)
        eng.dispose()
        _ok(f"{r['pairs']} theme-gap pairs across {r['stocks']} stocks")
    except Exception as e:
        _err("Theme valuation gaps failed", e)

    _step(6, "Backfill missing 8-K classifications")
    try:
        import json, time as _time
        from pipeline.events import _classify_8k
        from pipeline.hidden_gem_scorer import get_engine as _ge
        eng = _ge()
        with eng.connect() as conn:
            unclassified = conn.execute(text("""
                SELECT id, symbol, content FROM filings
                WHERE filing_type IN ('8-K','8-K/A')
                AND (llm_analysis IS NULL
                     OR llm_analysis::jsonb->>'impact' IS NULL
                     OR llm_analysis::jsonb->>'headline' IS NULL)
                ORDER BY filing_date DESC LIMIT 50
            """)).fetchall()
        fixed = 0
        for fid, sym, content in unclassified:
            try:
                result = _classify_8k(sym, content or "", "")
                with eng.begin() as conn:
                    conn.execute(text("""
                        UPDATE filings SET llm_analysis=:a, event_type=:et,
                        title=:hl, sentiment_score=:sc WHERE id=:id
                    """), {"a": json.dumps(result), "et": result["event_type"],
                          "hl": result["headline"], "sc": result.get("score", 0), "id": fid})
                fixed += 1
                _time.sleep(0.3)
            except Exception:
                pass
        eng.dispose()
        _ok(f"{fixed} 8-K filings backfilled")
    except Exception as e:
        _err("8-K backfill failed", e)

    _step(7, "Archive daily scores")
    try:
        from pipeline.daily_score_archiver import archive_daily_scores
        r = archive_daily_scores()
        _ok(f"{r.get('stored', 0)} scores archived")
    except Exception as e:
        _err("Daily score archive failed", e)

    _step(8, "Qual assessment sweep (movers + unassessed Buy/Strong Buy)")
    try:
        _qual_sweep(gems=gems)
    except Exception as e:
        _err("Qual sweep failed", e)

    _step("8b", "Track record — open weekly lots (no-op unless new week)")
    try:
        from pipeline.track_record import open_weekly_lots
        from pipeline.hidden_gem_scorer import get_engine as _ge
        eng = _ge()
        r = open_weekly_lots(eng)
        eng.dispose()
        _ok(f"Track record: {r}")
    except Exception as e:
        _err("Track record failed", e)

    _step("8c", "Data freshness sentinel")
    try:
        from pipeline.freshness_sentinel import run_sentinel
        from pipeline.hidden_gem_scorer import get_engine as _ge
        eng = _ge()
        v = run_sentinel(eng)
        eng.dispose()
        if v:
            _err("FRESHNESS VIOLATIONS", v)
        else:
            _ok("All sources fresh")
    except Exception as e:
        _err("Freshness sentinel failed", e)

    _step(9, "Daily brief")
    try:
        _ensure_brief()
    except Exception as e:
        _err("Daily brief failed", e)

    _step(10, "Filing synopses")
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
                  AND f.filing_type NOT IN ('8-K','8-K/A')
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

    try:
        _process_onboarding_queue()
    except Exception as e:
        _err("Onboarding queue failed", e)

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

    _step(4, "Daily brief (catch-up if 6AM run missed it)")
    try:
        _ensure_brief()
    except Exception as e:
        _err("Daily brief failed", e)

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

    _step("3b", "10-K/10-Q filings (SEC EDGAR)")
    try:
        from db.session import get_session
        from pipeline.ingestion import run_ingestion
        s = get_session()
        r = run_ingestion(s, symbols)
        s.close()
        _ok(f"10-K/Q ingestion: {r}")
    except Exception as e:
        _err("10-K/Q ingestion failed", e)

    _step("3c", "Narrative theme extraction (new filings)")
    try:
        from pipeline.narrative_extractor import run_extraction
        run_extraction(limit=30)
        _ok("Narrative extraction done")
    except Exception as e:
        _err("Narrative extraction failed", e)

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
                  AND f.filing_type NOT IN ('8-K','8-K/A')
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

    _step(6, "Qual assessment (tier movers + unassessed Buy/Strong Buy)")
    try:
        _qual_sweep(gems=gems)
    except Exception as e:
        _err("Qual assessment failed", e)

    _step(7, "Daily brief (catch-up if earlier runs missed it)")
    try:
        _ensure_brief()
    except Exception as e:
        _err("Daily brief failed", e)

    _banner("AFTER-CLOSE REFRESH COMPLETE")


# ── Weekly Sunday 6 PM UTC ───────────────────────────────────────────────────

def weekly_deep_refresh():
    _banner(f"WEEKLY DEEP REFRESH  {datetime.now():%Y-%m-%d %H:%M}")
    _wait_for_network()
    symbols = _load_tickers()

    _step(1, "Full fundamentals refresh")
    try:
        from pipeline.fundamentals import fetch_fundamentals
        from db.session import get_session
        s = get_session()
        r = fetch_fundamentals(s, symbols)
        s.close()
        _ok(f"{r.get('updated', 0)} updated")
    except Exception as e:
        _err("Fundamentals failed", e)

    _step(2, "Re-score + archive leaderboard")
    gems = None
    try:
        from pipeline.hidden_gem_scorer import get_engine, score_all_stocks
        from pipeline.leaderboard_archiver import create_table, archive_leaderboard, apply_qual_tiers
        eng = get_engine()
        gems = score_all_stocks(eng)
        create_table(eng)
        archive_leaderboard(eng, gems=gems)
        apply_qual_tiers(eng)
        eng.dispose()
        _ok(f"{len(gems)} scored")
    except Exception as e:
        _err("Scoring failed", e)

    _step(3, "Full qual assessment (all scored stocks)")
    try:
        from pipeline.qual_assessor import run_qual_assessment
        from pipeline.leaderboard_archiver import apply_qual_tiers, create_table as ct
        from pipeline.hidden_gem_scorer import get_engine as _ge
        run_qual_assessment(gems=gems or [])
        eng = _ge()
        ct(eng)
        apply_qual_tiers(eng)
        eng.dispose()
        _ok("Full qual assessment complete")
    except Exception as e:
        _err("Qual assessment failed", e)

    _step(4, "Deep dives (top stocks)")
    try:
        from pipeline.deep_dive import generate_deep_dive
        from pipeline.hidden_gem_scorer import get_engine as _ge
        eng = _ge()
        with eng.connect() as conn:
            rows = conn.execute(text("""
                SELECT symbol FROM leaderboard_history
                WHERE date = CURRENT_DATE AND tier IN ('Strong Buy', 'Buy')
                ORDER BY gem_score DESC LIMIT 20
            """)).fetchall()
        top_symbols = [r[0] for r in rows]
        eng.dispose()
        for sym in top_symbols:
            try:
                generate_deep_dive(sym, force=False)
                _ok(f"Deep dive: {sym}")
            except Exception as ex:
                _err(f"Deep dive {sym}", ex)
    except Exception as e:
        _err("Deep dives failed", e)

    _step(5, "Embeddings refresh")
    try:
        from pipeline.embedding_builder import run_embedding_build
        r = run_embedding_build()
        _ok(f"Embeddings done: {r}")
    except Exception as e:
        _err("Embeddings failed", e)

    _step("5b", "Meta-theme clustering + stock alignment (the meta-narrative)")
    try:
        from pipeline.meta_theme_builder import run_meta_theme_build
        run_meta_theme_build()
        _ok("Meta-narrative rebuilt")
    except Exception as e:
        _err("Meta-theme build failed", e)

    _step("5d", "Narrative exposure scoring (the brain — LLM-judged, cited)")
    try:
        from pipeline.narrative_exposure import run_exposure_scoring
        from pipeline.hidden_gem_scorer import get_engine as _ge
        eng = _ge()
        r = run_exposure_scoring(eng)
        eng.dispose()
        _ok(f"Exposures: {r}")
    except Exception as e:
        _err("Narrative exposure scoring failed", e)

    _step("5e", "Narrative lifecycle (candidates, promotions, falsification)")
    try:
        from pipeline.narrative_lifecycle import run_lifecycle
        run_lifecycle()
        _ok("Lifecycle evaluated")
    except Exception as e:
        _err("Narrative lifecycle failed", e)

    _step(6, "Historical metrics refresh (FMP quarterly)")
    try:
        from pipeline.fmp_historical import fetch_historical_metrics
        from db.session import get_session
        s = get_session()
        r = fetch_historical_metrics(s, symbols)
        s.close()
        _ok(f"Historical metrics: {r}")
    except Exception as e:
        _err("Historical metrics failed", e)

    _step(7, "Fundamentals history refresh (annual + quarterly)")
    try:
        from pipeline.fundamentals_history import run_history_backfill
        from pipeline.hidden_gem_scorer import get_engine as _ge
        eng = _ge()
        run_history_backfill(eng)
        eng.dispose()
        _ok("Fundamentals history refreshed")
    except Exception as e:
        _err("Fundamentals history failed", e)

    try:
        _process_onboarding_queue()
    except Exception as e:
        _err("Onboarding queue failed", e)

    _banner("WEEKLY DEEP REFRESH COMPLETE")


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

    scheduler.add_job(
        weekly_deep_refresh,
        trigger=CronTrigger(day_of_week="6", hour=18, minute=0, timezone="UTC"),
        id="weekly", name="Weekly deep refresh (Sunday)",
        replace_existing=True, misfire_grace_time=7200,
    )

    scheduler.start()
    _banner("CLOUD SCHEDULER STARTED")
    for job in scheduler.get_jobs():
        logger.info(f"  • {job.name} — next run: {job.next_run_time}")
    logger.info("=" * 72)
    return scheduler


if __name__ == "__main__":
    scheduler = start_scheduler()

    # Drain the onboarding queue at startup too — a deploy shouldn't make a
    # pending chunk wait for the next cron slot. Separate thread so scheduled
    # jobs fire on time regardless. status='running' guard prevents overlap.
    import threading
    threading.Thread(target=_process_onboarding_queue, name="onboarding").start()

    import time
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("Scheduler stopped.")
