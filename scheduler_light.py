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
    Trigger-based, UNIVERSE-WIDE qual sweep (user design 2026-07-25): a new
    assessment is warranted only when new information lands. Triggers, each
    vs the stock's LAST assessment (18h cooldown applies to all):
      earnings  — new earnings call / earnings 8-K since assessed_at (always)
      score     — |gem_now − gem_at_assessment| >= 0.05 (half a tier band)
      narrative — |E_now − E_at_assessment| >= 0.10
      new       — on-board stock never assessed (baseline covers the rest)
    The assessor is told WHY it's being asked and must open its rationale by
    saying whether the event changes the thesis or is noise.
    """
    from pipeline.qual_assessor import run_qual_assessment
    from pipeline.leaderboard_archiver import apply_qual_tiers, create_table
    from pipeline.hidden_gem_scorer import get_engine
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text(
            "ALTER TABLE qual_assessments ADD COLUMN IF NOT EXISTS narrative_score NUMERIC(10,4)"))
    with eng.connect() as conn:
        rows = conn.execute(text("""
            WITH latest AS (
                SELECT * FROM leaderboard_history
                WHERE date = (SELECT MAX(date) FROM leaderboard_history)
            )
            SELECT l.symbol,
                   CASE
                     WHEN qa.symbol IS NULL THEN 'first assessment: new to the board'
                     WHEN ov.promoted_since IS NOT NULL THEN
                       'this stock was PROMOTED to ' || ov.tier || ' by the narrative-override mechanism on ' ||
                       ov.promoted_since::date || ', AFTER your last assessment on ' || qa.assessed_at::date ||
                       '. The override thesis (evaluate it on its merits): ' || ov.reason
                     WHEN ef.fdate IS NOT NULL THEN
                       'new earnings data (' || ef.ftype || ' filed ' || ef.fdate ||
                       ') since your last assessment on ' || qa.assessed_at::date ||
                       COALESCE('. MARKET REACTION: the stock moved ' ||
                           ROUND(px.chg_pct, 1) || '% on the latest session — ' ||
                           'adjudicate whether the market sees something the thesis misses', '')
                     WHEN ABS(l.gem_score - qa.gem_score) >= 0.05 THEN
                       'the overall score moved ' || ROUND(qa.gem_score*10,1) || ' -> ' ||
                       ROUND(l.gem_score*10,1) || ' (10-point scale) since your last assessment on ' ||
                       qa.assessed_at::date
                     ELSE
                       'narrative exposure moved ' || ROUND(qa.narrative_score*10,1) ||
                       ' -> ' || ROUND(l.narrative_score*10,1) || ' (10-point scale)' ||
                       ' since your last assessment on ' || qa.assessed_at::date
                   END AS reason
            FROM latest l
            LEFT JOIN qual_assessments qa ON qa.symbol = l.symbol
            LEFT JOIN LATERAL (
                SELECT no2.assessed_at AS promoted_since, no2.adjusted_tier AS tier,
                       LEFT(COALESCE(no2.rationale,'') || ' Evidence: ' ||
                            COALESCE(no2.evidence,''), 600) AS reason
                FROM narrative_overrides no2
                WHERE no2.symbol = l.symbol AND no2.promoted
                  AND no2.assessed_at > qa.assessed_at
            ) ov ON qa.symbol IS NOT NULL AND COALESCE(l.qual_promoted, FALSE)
            LEFT JOIN LATERAL (
                -- created_at (ingestion time), NOT filing_date: transcripts are
                -- backdated to the call date, so a transcript arriving days
                -- after the 8-K-triggered assessment must RE-fire the trigger
                -- (GDDY case 2026-07-31).
                SELECT f.filing_type AS ftype, f.filing_date::date AS fdate
                FROM filings f
                WHERE f.symbol = l.symbol
                  AND (f.filing_type = 'EARN_CALL'
                       OR (f.filing_type = '8-K' AND f.event_type = 'EARNINGS'))
                  AND f.created_at > qa.assessed_at
                  AND f.filing_date > NOW() - INTERVAL '14 days'
                ORDER BY f.created_at DESC LIMIT 1
            ) ef ON qa.symbol IS NOT NULL
            LEFT JOIN LATERAL (
                SELECT ROUND(100 * (a.close / NULLIF(b.close, 0) - 1), 1) AS chg_pct
                FROM (SELECT close FROM eod_prices WHERE symbol = l.symbol
                      ORDER BY date DESC LIMIT 1) a,
                     (SELECT close FROM eod_prices WHERE symbol = l.symbol
                      ORDER BY date DESC OFFSET 1 LIMIT 1) b
            ) px ON ef.fdate IS NOT NULL
            WHERE (qa.assessed_at IS NULL OR qa.assessed_at < NOW() - INTERVAL '18 hours')
              AND (
                    (qa.symbol IS NULL AND (l.tier IS NOT NULL OR COALESCE(l.qual_promoted, FALSE)))
                 OR ov.promoted_since IS NOT NULL
                 OR ef.fdate IS NOT NULL
                 OR ABS(l.gem_score - COALESCE(qa.gem_score, l.gem_score)) >= 0.05
                 OR (qa.narrative_score IS NOT NULL
                     AND ABS(l.narrative_score - qa.narrative_score) >= 0.10)
              )
            ORDER BY l.gem_score DESC
            LIMIT 80
        """)).fetchall()

    to_assess = [r[0] for r in rows]
    trig = {r[0]: r[1] for r in rows}
    if to_assess:
        _ok(f"Assessing {len(to_assess)} triggered stocks: {', '.join(to_assess[:15])}"
            + ("…" if len(to_assess) > 15 else ""))
        # gems=None makes the assessor re-score itself; never pass [] (matches nothing)
        run_qual_assessment(symbols=to_assess, gems=gems if gems else None,
                            triggers=trig)
        create_table(eng)
        updated = apply_qual_tiers(eng)
        _ok(f"Qual tiers stamped: {updated} rows")
    else:
        _ok("No stocks need qual assessment")

    # Narrative-blind override sweep (user-approved 2026-07-21): quant-qualified
    # stocks the 19-narrative library can't see get a bounded qual promotion.
    # Runs AFTER apply_qual_tiers so its stamps are never overwritten this cycle.
    # LLM calls only for new/stale candidates (7-day reuse) — cheap daily.
    try:
        from pipeline.narrative_override import run_narrative_override
        r = run_narrative_override(eng, gems=gems if gems else None)
        _ok(f"Narrative override: {r}")
    except Exception as e:
        logger.error(f"    ✗  Narrative override failed: {e}")
    eng.dispose()


# ── Universe onboarding queue ─────────────────────────────────────────────────
# Heavy backfills must run HERE, next to the DB — never from a laptop through
# the proxy. Enqueue a chunk by inserting into onboarding_queue; the next
# scheduled run picks it up (one per run) and stores the readiness report.

def _process_job_queue():
    """
    Generic heavy-job runner — jobs execute ON RAILWAY, next to the DB,
    because the proxy kills long connections from outside the datacenter
    (root cause of every 'server closed the connection' failure to date).
    Enqueue: INSERT INTO job_queue (job_type, payload) VALUES
      ('verify_universe', NULL) | ('update_pass', NULL) |
      ('qual_full_sweep', NULL) — drained one per slot like onboarding.
    Failures store the full error text in report; never empty again.
    """
    import json as _json, traceback as _tb
    from pipeline.hidden_gem_scorer import get_engine
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS job_queue (
                id SERIAL PRIMARY KEY,
                job_type VARCHAR(40) NOT NULL,
                payload TEXT,
                status VARCHAR(12) DEFAULT 'pending',
                report TEXT,
                requested_at TIMESTAMP DEFAULT NOW(),
                finished_at TIMESTAMP
            )"""))
    with eng.connect() as conn:
        row = conn.execute(text("""
            SELECT id, job_type, payload FROM job_queue
            WHERE status = 'pending' ORDER BY id LIMIT 1
        """)).fetchone()
    if row:
        jid, jtype, payload = row
        _banner(f"JOB QUEUE — {jtype}")
        with eng.begin() as conn:
            conn.execute(text("UPDATE job_queue SET status='running' WHERE id=:i"), {"i": jid})
        try:
            if jtype == "verify_universe":
                from pipeline.exposure_ledger import verify_universe
                syms = _json.loads(payload) if payload else None
                rep = verify_universe(eng, symbols=syms)
            elif jtype == "update_pass":
                from pipeline.exposure_ledger import run_update_pass
                rep = run_update_pass(eng)
            elif jtype == "qual_full_sweep":
                from pipeline.qual_assessor import run_qual_assessment
                from pipeline.hidden_gem_scorer import score_all_stocks
                gems = score_all_stocks(eng)
                run_qual_assessment(symbols=[g["symbol"] for g in gems], gems=gems)
                rep = {"assessed": len(gems)}
            elif jtype == "birth_queue":
                from pipeline.company_narrative import process_birth_queue
                rep = process_birth_queue(eng, limit=_json.loads(payload) if payload else 2)
            elif jtype == "fmp_backfill":
                from pipeline.fmp_canonical import backfill_universe
                rep = backfill_universe(eng)
            elif jtype == "fmp_ttm_sweep":
                from pipeline.fmp_canonical import ttm_sweep
                rep = ttm_sweep(eng)
            elif jtype == "negative_controls":
                # Amendment 2026-08-05: job name kept for queue compat;
                # the audit measures evidence-grounding, not story-scarcity.
                from pipeline.company_narrative import run_grounding_audit
                rep = run_grounding_audit(eng)
            else:
                raise ValueError(f"unknown job_type {jtype}")
            with eng.begin() as conn:
                conn.execute(text("""UPDATE job_queue SET status='done', finished_at=NOW(),
                    report=:r WHERE id=:i"""), {"r": _json.dumps(rep)[:2000], "i": jid})
            _ok(f"Job {jtype} done: {rep}")
        except Exception:
            err = _tb.format_exc()[-1800:]
            _err(f"Job {jtype} failed", err)
            with eng.begin() as conn:
                conn.execute(text("""UPDATE job_queue SET status='failed', finished_at=NOW(),
                    report=:r WHERE id=:i"""), {"r": err, "i": jid})
    eng.dispose()
    _process_onboarding_queue()


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
    except Exception:
        import traceback as _tb2
        err = _tb2.format_exc()[-1800:]
        _err("Onboarding failed", err)
        with eng.begin() as conn:
            conn.execute(text("""
                UPDATE onboarding_queue SET status='failed', finished_at=NOW(),
                    report=:r WHERE id=:i"""), {"r": _json.dumps({"error": err}), "i": qid})
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

    _step("2b", "PEG normalization (sustainable-growth denominator)")
    try:
        from pipeline.peg_normalizer import recompute_pegs
        from pipeline.hidden_gem_scorer import get_engine as _ge
        eng = _ge()
        r = recompute_pegs(eng)
        eng.dispose()
        _ok(f"PEG: {r}")
    except Exception as e:
        _err("PEG normalization failed", e)

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
        # Fast path first (earningscall.biz, ~15 min post-call), then FMP
        # fallback — same EARN_CALL:{sym}:Q{q}:{year} key-space, so whichever
        # lands first owns the row and the other skips. Purely additive.
        try:
            from pipeline.earningscall_source import fetch_fast_transcripts
            from pipeline.hidden_gem_scorer import get_engine as _ge_ec
            _ec = _ge_ec()
            _ok(f"Fast transcripts: {fetch_fast_transcripts(_ec)}")
            _ec.dispose()
        except Exception as e:
            _err("Fast transcript source failed (FMP fallback continues)", e)
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

    _step("4c", "Narrative ledger update (evidence-gated, daily cadence)")
    try:
        from pipeline.exposure_ledger import run_update_pass
        from pipeline.hidden_gem_scorer import get_engine as _ge4c
        eng = _ge4c()
        r = run_update_pass(eng)
        eng.dispose()
        _ok(f"Ledger update: {r}")
    except Exception as e:
        _err("Ledger update failed", e)

    _step("4d", "Company-narrative birth queue (judge is the filter; cap = circuit-breaker)")
    try:
        from pipeline.company_narrative import process_birth_queue
        from pipeline.hidden_gem_scorer import get_engine as _ge4d
        eng = _ge4d()
        r = process_birth_queue(eng)
        eng.dispose()
        _ok(f"Birth queue: {r}")
    except Exception as e:
        _err("Birth queue failed", e)

    _step(5, "Re-score + archive leaderboard")
    engine = None
    gems = None
    try:
        engine, gems = _score_and_archive()
    except Exception as e:
        _err("Scoring failed", e)

    _step("5b2", "Prediction grader (due checkpoints -> maturity)")
    try:
        from pipeline.checkpoint_grader import grade_due_checkpoints
        from pipeline.hidden_gem_scorer import get_engine as _ge5b
        _e5b = _ge5b()
        r = grade_due_checkpoints(_e5b)
        _e5b.dispose()
        _ok(f"Grader: {r}")
    except Exception as e:
        _err("Prediction grader failed", e)

    _step("5b3", "Shadow lane (designs A/B/C, live scores untouched)")
    try:
        from pipeline.shadow_lane import compute_shadow
        from pipeline.hidden_gem_scorer import get_engine as _ge5s
        _e5s = _ge5s()
        if gems:
            r = compute_shadow(_e5s, gems)
            _ok(f"Shadow lane: {r}")
        else:
            _ok("Shadow lane skipped (no scored universe this run)")
        _e5s.dispose()
    except Exception as e:
        _err("Shadow lane failed", e)

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

    # Step 7 (archive daily scores) RETIRED 2026-08-04: daily_score_archiver
    # computed the LEGACY formula into a table nothing reads — score-history
    # truth lives in leaderboard_history (which Stock Detail's chart uses).
    # Table retained for its historical rows; no new legacy numbers written.

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

    _step("8b2", "Position management (SB=buy, Buy=hold, 2 days below Buy=sell)")
    try:
        from pipeline.track_record import manage_positions
        from pipeline.hidden_gem_scorer import get_engine as _ge8b2
        _e8b2 = _ge8b2()
        r = manage_positions(_e8b2)
        _e8b2.dispose()
        _ok(f"Positions: {r}")
    except Exception as e:
        _err("Position management failed", e)

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

    _step("9b", "Morning Report (shadow phase — stored, not yet on Home)")
    try:
        from pipeline.daily_report import generate_report
        from pipeline.hidden_gem_scorer import get_engine as _ge9b
        _e9b = _ge9b()
        r = generate_report(_e9b)
        _e9b.dispose()
        _ok(f"Morning Report: {r}")
    except Exception as e:
        _err("Morning Report failed", e)

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
        _process_job_queue()
    except Exception as e:
        _err("Job queue failed", e)

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
        # Fast path first (earningscall.biz, ~15 min post-call), then FMP
        # fallback — same EARN_CALL:{sym}:Q{q}:{year} key-space, so whichever
        # lands first owns the row and the other skips. Purely additive.
        try:
            from pipeline.earningscall_source import fetch_fast_transcripts
            from pipeline.hidden_gem_scorer import get_engine as _ge_ec
            _ec = _ge_ec()
            _ok(f"Fast transcripts: {fetch_fast_transcripts(_ec)}")
            _ec.dispose()
        except Exception as e:
            _err("Fast transcript source failed (FMP fallback continues)", e)
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
        # Fast path first (earningscall.biz, ~15 min post-call), then FMP
        # fallback — same EARN_CALL:{sym}:Q{q}:{year} key-space, so whichever
        # lands first owns the row and the other skips. Purely additive.
        try:
            from pipeline.earningscall_source import fetch_fast_transcripts
            from pipeline.hidden_gem_scorer import get_engine as _ge_ec
            _ec = _ge_ec()
            _ok(f"Fast transcripts: {fetch_fast_transcripts(_ec)}")
            _ec.dispose()
        except Exception as e:
            _err("Fast transcript source failed (FMP fallback continues)", e)
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

    _step("3d", "Dirty-symbol fundamentals re-fetch (event-driven, 2026-07-31)")
    # Same-evening structured numbers for stocks that JUST reported: a symbol
    # is dirty iff an earnings filing was INGESTED after its last fundamentals
    # fetch. Self-limiting: once re-fetched, fetched_at > created_at -> clean.
    # Bounded at 25/run; the 06:00 full refresh mops up any overflow.
    try:
        from pipeline.hidden_gem_scorer import get_engine as _ge
        eng = _ge()
        with eng.connect() as _c:
            dirty = [r[0] for r in _c.execute(text("""
                SELECT DISTINCT fu.symbol FROM fundamentals fu
                JOIN filings f ON f.symbol = fu.symbol
                WHERE (f.filing_type = 'EARN_CALL'
                       OR (f.filing_type = '8-K' AND f.event_type = 'EARNINGS'))
                  AND f.created_at > fu.fetched_at
                  AND f.created_at > NOW() - INTERVAL '3 days'
                LIMIT 25
            """)).fetchall()]
        eng.dispose()
        if dirty:
            from db.session import get_session
            from pipeline.fundamentals import fetch_fundamentals
            s = get_session()
            fetch_fundamentals(s, dirty)
            # Canonical TTM refresh for the same symbols so statement
            # fields stay FMP-owned even between weekly sweeps (P2).
            try:
                from pipeline.fmp_canonical import ttm_sweep
                from pipeline.hidden_gem_scorer import get_engine as _ged
                _ed = _ged()
                ttm_sweep(_ed, symbols=dirty)
                _ed.dispose()
            except Exception as _e:
                _err("Canonical TTM refresh failed", _e)
            s.close()
            _ok(f"Dirty re-fetch: {len(dirty)} just-reported symbols: {', '.join(dirty[:10])}")
        else:
            _ok("No dirty symbols — nothing re-fetched")
    except Exception as e:
        _err("Dirty fundamentals re-fetch failed", e)

    _step("3e", "Narrative ledger update (evidence-gated, daily cadence)")
    # The stateful update-pass self-limits to stocks whose filings are newer
    # than their ledger — zero LLM calls on quiet days by construction.
    try:
        from pipeline.exposure_ledger import run_update_pass
        eng = _ge()
        r = run_update_pass(eng)
        eng.dispose()
        _ok(f"Ledger update: {r}")
    except Exception as e:
        _err("Ledger update failed", e)

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

    _step("2b", "PEG normalization (sustainable-growth denominator)")
    try:
        from pipeline.peg_normalizer import recompute_pegs
        from pipeline.hidden_gem_scorer import get_engine as _ge
        eng = _ge()
        r = recompute_pegs(eng)
        eng.dispose()
        _ok(f"PEG: {r}")
    except Exception as e:
        _err("PEG normalization failed", e)

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
                WHERE date = (SELECT MAX(date) FROM leaderboard_history)
                  AND COALESCE(assessed_tier, tier) IN ('Strong Buy', 'Buy')
                ORDER BY gem_score DESC LIMIT 20
            """)).fetchall()
        top_symbols = [r[0] for r in rows]
        for sym in top_symbols:
            try:
                # BUG until 2026-07-20: called generate_deep_dive(sym, ...) —
                # ticker passed AS the engine; every weekly dive crashed
                # silently. All existing memos came from on-page generation.
                generate_deep_dive(eng, sym, force=False)
                _ok(f"Deep dive: {sym}")
            except Exception as ex:
                _err(f"Deep dive {sym}", ex)
        eng.dispose()
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

    _step("5d", "Narrative exposure UPDATE pass (stateful ledger — user directive 2026-07-27)")
    try:
        import os as _os
        from pipeline.hidden_gem_scorer import get_engine as _ge
        eng = _ge()
        if _os.environ.get("EXPOSURE_LEGACY") == "1":
            # Rollback path: the old wipe-and-rewrite judge (one cycle only)
            from pipeline.narrative_exposure import run_exposure_scoring, sign_exposures
            _ok(f"LEGACY exposures: {run_exposure_scoring(eng)}")
            _ok(f"Signed: {sign_exposures(eng)}")
        else:
            from pipeline.exposure_ledger import run_update_pass, verify_universe
            r = run_update_pass(eng)   # evidence-gated changes only
            _ok(f"Ledger update: {r}")
            # Establishment for stocks with NO ledger (new onboardings) —
            # Sonnet-grade with two-vote removal protection, never Haiku coin-flips
            with eng.connect() as _c:
                newcomers = [x[0] for x in _c.execute(text("""
                    SELECT DISTINCT ft.symbol FROM filing_themes ft
                    LEFT JOIN narrative_exposures ne ON ne.symbol = ft.symbol
                    WHERE ne.symbol IS NULL
                      AND ft.filing_date >= NOW() - INTERVAL '15 months'
                """)).fetchall()]
            if newcomers:
                _ok(f"Establishing ledgers for {len(newcomers)} new stocks")
                verify_universe(eng, symbols=newcomers)
        eng.dispose()
    except Exception as e:
        _err("Exposure ledger pass failed", e)

    _step("5e", "Narrative lifecycle (candidates, promotions, falsification)")
    try:
        from pipeline.narrative_lifecycle import run_lifecycle
        run_lifecycle()
        _ok("Lifecycle evaluated")
    except Exception as e:
        _err("Narrative lifecycle failed", e)

    _step("5f", "Narrative structure pass (taxonomy, merge discipline, census)")
    try:
        from pipeline.narrative_structure import run_structure_pass
        from pipeline.hidden_gem_scorer import get_engine as _ge5f
        _e5f = _ge5f()
        r = run_structure_pass(_e5f)
        _e5f.dispose()
        _ok(f"Structure: {r}")
    except Exception as e:
        _err("Narrative structure pass failed", e)

    _step("5g", "Grounding audit (monthly: dossier evidence must trace to filings)")
    try:
        from pipeline.hidden_gem_scorer import get_engine as _ge5g
        _e5g = _ge5g()
        with _e5g.connect() as _c:
            last = _c.execute(text("""
                SELECT MAX(judged_at) FROM narrative_births WHERE source='audit'
            """)).scalar()
        from datetime import datetime as _dt, timedelta as _td
        if last is None or _dt.utcnow() - last > _td(days=28):
            with _e5g.begin() as _c:
                _c.execute(text("""
                    INSERT INTO job_queue (job_type, payload)
                    SELECT 'negative_controls', NULL
                    WHERE NOT EXISTS (SELECT 1 FROM job_queue
                        WHERE job_type='negative_controls' AND status='pending')
                """))
            _ok("Negative-control audit enqueued (last run >28d ago)")
        else:
            _ok(f"Negative controls fresh (last {last:%Y-%m-%d})")
        _e5g.dispose()
    except Exception as e:
        _err("Negative-control audit check failed", e)

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

    _step("6b", "Canonical TTM sweep (weekly full universe, FMP)")
    try:
        from pipeline.fmp_canonical import ttm_sweep
        from pipeline.hidden_gem_scorer import get_engine as _ge6b
        _e6b = _ge6b()
        r = ttm_sweep(_e6b)
        _e6b.dispose()
        _ok(f"Canonical TTM: {r}")
    except Exception as e:
        _err("Canonical TTM sweep failed", e)

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
        _process_job_queue()
    except Exception as e:
        _err("Job queue failed", e)

    _banner("WEEKLY DEEP REFRESH COMPLETE")


# ── Missed-slot catch-up (V2 #16) ────────────────────────────────────────────
# APScheduler keeps its schedule in memory only: a deploy restarting the
# service at (or during) a cron slot silently eats that run — happened
# Jul 7, Jul 20, Jul 22. Every job records itself in scheduler_runs; at
# startup, if a slot fired within the lookback window and has no recorded
# start, the job runs once immediately. All jobs are idempotent (upserts,
# ON CONFLICT, 18h qual guards), so a catch-up can never double-apply.

CATCHUP_LOOKBACK_MIN = 45

def _record_run(job_id: str, slot_ts, phase: str):
    from pipeline.hidden_gem_scorer import get_engine
    eng = get_engine()
    try:
        with eng.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS scheduler_runs (
                    id SERIAL PRIMARY KEY,
                    job_id VARCHAR(20) NOT NULL,
                    slot_ts TIMESTAMP NOT NULL,
                    started_at TIMESTAMP,
                    finished_at TIMESTAMP,
                    UNIQUE (job_id, slot_ts)
                )"""))
            if phase == "start":
                conn.execute(text("""
                    INSERT INTO scheduler_runs (job_id, slot_ts, started_at)
                    VALUES (:j, :s, NOW())
                    ON CONFLICT (job_id, slot_ts) DO UPDATE SET started_at = NOW()
                """), {"j": job_id, "s": slot_ts})
            else:
                conn.execute(text("""
                    UPDATE scheduler_runs SET finished_at = NOW()
                    WHERE job_id = :j AND slot_ts = :s
                """), {"j": job_id, "s": slot_ts})
    finally:
        eng.dispose()


