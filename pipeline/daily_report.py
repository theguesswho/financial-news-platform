"""
Morning Report generator (Home revamp Phase 1, user-approved mockup
2026-08-05). Writes one stored report per day into daily_report; the Home
page (Phase 2) renders it with a single SELECT. The emailed brief converges
onto these rows in Phase 3.

Structure (plain lexicon everywhere — no internal jargon on any surface):
  masthead   - the ten-second read (counts, race vs S&P 500, next test)
  week_ahead - upcoming tests of our predictions (5 trading days)
  top_story  - the single most significant event (significance ladder:
               exit > entry > SB upgrade > prediction verdict > birth)
  moves      - every other board change WITH ITS CAUSE, decomposed
               deterministically from stored components (the SPGI lesson:
               a move without a why should never render)
  coverage   - news on our picks: Strong Buys deep, Buys light, tracked
               positions always; annotated against predictions; no padding
  stories    - the story library: births, prediction verdicts, shadow line
  radar      - approaching the board
  scoreboard - our picks vs the S&P 500

Cost discipline: every fact is assembled from stored rows (SQL, free);
ONE batched Sonnet call phrases the narrative sections; deterministic
sections (masthead, week_ahead, scoreboard) are template-built with no
LLM at all. Failures leave yesterday's report in place — the page never
renders a half-written artifact.
"""
import json
import time
from datetime import date

from sqlalchemy import text

SONNET = "claude-sonnet-4-6"

VOICE = """You write the Morning Report for an investment platform that finds quality companies whose genuine story the market has not priced yet. You are given STRUCTURED FACTS assembled from the platform's own data. Write the report items from those facts.

Voice rules (strict):
- Plain language a smart non-specialist understands. Never use internal jargon: no "E score", "NG", "qual", "v2", "checkpoint", "override", "narrative score". Say "our score", "a prediction we made", "our assessment", "how much is already priced in".
- Scores are on a 10-point scale, one decimal ("5.2"). Company names alongside tickers on first mention.
- Every board move must state its CAUSE from the provided decomposition — never report a move without its why. Component semantics (get these RIGHT): priced_in UP = the market caught up, less opportunity left (bearish for us); priced_in DOWN = the market backed off, more opportunity (bullish for us); value UP = the stock got CHEAPER relative to peers (bullish); value DOWN = the valuation richened (bearish); story_exposure UP/DOWN = filings strengthened/weakened the link to its story. If the components conflict with the direction of the move, the score and thresholds decide — say "despite X, Y dominated".
- "Position" means a HELD tracked lot only. Stocks on the board that we don't hold are picks or ratings, never positions.
- Never treat price moves or analyst opinions as evidence about a business. A price move is only opportunity ("the market just made it cheaper") or crowding ("the market caught up").
- No padding. If a fact list is thin, write fewer, shorter items. Never invent color.
- 1-3 sentences per item body. Direct, confident, honest about uncertainty.
- Coverage items: when score_prev/score_now are present, say what the news did to the score ("score held at 5.2" / "score moved 4.8 to 5.2"). When the news is solid but the price FELL (price_move_1d_pct negative), note the setup explicitly: the business delivered, the market made it cheaper — that combination is what tends to RAISE our score next. Never present the price drop itself as bad news about the business.
- The item under "top_story_pick" is the decided top story — write it as such; do not choose your own.
- week_ahead input rows have raw "watching" text (often technical prediction claims). For each, return a "watch" phrase of AT MOST 14 plain words saying what we're looking for in the report — e.g. "does the sterilization margin hold above 45% as new capacity ramps". Keep stake labels (held, board tier, under review) out of it — those render separately.

Add to the JSON: "week_ahead": [{"symbol": "...", "watch": "<=14 words"}]

Return ONLY valid JSON:
{"top_story": {"symbol": "...", "headline": "...", "body": "...", "kind": "exit|entry|upgrade|verdict|birth|info"},
 "moves": [{"symbol": "...", "headline": "...", "body": "...", "kind": "entry|exit|upgrade|downgrade"}],
 "coverage": [{"symbol": "...", "headline": "...", "body": "...", "kind": "info"}],
 "stories": [{"symbol": "...", "headline": "...", "body": "...", "kind": "birth|verdict|info"}]}"""