def _last_slot(job_id: str, now):
    """Most recent scheduled fire time <= now for a job, or None."""
    from datetime import datetime, timedelta
    for days_back in range(0, 8):
        d = (now - timedelta(days=days_back)).date()
        wd = d.weekday()          # Mon=0 .. Sun=6
        hour = {"daily": 6, "midday": 13, "after_close": 21, "weekly": 18}[job_id]
        if job_id in ("midday", "after_close") and wd > 4:
            continue
        if job_id == "weekly" and wd != 6:
            continue
        slot = datetime(d.year, d.month, d.day, hour, 0, 0)
        if slot <= now:
            return slot
    return None


def _wrap_job(job_id: str, fn):
    """Job wrapper: stamps the run ledger around the real job."""
    from datetime import datetime
    def runner():
        slot = _last_slot(job_id, datetime.utcnow()) or datetime.utcnow().replace(
            minute=0, second=0, microsecond=0)
        try:
            _record_run(job_id, slot, "start")
        except Exception as e:
            logger.warning(f"run-ledger start failed for {job_id}: {e}")
        fn()
        try:
            _record_run(job_id, slot, "finish")
        except Exception as e:
            logger.warning(f"run-ledger finish failed for {job_id}: {e}")
    runner.__name__ = f"{job_id}_recorded"
    return runner


def _catchup_missed_slots(jobs: dict):
    """At startup: run any job whose slot fired within the lookback window
    but never recorded a start (the deploy ate it)."""
    from datetime import datetime, timedelta
    from pipeline.hidden_gem_scorer import get_engine
    now = datetime.utcnow()
    eng = get_engine()
    try:
        with eng.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS scheduler_runs (
                    id SERIAL PRIMARY KEY,
                    job_id VARCHAR(20) NOT NULL,
                    slot_ts TIMESTAMP NOT NULL,
                    started_at TIMESTAMP,
                    finished_at TIMESTAMP,
                    UNIQUE (job_id, slot_ts)
                )"""))
        for job_id, fn in jobs.items():
            slot = _last_slot(job_id, now)
            if slot is None or now - slot > timedelta(minutes=CATCHUP_LOOKBACK_MIN):
                continue
            # A run must have FINISHED to count. At startup, any started-but-
            # unfinished row is guaranteed dead — the restart killed the process
            # that stamped it (proven live 2026-07-31: deploy at 13:00:26 killed
            # the 13:00 run 3 min in; started_at alone made catch-up skip it).
            with eng.connect() as conn:
                seen = conn.execute(text("""
                    SELECT 1 FROM scheduler_runs
                    WHERE job_id = :j AND slot_ts = :s AND finished_at IS NOT NULL
                """), {"j": job_id, "s": slot}).fetchone()
            if seen:
                continue
            logger.info(f"⚠ CATCH-UP: slot {slot} UTC for '{job_id}' has no recorded "
                        f"run (deploy ate it?) — running now")
            _wrap_job(job_id, fn)()
    except Exception as e:
        logger.error(f"catch-up check failed: {e}")
    finally:
        eng.dispose()


# ── Scheduler setup ───────────────────────────────────────────────────────────

def start_scheduler():
    scheduler = BackgroundScheduler(timezone="UTC")

    scheduler.add_job(
        _wrap_job("daily", daily_data_update),
        trigger=CronTrigger(hour=6, minute=0, timezone="UTC"),
        id="daily", name="Daily data update",
        replace_existing=True, misfire_grace_time=3600,
    )
    scheduler.add_job(
        _wrap_job("midday", midday_refresh),
        trigger=CronTrigger(day_of_week="0-4", hour=13, minute=0, timezone="UTC"),
        id="midday", name="Mid-day refresh (Mon–Fri)",
        replace_existing=True, misfire_grace_time=1800,
    )
    scheduler.add_job(
        _wrap_job("after_close", after_close_refresh),
        trigger=CronTrigger(day_of_week="0-4", hour=21, minute=0, timezone="UTC"),
        id="after_close", name="After-close refresh (Mon–Fri)",
        replace_existing=True, misfire_grace_time=1800,
    )

    scheduler.add_job(
        _wrap_job("weekly", weekly_deep_refresh),
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
    threading.Thread(target=_process_job_queue, name="jobqueue").start()

    # V2 #16: if a deploy just ate a cron slot, run the missed job now.
    threading.Thread(target=_catchup_missed_slots, name="catchup", kwargs={
        "jobs": {"daily": daily_data_update, "midday": midday_refresh,
                 "after_close": after_close_refresh, "weekly": weekly_deep_refresh}
    }).start()

    import time
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("Scheduler stopped.")