def create_table(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS daily_report (
                date     DATE NOT NULL,
                position INTEGER NOT NULL,
                section  VARCHAR(16) NOT NULL,
                kind     VARCHAR(12),
                symbol   VARCHAR(10),
                headline TEXT,
                body     TEXT,
                meta     TEXT,
                payload  TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (date, position)
            )"""))


# ---------------------------------------------------------------- facts

def _board_moves(engine) -> list:
    """Board changes between the last two snapshots, with deterministic
    cause decomposition from stored components."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            WITH d AS (SELECT DISTINCT date FROM leaderboard_history
                       ORDER BY date DESC LIMIT 2),
            cur AS (SELECT * FROM leaderboard_history WHERE date=(SELECT MAX(date) FROM d)),
            prev AS (SELECT * FROM leaderboard_history WHERE date=(SELECT MIN(date) FROM d))
            SELECT COALESCE(c.symbol, p.symbol),
                   COALESCE(p.assessed_tier, p.tier), COALESCE(c.assessed_tier, c.tier),
                   p.gem_score, c.gem_score, p.priced_in, c.priced_in,
                   p.narrative_score, c.narrative_score, p.value_score, c.value_score,
                   p.assessed_tier IS NOT NULL, c.assessed_tier IS NOT NULL,
                   p.quality_score, c.quality_score, p.ng_score, c.ng_score
            FROM cur c FULL OUTER JOIN prev p USING (symbol)
            WHERE COALESCE(COALESCE(c.assessed_tier, c.tier), '_')
                  IS DISTINCT FROM COALESCE(COALESCE(p.assessed_tier, p.tier), '_')
        """)).fetchall()
    from pipeline.tiers import BOARD_EXIT, WATCH
    moves = []
    for (sym, pt, ct, pg, cg, pp, cp, pn, cn, pv, cv, p_qual, c_qual,
         pq, cq, png, cng) in rows:
        causes = []
        f = lambda x: float(x) if x is not None else None
        pp, cp, pn, cn, pv, cv, pg_f, cg_f, pq, cq, png, cng = map(
            f, (pp, cp, pn, cn, pv, cv, pg, cg, pq, cq, png, cng))
        # Threshold crossings FIRST — a stock leaving because its score
        # crossed the exit line is score-driven, not "assessment lapsed"
        # (the META mislabel, user 2026-08-06).
        if ct is None and pg_f is not None and cg_f is not None \
                and pg_f > BOARD_EXIT >= cg_f:
            causes.append(f"score crossed below the exit line "
                          f"({BOARD_EXIT*10:.1f} on the 10-scale)")
        if pt is None and cg_f is not None and pg_f is not None \
                and cg_f > WATCH >= pg_f:
            causes.append("score crossed above the entry line")
        # Causes are FINISHED plain-language phrases — the writer must not
        # reinterpret component directions (it inverted value twice on PEG).
        if pp is not None and cp is not None and abs(cp - pp) >= 0.02:
            causes.append(
                f"the market caught up — more of the story is now paid for "
                f"(priced-in {pp:.2f}->{cp:.2f})" if cp > pp else
                f"the market backed off — more unpriced opportunity "
                f"(priced-in {pp:.2f}->{cp:.2f})")
        if pn is not None and cn is not None and abs(cn - pn) >= 0.03:
            causes.append(
                f"filings {'strengthened' if cn > pn else 'weakened'} the link "
                f"to its story (exposure {pn:.2f}->{cn:.2f})")
        if pv is not None and cv is not None and abs(cv - pv) >= 0.03:
            causes.append(
                f"the stock got cheaper relative to peers (value {pv:.2f}->{cv:.2f})"
                if cv > pv else
                f"the valuation richened (value {pv:.2f}->{cv:.2f})")
        # Growth-penalty detection (PEG 2026-08-06: components fine, score
        # halved by fresh fundamentals showing shrinking revenue+earnings).
        # Stored gem vs gem expected from components exposes the multiplier.
        def _ratio(g, v, q, ng):
            if None in (g, v, q, ng) or v <= 0 or q <= 0 or ng <= 0:
                return None
            return g / ((v * q) ** 0.5 * ng ** 0.75)
        r_prev, r_now = _ratio(pg_f, pv, pq, png), _ratio(cg_f, cv, cq, cng)
        if r_now is not None and r_now < 0.6 and (r_prev is None or r_prev > 0.85):
            causes.append("fresh filed numbers show BOTH revenue and earnings "
                          "shrinking — the growth penalty halved the score")
        elif r_now is not None and 0.6 <= r_now < 0.85 and (r_prev is None or r_prev > 0.85):
            causes.append("fresh filed numbers show earnings declining — "
                          "the earnings penalty cut the score by a quarter")
        elif r_prev is not None and r_prev < 0.85 and r_now is not None and r_now > 0.85:
            causes.append("delivered growth turned positive again — the "
                          "growth penalty lifted")
        if p_qual != c_qual and not causes:
            # Only a cause when nothing real moved: pure stamp bookkeeping
            causes.append("bookkeeping_only: assessment stamp "
                          + ("added" if c_qual else "expired"))
        kind = ("entry" if pt is None else "exit" if ct is None else
                "upgrade" if ["Watch", "Buy", "Strong Buy"].index(ct)
                > ["Watch", "Buy", "Strong Buy"].index(pt) else "downgrade") \
            if (pt in (None, "Watch", "Buy", "Strong Buy")
                and ct in (None, "Watch", "Buy", "Strong Buy")) else "info"
        moves.append({
            "symbol": sym, "from": pt, "to": ct, "kind": kind,
            "score_from": round(float(pg) * 10, 1) if pg is not None else None,
            "score_to": round(float(cg) * 10, 1) if cg is not None else None,
            "bookkeeping": bool(causes) and all("bookkeeping_only" in c for c in causes),
            "causes": causes or ["small combined drift across components"]})
    return moves


def _pick_top_story(moves, story_facts) -> dict | None:
    """Deterministic (user 2026-08-06): ladder exit > entry > SB upgrade >
    prediction verdict > birth; |score change| breaks ties. Bookkeeping-only
    moves never lead."""
    real = [m for m in moves if not m.get("bookkeeping")]
    delta = lambda m: abs((m.get("score_to") or 0) - (m.get("score_from") or 0))
    for kind in ("exit", "entry"):
        cand = sorted((m for m in real if m["kind"] == kind), key=delta, reverse=True)
        if cand:
            return {"type": "move", **cand[0]}
    ups = sorted((m for m in real if m["kind"] == "upgrade"
                  and m.get("to") == "Strong Buy"), key=delta, reverse=True)
    if ups:
        return {"type": "move", **ups[0]}
    if story_facts["verdicts"]:
        return {"type": "verdict", **story_facts["verdicts"][0]}
    if story_facts["births"]:
        return {"type": "birth", **story_facts["births"][0]}
    rest = sorted(real, key=delta, reverse=True)
    return {"type": "move", **rest[0]} if rest else None


def _coverage_facts(engine) -> list:
    """Filings in the last ~26h for covered symbols (board SB/Buy + all
    tracked positions), annotated against open predictions."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            WITH covered AS (
                SELECT symbol, COALESCE(assessed_tier, tier) AS tier
                FROM leaderboard_history
                WHERE date = (SELECT MAX(date) FROM leaderboard_history)
                  AND COALESCE(assessed_tier, tier) IN ('Strong Buy', 'Buy')
                UNION
                SELECT DISTINCT symbol, 'Held position' FROM track_lots
                WHERE COALESCE(era, 'v1') = 'v2' AND NOT COALESCE(voided, FALSE)
            )
            SELECT c.symbol, c.tier, f.filing_type, f.filing_date::date,
                   LEFT(COALESCE(f.llm_analysis, ft.raw_themes::text), 400),
                   (SELECT COUNT(*) FROM narrative_checkpoints cp
                    JOIN narratives n ON n.id = cp.narrative_id
                    WHERE n.symbol = c.symbol AND n.scope = 'company'
                      AND cp.status = 'pending') AS open_predictions,
                   scores.s_prev, scores.s_now, px.move_pct
            FROM covered c
            JOIN filings f ON f.symbol = c.symbol
                AND f.created_at > NOW() - INTERVAL '26 hours'
            LEFT JOIN filing_themes ft ON ft.filing_id = f.id
            LEFT JOIN LATERAL (
                SELECT MIN(gem_score) FILTER (WHERE date < (SELECT MAX(date) FROM leaderboard_history)) AS s_prev,
                       MIN(gem_score) FILTER (WHERE date = (SELECT MAX(date) FROM leaderboard_history)) AS s_now
                FROM leaderboard_history lh
                WHERE lh.symbol = c.symbol
                  AND lh.date >= (SELECT MAX(date) FROM leaderboard_history) - 1
            ) scores ON TRUE
            LEFT JOIN LATERAL (
                SELECT ROUND(((MAX(close) FILTER (WHERE rn = 1)) /
                              NULLIF(MAX(close) FILTER (WHERE rn = 2), 0) - 1) * 100, 1) AS move_pct
                FROM (SELECT close, ROW_NUMBER() OVER (ORDER BY date DESC) rn
                      FROM eod_prices WHERE symbol = c.symbol
                        AND date > CURRENT_DATE - 7 LIMIT 2) p
            ) px ON TRUE
            ORDER BY c.tier, f.filing_date DESC LIMIT 12
        """)).fetchall()
    out = []
    for r in rows:
        item = {"symbol": r[0], "tier": r[1], "filing": f"{r[2]} {r[3]}",
                "content": r[4], "open_predictions": r[5],
                "price_move_1d_pct": float(r[8]) if r[8] is not None else None}
        if r[6] is not None and r[7] is not None:
            item["score_prev"] = round(float(r[6]) * 10, 1)
            item["score_now"] = round(float(r[7]) * 10, 1)
        out.append(item)
    return out


def _story_facts(engine) -> dict:
    with engine.connect() as conn:
        births = conn.execute(text("""
            SELECT b.symbol, n.name, n.maturity,
                   (SELECT COUNT(*) FROM narrative_checkpoints c
                    WHERE c.narrative_id = n.id)
            FROM narrative_births b JOIN narratives n ON n.id = b.narrative_id
            WHERE b.verdict = 'accepted' AND b.source IN ('override', 'event')
              AND b.judged_at > NOW() - INTERVAL '26 hours'""")).fetchall()
        verdicts = conn.execute(text("""
            SELECT n.symbol, c.claim, c.status, LEFT(c.status_evidence, 200)
            FROM narrative_checkpoints c JOIN narratives n ON n.id = c.narrative_id
            WHERE c.status IN ('confirmed', 'missed')
              AND c.status_updated > NOW() - INTERVAL '26 hours'""")).fetchall()
        pending = conn.execute(text(
            "SELECT COUNT(*) FROM narrative_birth_queue WHERE status='pending'")).scalar()
        total = conn.execute(text("""
            SELECT COUNT(*) FROM narratives
            WHERE scope='company' AND status IN ('active','candidate','declining')""")).scalar()
    shadow = ""
    try:
        from pipeline.shadow_lane import shadow_summary
        shadow = shadow_summary(engine)
    except Exception:
        pass
    return {"births": [{"symbol": b[0], "name": b[1], "maturity": float(b[2]),
                        "predictions": b[3]} for b in births],
            "verdicts": [{"symbol": v[0], "claim": v[1][:150], "status": v[2],
                          "evidence": v[3]} for v in verdicts],
            "queue_pending": pending, "library_total": total, "shadow": shadow}


def _week_ahead(engine) -> dict:
    """User 2026-08-06: ALL universe earnings this week, with 'what we're
    looking out for' on the ones we have a stake in (board tier, held
    position, open predictions, story under review); the rest compressed
    into per-day lists."""
    with engine.connect() as conn:
        # ALL open predictions (no window): an earnings report grades a
        # company's predictions whenever they exist, not only when the
        # deadline falls this week (CDE case, 2026-08-06).
        cps = conn.execute(text("""
            SELECT n.symbol, MIN(c.deadline), COUNT(*), MIN(LEFT(c.claim, 150))
            FROM narrative_checkpoints c JOIN narratives n ON n.id = c.narrative_id
            WHERE c.status = 'pending' AND n.scope = 'company'
              AND c.deadline >= CURRENT_DATE
            GROUP BY n.symbol""")).fetchall()
        tiers = dict(conn.execute(text("""
            SELECT symbol, COALESCE(assessed_tier, tier) FROM leaderboard_history
            WHERE date = (SELECT MAX(date) FROM leaderboard_history)
              AND COALESCE(assessed_tier, tier) IS NOT NULL""")).fetchall())
        held = {r[0] for r in conn.execute(text("""
            SELECT DISTINCT symbol FROM track_lots
            WHERE COALESCE(era,'v1')='v2' AND NOT COALESCE(voided, FALSE)""")).fetchall()}
        review = {r[0] for r in conn.execute(text(
            "SELECT symbol FROM narrative_birth_queue WHERE status='pending'")).fetchall()}
    cp_map = {r[0]: {"due": str(r[1]), "count": r[2], "claim": r[3]} for r in cps}

    earnings = []
    try:
        from pipeline.earningscall_source import fetch_calendar
        earnings = fetch_calendar(engine, days=7)
    except Exception:
        pass

    notable, other_by_day = [], {}
    seen = set()
    for e in earnings:
        sym = e["symbol"]
        if sym in seen:      # calendar duplicates (CF listed Q2 + Q1)
            continue
        seen.add(sym)
        stake = []
        if sym in tiers: stake.append(f"on the board ({tiers[sym]})")
        if sym in held: stake.append("held position")
        if sym in cp_map:
            stake.append(f"{cp_map[sym]['count']} prediction(s) due — "
                         f"e.g. \"{cp_map[sym]['claim']}\"")
        if sym in review: stake.append("story under review")
        if stake:
            notable.append({"symbol": sym, "date": e["date"],
                            "quarter": e["quarter"], "watching": "; ".join(stake),
                            "tier": tiers.get(sym), "held": sym in held,
                            "review": sym in review,
                            "predictions": cp_map.get(sym, {}).get("count", 0)})
        else:
            other_by_day.setdefault(e["date"], []).append(sym)
    # Prediction deadlines not tied to an earnings date still belong here
    # (but only ones actually due this week)
    from datetime import date as _date, timedelta as _td
    week_end = str(_date.today() + _td(days=7))
    for sym, cp in cp_map.items():
        if sym not in seen and cp["due"] <= week_end:
            notable.append({"symbol": sym, "date": cp["due"], "quarter": "",
                            "watching": f"{cp['count']} prediction(s) due — "
                                        f"e.g. \"{cp['claim']}\"",
                            "tier": tiers.get(sym), "held": sym in held,
                            "review": sym in review, "predictions": cp["count"]})
    notable.sort(key=lambda x: x["date"])
    if len(notable) > 16:
        # Trim plain Watch-tier lines first; held positions and Strong Buys
        # are never cut.
        protected = [n for n in notable if "held" in n["watching"]
                     or "Strong Buy" in n["watching"] or "prediction" in n["watching"]]
        rest = [n for n in notable if n not in protected]
        notable = sorted(protected + rest[:max(0, 16 - len(protected))],
                         key=lambda x: x["date"])
    return {"notable": notable[:20],
            "other": [{"date": d, "symbols": sorted(s)}
                      for d, s in sorted(other_by_day.items())]}


def _masthead(engine, moves) -> dict:
    from pipeline.track_record import get_scorecard
    with engine.connect() as conn:
        board_n = conn.execute(text("""
            SELECT COUNT(*) FROM leaderboard_history
            WHERE date = (SELECT MAX(date) FROM leaderboard_history)
              AND COALESCE(assessed_tier, tier) IN ('Strong Buy', 'Buy')""")).scalar()
    sc = {}
    try:
        sc = get_scorecard(engine) or {}
    except Exception:
        pass
    return {"board": board_n, "changes": len(moves),
            "us_pct": sc.get("portfolio_return_pct"),
            "spy_pct": sc.get("spy_return_pct"),
            "positions": sc.get("open_lots", sc.get("n_lots")),
            "closed": sc.get("closed_lots"), "since": "July 23"}


# ------------------------------------------------------------- generate

SIG_ORDER = {"exit": 0, "entry": 1, "upgrade": 2, "verdict": 3, "birth": 4,
             "downgrade": 5, "info": 6}


def generate_report(engine, for_date: date | None = None) -> dict:
    """Assemble facts, phrase once, store rows. Idempotent per day."""
    from anthropic import Anthropic
    from pipeline.llm_usage import record_usage

    create_table(engine)
    for_date = for_date or date.today()
    moves = _board_moves(engine)
    coverage = _coverage_facts(engine)
    stories = _story_facts(engine)
    week = _week_ahead(engine)
    masthead = _masthead(engine, moves)

    real_moves = [m for m in moves if not m.get("bookkeeping")]
    bookkeeping = [m for m in moves if m.get("bookkeeping")]
    with engine.connect() as conn:
        sales = [{"symbol": r[0],
                  "return_pct": round((float(r[1]) / float(r[2]) - 1) * 100, 1),
                  "twin_pct": round((float(r[3]) / float(r[4]) - 1) * 100, 1),
                  "reason": r[5]}
                 for r in conn.execute(text("""
                     SELECT symbol, exit_price, entry_price,
                            spy_exit_price, spy_price, exit_reason
                     FROM track_lots
                     WHERE exit_date > CURRENT_DATE - 2
                       AND COALESCE(era,'v1') = 'v2'""")).fetchall()]
    top_pick = _pick_top_story(real_moves, stories)
    facts = {"top_story_pick": top_pick, "board_moves": real_moves,
             "position_sales": sales,
             "week_ahead": week["notable"], "coverage": coverage,
             "story_events": {k: stories[k] for k in ("births", "verdicts")},
             "note": "Write top_story from top_story_pick and leave it out of "
                     "'moves'. Coverage items only where content is material; "
                     "skip quiet filings entirely. position_sales are REAL "
                     "portfolio sales — each gets a 'moves' item (kind 'exit') "
                     "leading with the locked result vs its S&P twin."}
    client = Anthropic()
    phrased = None
    for attempt in range(3):
        try:
            resp = client.messages.create(
                model=SONNET, max_tokens=3000, timeout=120,
                system=[{"type": "text", "text": VOICE,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content":
                           "STRUCTURED FACTS:\n" + json.dumps(facts, default=str)}])
            record_usage(engine, "daily_report", SONNET, resp.usage)
            raw = resp.content[0].text.strip()
            phrased = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
            break
        except Exception:
            if attempt < 2:
                time.sleep(2 ** attempt)
    if not isinstance(phrased, dict):
        print("daily report: phrasing failed — keeping previous report")
        return {"status": "failed"}

    rows, pos = [], 0

    def add(section, item, meta=None, payload=None):
        nonlocal pos
        rows.append({"date": for_date, "position": pos, "section": section,
                     "kind": (item or {}).get("kind"),
                     "symbol": (item or {}).get("symbol"),
                     "headline": (item or {}).get("headline"),
                     "body": (item or {}).get("body"), "meta": meta,
                     "payload": json.dumps(payload, default=str) if payload else None})
        pos += 1

    add("masthead", {"headline": "Morning Report"}, payload=masthead)
    watch_lines = {w.get("symbol"): w.get("watch")
                   for w in phrased.get("week_ahead") or [] if isinstance(w, dict)}
    for w in week["notable"]:
        add("week_ahead", {"symbol": w["symbol"], "kind": "watch"},
            payload={**w, "watch": watch_lines.get(w["symbol"])})
    for o in week["other"]:
        add("week_ahead", {"kind": "other"}, payload=o)
    if phrased.get("top_story"):
        add("top_story", phrased["top_story"])
    for m in sorted(phrased.get("moves") or [],
                    key=lambda x: SIG_ORDER.get(x.get("kind"), 9)):
        add("moves", m)
    for c in phrased.get("coverage") or []:
        add("coverage", c)
    for s in phrased.get("stories") or []:
        add("stories", s)
    add("stories", {"headline": "Shadow test", "kind": "info",
                    "body": stories["shadow"]}) if stories["shadow"] else None
    if bookkeeping:
        add("moves", {"headline": "Bookkeeping", "kind": "info",
                      "body": "Stamp-only adjustments (no new information): "
                              + ", ".join(m["symbol"] for m in bookkeeping)})
    add("radar", {"headline": f"{stories['queue_pending']} candidates in review",
                  "kind": "info",
                  "body": (f"{stories['queue_pending']} companies flagged for possible "
                           f"stories await their two-vote review. The library tracks "
                           f"{stories['library_total']} company stories in all.")})
    add("scoreboard", {"headline": "How we're doing vs the market"}, payload=masthead)

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM daily_report WHERE date = :d"), {"d": for_date})
        for r in rows:
            conn.execute(text("""
                INSERT INTO daily_report (date, position, section, kind, symbol,
                                          headline, body, meta, payload)
                VALUES (:date, :position, :section, :kind, :symbol,
                        :headline, :body, :meta, :payload)"""), r)
    print(f"daily report {for_date}: {len(rows)} rows "
          f"({len(moves)} moves, {len(coverage)} coverage facts)")
    return {"status": "ok", "rows": len(rows), "date": str(for_date)}


def render_markdown(engine, for_date: date | None = None) -> str:
    """Render a stored report as markdown (shadow-phase review + fallback)."""
    create_table(engine)
    with engine.connect() as conn:
        if for_date is None:
            for_date = conn.execute(text(
                "SELECT MAX(date) FROM daily_report")).scalar()
        rows = conn.execute(text("""
            SELECT section, kind, symbol, headline, body, payload
            FROM daily_report WHERE date = :d ORDER BY position"""),
            {"d": for_date}).fetchall()
    if not rows:
        return "(no report stored)"
    out = []
    # Week-ahead rows render as one day-grouped block regardless of storage
    # order; pull them out first.
    week_rows = [(k, s, json.loads(pl) if pl else {})
                 for sec, k, s, h, b, pl in rows if sec == "week_ahead"]
    rows = [r for r in rows if r[0] != "week_ahead"]
    def _week_block() -> list:
        from datetime import date as _d
        by_day: dict[str, dict] = {}
        for k, s, p in week_rows:
            d = p.get("date")
            slot = by_day.setdefault(d, {"watch": [], "other": []})
            if k == "other":
                slot["other"] = p.get("symbols") or []
            else:
                slot["watch"].append((s, p))
        blk = ["## Earnings ahead",
               "*Who in our universe reports this week — and what we're looking for.*"]
        for d in sorted(by_day):
            try:
                dd = _d.fromisoformat(d)
                blk.append("**Today**" if dd == _d.today() else f"**{dd:%a %b %-d}**")
            except Exception:
                blk.append(f"**{d}**")
            for sym, p in by_day[d]["watch"]:
                badges = []
                if p.get("held"): badges.append("HELD")
                if p.get("tier"): badges.append(p["tier"].upper())
                if p.get("predictions"): badges.append(
                    f"{p['predictions']} PREDICTION{'S' if p['predictions'] > 1 else ''} ON THE LINE")
                if p.get("review"): badges.append("STORY UNDER REVIEW")
                watch = p.get("watch") or ""
                blk.append(f"- **{sym}** `{' · '.join(badges)}`"
                           + (f" — {watch}" if watch else ""))
            if by_day[d]["other"]:
                syms = by_day[d]["other"]
                blk.append("- *Also reporting:* " + ", ".join(syms[:14])
                           + (f" +{len(syms)-14} more" if len(syms) > 14 else ""))
        return blk

    for section, kind, symbol, headline, body, payload in rows:
        p = json.loads(payload) if payload else {}
        if section == "masthead":
            out.append(f"# Morning Report — {for_date:%A, %B %-d, %Y}")
            us, spy = p.get("us_pct"), p.get("spy_pct")
            race = (f"Our picks {us:+.1f}% vs S&P 500 {spy:+.1f}%"
                    if us is not None and spy is not None else "")
            out.append(f"**{p.get('board')} stocks on the board · "
                       f"{p.get('changes')} changes · {race}**\n")
            if week_rows:
                out.extend(_week_block())
        elif section in ("top_story", "moves", "coverage", "stories", "radar"):
            title = {"top_story": "## Top story", "moves": "## What changed on the board",
                     "coverage": "## News on our picks",
                     "stories": "## The stories we're tracking",
                     "radar": "## Approaching the board"}[section]
            if not any(o == title for o in out):
                out.append(title)
            tag = f" `{kind}`" if kind and kind != "info" else ""
            out.append(f"**{headline}**{tag}\n{body or ''}")
        elif section == "scoreboard":
            out.append("## How we're doing vs the market")
            us, spy = p.get("us_pct"), p.get("spy_pct")
            if us is not None and spy is not None:
                out.append(f"Our picks **{us:+.1f}%** vs S&P 500 **{spy:+.1f}%** · "
                           f"{p.get('positions')} positions · since {p.get('since')}")
    return "\n\n".join(out)


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    from pipeline.hidden_gem_scorer import get_engine
    eng = get_engine()
    if "--render" in sys.argv:
        print(render_markdown(eng))
    else:
        generate_report(eng)
