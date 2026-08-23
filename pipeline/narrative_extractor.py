"""
Phase 1: Extract raw themes from every 10-K and 10-Q filing.

For filings that already have master_analysis  → extract from that text (fast, cheap).
For filings without master_analysis            → extract from raw content.

Output per filing (stored in filing_themes table):
  raw_themes         — list of raw theme strings in the company's own language
  trajectory         — accelerating / stable / decelerating
  narrative_strength — 0.0–1.0 (how clearly management is signalling a direction)
  management_tone    — confident / cautious / defensive
  catalysts          — specific future drivers
  risks              — what could break the thesis

RUBRIC v2 (V3 #15, V3_15_STORY_GRADING_DESIGN.md A/B/C): anchored,
evidence-cited grading. Strength bands must be paid for with cited
numbers (cap 0.6 without); trajectory graded against the company's OWN
prior artifact; tone axis becomes groundedness
(grounded/promotional/cautious/defensive), stored in the same
management_tone column; adds a 2–4 sentence synopsis grounded in the
same cited evidence. Rows stamp rubric_version=2. An output whose band
has no non-empty cited evidence string is INVALID → retried → never
stored (the PAG rule). Synopsis defects (figures absent from the
evidence list, or bad length) are NOT fatal (Edmund 2026-08-22,
Sitting 2): the grade stores, the synopsis is dropped and logged as
synopsis_dropped — a grade is never discarded over the synopsis field.

v2 is the LIVE default since the V3_15_CUTOVER_SPEC.md Phase 5 cutover
(2026-08-23); RUBRIC_V2=0 forces the v1 path as an emergency fallback.
"""

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from anthropic import Anthropic
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(override=True)

MODEL = "claude-haiku-4-5-20251001"   # Fast + cheap for structured extraction
MAX_RETRIES = 3
MAX_WORKERS = 20  # Parallel API calls — Haiku handles high concurrency well
MAX_CONTENT_CHARS = 48_000  # ~12k tokens — Haiku handles 200k tokens, send full filing in one call


def get_engine():
    if os.getenv("DATABASE_URL"):
        url = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg2://")
        from sqlalchemy import create_engine
        return create_engine(url, pool_pre_ping=True)
    host = os.getenv("DB_HOST_IP", "localhost")
    password = os.getenv("DB_PASSWORD", "")
    user = os.getenv("DB_USER", "postgres")
    name = os.getenv("DB_NAME", "postgres")
    return create_engine(f"postgresql+psycopg2://{user}:{password}@{host}/{name}", pool_pre_ping=True)


EXTRACTION_PROMPT = """You are analysing a company SEC filing to extract narrative themes.

Extract the following as JSON. Be specific and concrete — use the company's actual language and context, not generic labels.

{{
  "raw_themes": [
    "3–8 specific themes this company is focused on, in their own words/context",
    "e.g. 'AI-driven drug discovery pipeline acceleration' not just 'AI'"
  ],
  "trajectory": "accelerating | stable | decelerating",
  "narrative_strength": 0.0–1.0 (how clearly is management signalling a strategic direction?),
  "management_tone": "confident | cautious | defensive",
  "catalysts": [
    "specific near-term drivers that could move the stock"
  ],
  "risks": [
    "specific risks management is highlighting"
  ]
}}

Return ONLY valid JSON. No explanation, no markdown fences.

FILING ({symbol} — {filing_type} — {filing_date}):
{text}"""


def extract_themes_from_filing(client, symbol, filing_type, filing_date, text_content):
    """
    Call Claude to extract structured themes from a filing.

    Sends the full document in ONE API call (Haiku supports 200k tokens;
    a typical filing/transcript is 8-15k tokens). This is 4× faster than
    the previous chunked approach and has fewer failure points.
    """
    # For very long documents, take samples from beginning, middle, and end
    # to ensure full coverage without exceeding context limits
    total_len = len(text_content)
    if total_len <= MAX_CONTENT_CHARS:
        text = text_content.strip()
    else:
        # Take first 40%, middle 20%, last 40% — covers exec summary, body, outlook
        a = int(MAX_CONTENT_CHARS * 0.40)
        b = int(MAX_CONTENT_CHARS * 0.20)
        c = int(MAX_CONTENT_CHARS * 0.40)
        mid_start = (total_len // 2) - (b // 2)
        text = (
            text_content[:a] +
            "\n\n[...]\n\n" +
            text_content[mid_start:mid_start + b] +
            "\n\n[...]\n\n" +
            text_content[total_len - c:]
        ).strip()

    prompt = EXTRACTION_PROMPT.format(
        symbol=symbol,
        filing_type=filing_type,
        filing_date=str(filing_date)[:10] if filing_date else "unknown",
        text=text,
    )

    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
                timeout=45,  # never hang a worker indefinitely
            )
            try:
                from pipeline.llm_usage import record_usage
                record_usage(None, "theme_extraction", MODEL, response.usage)
            except Exception:
                pass
            raw = response.content[0].text.strip()

            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.rsplit("```", 1)[0]

            result = json.loads(raw)

            if "raw_themes" not in result:
                raise ValueError("Missing raw_themes")

            return {
                "raw_themes":         result.get("raw_themes", [])[:12],
                "trajectory":         result.get("trajectory", "stable"),
                "narrative_strength": round(float(result.get("narrative_strength", 0.5)), 3),
                "management_tone":    result.get("management_tone", "cautious"),
                "catalysts":          result.get("catalysts", [])[:6],
                "risks":              result.get("risks", [])[:6],
            }

        except (json.JSONDecodeError, ValueError):
            if attempt < MAX_RETRIES - 1:
                time.sleep(1)

        except Exception:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)

    return None


def get_unprocessed_filings(engine, limit=None):
    """Get all 10-K/10-Q filings not yet in filing_themes."""
    query = """
        SELECT f.id, f.symbol, f.filing_type, f.filing_date,
               COALESCE(f.master_analysis, f.content) as text_content
        FROM filings f
        LEFT JOIN filing_themes ft ON ft.filing_id = f.id
        WHERE f.filing_type IN ('10-K', '10-Q', 'EARN_CALL')
          AND ft.id IS NULL
          AND (f.master_analysis IS NOT NULL OR f.content IS NOT NULL)
        ORDER BY f.filing_date DESC
    """
    if limit:
        query += f" LIMIT {limit}"

    with engine.connect() as conn:
        result = conn.execute(text(query))
        return result.fetchall()


def store_themes(engine, filing_id, symbol, filing_type, filing_date, themes):
    """Store extracted themes in filing_themes table."""
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO filing_themes
                (filing_id, symbol, filing_type, filing_date,
                 raw_themes, trajectory, narrative_strength,
                 management_tone, catalysts, risks)
            VALUES
                (:filing_id, :symbol, :filing_type, :filing_date,
                 :raw_themes, :trajectory, :narrative_strength,
                 :management_tone, :catalysts, :risks)
            ON CONFLICT (filing_id) DO UPDATE SET
                raw_themes         = EXCLUDED.raw_themes,
                trajectory         = EXCLUDED.trajectory,
                narrative_strength = EXCLUDED.narrative_strength,
                management_tone    = EXCLUDED.management_tone,
                catalysts          = EXCLUDED.catalysts,
                risks              = EXCLUDED.risks,
                extracted_at       = NOW()
        """), {
            "filing_id":          filing_id,
            "symbol":             symbol,
            "filing_type":        filing_type,
            "filing_date":        filing_date,
            "raw_themes":         json.dumps(themes.get("raw_themes", [])),
            "trajectory":         themes.get("trajectory", "stable"),
            "narrative_strength": themes.get("narrative_strength", 0.5),
            "management_tone":    themes.get("management_tone", "cautious"),
            "catalysts":          json.dumps(themes.get("catalysts", [])),
            "risks":              json.dumps(themes.get("risks", [])),
        })
        conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# RUBRIC v2 — anchored, evidence-cited grading (V3 #15)
# The grading text below is the VALIDATED shadow prompt (shadow_regrade.py,
# 141-filing sample, 2026-08-20) transcribed verbatim — do not re-draft it.
# The raw_themes/catalysts/risks extraction instructions carry over from v1.
# ─────────────────────────────────────────────────────────────────────────────

V2_MAX_WORKERS = 12          # backfill/quote basis (GATE 1 is quoted at 12)
V2_MAX_OUTPUT_TOKENS = 2500  # themes + evidence + synopsis + catalysts/risks
                             # (1400 truncated mid-JSON in the Sitting-1 smoke)

VALID_TRAJECTORIES = {"accelerating", "stable", "decelerating"}
VALID_GROUNDEDNESS = {"grounded", "promotional", "cautious", "defensive"}

EXTRACTION_PROMPT_V2 = """You are re-grading a company SEC filing/transcript under an ANCHORED, evidence-cited rubric. Grade the claim-number relationship, NOT the confidence of the prose. No distribution target: score whatever the evidence supports — but every band must be PAID FOR with citations from the document.

STRENGTH BANDS (0.0-1.0; cite evidence or you cannot award the band):
- 0.9-1.0: guidance RAISED + acceleration visible in numbers the document itself quotes + specific named new business (contract/capacity/product WITH figures). ALL THREE, each cited.
- 0.7-0.8: at least one concrete, quantified positive development; no negative guidance action.
- 0.5-0.6: steady state; claims mostly adjectives; numbers flat.
- 0.3-0.4: a negative guidance action, OR the numbers contradict the narrative (prose claims growth, filed figures flat/declining).
- 0.0-0.2: cuts, withdrawals, impairments; narrative in retreat.
HARD RULE: if you cannot cite specific numbers from the document supporting the band, cap at 0.6.

TRAJECTORY — graded against the company's OWN PRIOR filing (its claims are given below). "accelerating" ONLY if THIS document claims MORE than the prior one (higher guidance, faster claimed growth, new initiatives added). "decelerating" if walking back or claiming less. "stable" otherwise or if the prior claims are not comparable.

GROUNDEDNESS: grounded (confident WITH cited numbers) | promotional (confident WITHOUT them) | cautious | defensive.

ALSO EXTRACT (theme fields, unchanged from the standing extraction):
- "raw_themes": 3–8 specific themes this company is focused on, in their own words/context (e.g. 'AI-driven drug discovery pipeline acceleration' not just 'AI'). Each theme is a SHORT PHRASE (under ~15 words), not a sentence with figures.
- "catalysts": specific near-term drivers that could move the stock (short phrases)
- "risks": specific risks management is highlighting (short phrases)

SYNOPSIS: 2–4 SHORT sentences, HARD LIMIT 450 characters, plain newswire style, stating what this filing/call actually reported. Every figure in the synopsis MUST also appear in your strength_evidence list — a synopsis figure not in the evidence list is invalid; if in doubt, leave the figure out of the synopsis.

PRIOR FILING'S CLAIMS ({prior_label}):
{prior_claims}

Return ONLY valid JSON:
{{"raw_themes": ["..."],
 "narrative_strength": 0.0-1.0,
 "strength_evidence": ["cited fact 1", "..."],
 "trajectory": "accelerating|stable|decelerating",
 "trajectory_evidence": "one sentence citing this doc vs the prior claims",
 "groundedness": "grounded|promotional|cautious|defensive",
 "catalysts": ["..."],
 "risks": ["..."],
 "synopsis": "2-4 short sentences, max 450 chars"}}

FILING ({symbol} — {filing_type} — {filing_date}):
{text}"""

NO_PRIOR_CLAIMS = ("(no prior filing on record — treat trajectory per rubric: "
                   "stable unless internal evidence)")

# Table names the v2 writer/prior-lookup may touch. Anything else is a bug.
_ALLOWED_TABLES = re.compile(r"^[a-z_][a-z0-9_]*$")


def _safe_table(name):
    if not _ALLOWED_TABLES.match(name or ""):
        raise ValueError(f"illegal table name: {name!r}")
    return name


# Tokens whose digits are labels, not figures: form types, fiscal labels,
# quarter refs, bare years. Stripped before figure comparison so "Q3 2026"
# in a synopsis never demands evidence.
_NON_FIGURE_RE = re.compile(
    r"\b(?:10-[KQ](?:/A)?|8-K(?:/A)?|Q[1-4]|H[12]|FY\s?\d{2,4}|(?:19|20)\d{2})\b")
_NUM_RE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")


def _figures(s):
    """Normalised numeric tokens in a string ('$6.7B'→'6.7', '13%'→'13')."""
    cleaned = _NON_FIGURE_RE.sub(" ", s or "")
    return {m.group(0).strip("$%").replace(",", "")
            for m in _NUM_RE.finditer(cleaned)}


def validate_v2_output(result):
    """
    Cutover validation (V3_15_CUTOVER_SPEC Phase 1, from the PAG defect):
    returns (ok, reason, synopsis_defect). An invalid output (ok=False) is
    retried and NEVER stored:
      - strength band must carry at least one non-empty cited evidence string
      - trajectory / groundedness must use the v2 vocabulary
    Synopsis checks are NOT fatal (Edmund 2026-08-22, Sitting 2 — the
    overlay was rejecting ~27% of grades over a field it does not store):
    a synopsis that is missing/mis-sized or states figures absent from the
    evidence list comes back as synopsis_defect; the caller stores the
    grade, drops the synopsis, and logs synopsis_dropped. The PAG rule
    itself is unchanged.
    """
    try:
        strength = float(result.get("narrative_strength"))
    except (TypeError, ValueError):
        return False, "narrative_strength missing or non-numeric", None
    if not (0.0 <= strength <= 1.0):
        return False, f"narrative_strength out of range: {strength}", None

    evidence = result.get("strength_evidence")
    if not isinstance(evidence, list) or not any(
            isinstance(e, str) and e.strip() for e in evidence):
        return False, "no non-empty cited evidence string (PAG rule)", None

    if result.get("trajectory") not in VALID_TRAJECTORIES:
        return False, f"bad trajectory: {result.get('trajectory')!r}", None
    if result.get("groundedness") not in VALID_GROUNDEDNESS:
        return False, f"bad groundedness: {result.get('groundedness')!r}", None

    if not isinstance(result.get("raw_themes"), list) or not result["raw_themes"]:
        return False, "missing raw_themes", None

    synopsis_defect = None
    synopsis = result.get("synopsis")
    if not isinstance(synopsis, str) or not (80 <= len(synopsis.strip()) <= 700):
        synopsis_defect = ("synopsis missing or outside 2-4 short sentences "
                           "(80-700 chars)")
    else:
        ev_figs = _figures(" ".join(e for e in evidence if isinstance(e, str)))
        orphan = _figures(synopsis) - ev_figs
        if orphan:
            synopsis_defect = (f"synopsis figures not in evidence: "
                               f"{sorted(orphan)[:4]}")
    return True, "ok", synopsis_defect


def fetch_prior_claims(conn, symbol, filing_date, filing_id,
                       tables=("filing_themes",)):
    """
    The company's OWN prior artifact, selected deterministically: latest
    (filing_date, filing_id) strictly before this one — same tiebreak class
    as the wire delta fix. `tables` is priority-ordered (backfill passes the
    v2 side table first so in-window priors are same-era; v1 covers history
    before the window). Returns (prior_label, prior_claims_json_str).
    """
    from sqlalchemy import text as _t
    best, best_key = None, None
    for rank, table in enumerate(tables):
        row = conn.execute(_t(f"""
            SELECT filing_type, filing_date, raw_themes, catalysts, filing_id
            FROM {_safe_table(table)}
            WHERE symbol = :s
              AND (filing_date < :d OR (filing_date = :d AND filing_id < :i))
            ORDER BY filing_date DESC, filing_id DESC LIMIT 1
        """), {"s": symbol, "d": filing_date, "i": filing_id}).fetchone()
        if row is None:
            continue
        # Higher (filing_date, filing_id) wins; on a full tie the earlier
        # table in the priority list (the v2 era) wins.
        key = (row[1], row[4], -rank)
        if best_key is None or key > best_key:
            best, best_key = row, key
    if best is None:
        return "none on record", NO_PRIOR_CLAIMS
    label = f"{best[0]} {str(best[1])[:10]}"
    claims = json.dumps({"themes": best[2], "catalysts": best[3]},
                        default=str)[:1800]
    return label, claims


def extract_themes_v2(client, symbol, filing_type, filing_date, text_content,
                      prior_label, prior_claims):
    """
    One filing through the v2 anchored rubric. Returns (themes_dict, None) on
    success or (None, reason) after MAX_RETRIES invalid/failed attempts —
    the caller stores NOTHING on failure and counts it.
    """
    total_len = len(text_content)
    if total_len <= MAX_CONTENT_CHARS:
        body = text_content.strip()
    else:
        a = int(MAX_CONTENT_CHARS * 0.40)
        b = int(MAX_CONTENT_CHARS * 0.20)
        mid_start = (total_len // 2) - (b // 2)
        body = (text_content[:a] + "\n\n[...]\n\n" +
                text_content[mid_start:mid_start + b] + "\n\n[...]\n\n" +
                text_content[total_len - a:]).strip()

    prompt = EXTRACTION_PROMPT_V2.format(
        prior_label=prior_label, prior_claims=prior_claims, symbol=symbol,
        filing_type=filing_type,
        filing_date=str(filing_date)[:10] if filing_date else "unknown",
        text=body)

    reason = "no attempt"
    for attempt in range(MAX_RETRIES):
        try:
            # Retries carry the rejection back so the model fixes the actual
            # defect instead of re-rolling blind.
            attempt_prompt = prompt if attempt == 0 or reason == "no attempt" else (
                prompt + f"\n\nYOUR PREVIOUS ATTEMPT WAS REJECTED: {reason}. "
                         f"Correct exactly that and return the full JSON again.")
            response = client.messages.create(
                model=MODEL,
                max_tokens=V2_MAX_OUTPUT_TOKENS,
                messages=[{"role": "user", "content": attempt_prompt}],
                timeout=60,
            )
            try:
                from pipeline.llm_usage import record_usage
                record_usage(None, "theme_extraction_v2", MODEL, response.usage)
            except Exception:
                pass
            if response.stop_reason == "max_tokens":
                reason = "output truncated (max_tokens)"
                if attempt < MAX_RETRIES - 1:
                    time.sleep(1)
                continue
            raw = response.content[0].text.strip()
            result = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])

            ok, reason, synopsis_defect = validate_v2_output(result)
            if not ok:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(1)
                continue

            return ({
                "raw_themes":         result["raw_themes"][:12],
                "trajectory":         result["trajectory"],
                "narrative_strength": round(float(result["narrative_strength"]), 3),
                # groundedness rides the management_tone column (design C)
                "management_tone":    result["groundedness"],
                "catalysts":          (result.get("catalysts") or [])[:6],
                "risks":              (result.get("risks") or [])[:6],
                "strength_evidence":  result["strength_evidence"][:8],
                "trajectory_evidence": result.get("trajectory_evidence"),
                # a synopsis defect drops the synopsis, never the grade
                "synopsis":           (None if synopsis_defect
                                       else result["synopsis"].strip()),
                "synopsis_dropped":   synopsis_defect,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            }, None)
        except Exception as ex:
            reason = f"{type(ex).__name__}: {str(ex)[:120]}"
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
    return None, reason


def store_themes_v2(engine, filing_id, symbol, filing_type, filing_date,
                    themes, table="filing_themes"):
    """
    Store a VALIDATED v2 output with rubric_version=2. `table` lets the
    Phase 3 backfill write the side table (filing_themes_v2) while live
    stays untouched. Evidence/synopsis are not columns here — the synopsis
    goes to filings.llm_analysis via write_synopsis(); evidence lives in
    the backfill's audit log.
    """
    with engine.connect() as conn:
        conn.execute(text(f"""
            INSERT INTO {_safe_table(table)}
                (filing_id, symbol, filing_type, filing_date,
                 raw_themes, trajectory, narrative_strength,
                 management_tone, catalysts, risks, rubric_version)
            VALUES
                (:filing_id, :symbol, :filing_type, :filing_date,
                 :raw_themes, :trajectory, :narrative_strength,
                 :management_tone, :catalysts, :risks, 2)
            ON CONFLICT (filing_id) DO UPDATE SET
                raw_themes         = EXCLUDED.raw_themes,
                trajectory         = EXCLUDED.trajectory,
                narrative_strength = EXCLUDED.narrative_strength,
                management_tone    = EXCLUDED.management_tone,
                catalysts          = EXCLUDED.catalysts,
                risks              = EXCLUDED.risks,
                rubric_version     = 2,
                extracted_at       = NOW()
        """), {
            "filing_id":          filing_id,
            "symbol":             symbol,
            "filing_type":        filing_type,
            "filing_date":        filing_date,
            "raw_themes":         json.dumps(themes.get("raw_themes", [])),
            "trajectory":         themes.get("trajectory", "stable"),
            "narrative_strength": themes.get("narrative_strength", 0.5),
            "management_tone":    themes.get("management_tone", "cautious"),
            "catalysts":          json.dumps(themes.get("catalysts", [])),
            "risks":              json.dumps(themes.get("risks", [])),
        })
        conn.commit()


def write_synopsis(engine, filing_id, synopsis):
    """
    Merge the v2 synopsis into the filings.llm_analysis slot the wire
    already displays (SYNOPSIS PARITY, Edmund 2026-08-21). Only the
    'synopsis' key is touched; other keys are preserved.
    """
    if not synopsis:
        return
    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT llm_analysis FROM filings WHERE id = :id"),
            {"id": filing_id}).fetchone()
        existing = {}
        if row and row[0]:
            try:
                existing = json.loads(row[0]) if isinstance(row[0], str) else dict(row[0])
                if not isinstance(existing, dict):
                    existing = {}
            except Exception:
                existing = {}
        existing["synopsis"] = synopsis
        conn.execute(text(
            "UPDATE filings SET llm_analysis = :v WHERE id = :id"),
            {"v": json.dumps(existing), "id": filing_id})


def run_extraction_v2(limit=None, table="filing_themes",
                      prior_tables=None, write_synopses=True,
                      max_workers=V2_MAX_WORKERS,
                      overlay=False, audit_path=None):
    """
    v2 twin of run_extraction: unprocessed filings through the anchored
    rubric, OLDEST→NEWEST so each filing's prior-claims context is already
    same-era (spec Phase 3). Invalid-after-retries filings store NOTHING
    and are returned in the failure list.

    overlay=True (Phase 3 copy-then-overlay): the target table is a full
    era-1 COPY, so select rows that EXIST there with rubric_version < 2 —
    resumable by skipping rows already stamped 2. audit_path: JSONL, one
    line per stored filing with evidence + synopsis + usage (with
    write_synopses=False this is the only place the synopsis survives
    until cutover applies it).
    """
    engine = get_engine()
    prior_tables = tuple(prior_tables) if prior_tables else (table,)
    if table != "filing_themes" and "filing_themes" not in prior_tables:
        prior_tables = prior_tables + ("filing_themes",)

    if overlay:
        query = f"""
            SELECT f.id, f.symbol, f.filing_type, f.filing_date,
                   COALESCE(f.master_analysis, f.content) as text_content
            FROM filings f
            JOIN {_safe_table(table)} ft ON ft.filing_id = f.id
            WHERE f.filing_type IN ('10-K', '10-Q', 'EARN_CALL')
              AND ft.rubric_version < 2
              AND (f.master_analysis IS NOT NULL OR f.content IS NOT NULL)
            ORDER BY f.filing_date ASC, f.id ASC
        """
    else:
        query = f"""
            SELECT f.id, f.symbol, f.filing_type, f.filing_date,
                   COALESCE(f.master_analysis, f.content) as text_content
            FROM filings f
            LEFT JOIN {_safe_table(table)} ft ON ft.filing_id = f.id
            WHERE f.filing_type IN ('10-K', '10-Q', 'EARN_CALL')
              AND ft.id IS NULL
              AND (f.master_analysis IS NOT NULL OR f.content IS NOT NULL)
            ORDER BY f.filing_date ASC, f.id ASC
        """
    if limit:
        query += f" LIMIT {limit}"
    with engine.connect() as conn:
        filings = conn.execute(text(query)).fetchall()

    total = len(filings)
    print(f"RUBRIC v2 extraction: {total} filings | {max_workers} workers "
          f"| table={table}")
    if total == 0:
        return {"total": 0, "success": 0, "failed": 0, "failures": [],
                "synopsis_dropped": 0}

    stats = {"total": total, "success": 0, "failed": 0, "failures": [],
             "synopsis_dropped": 0}
    lock = Lock()
    start = time.time()

    def process_one(row):
        filing_id, symbol, filing_type, filing_date, text_content = row
        if not text_content:
            return filing_id, symbol, None, "no content"
        client = Anthropic()
        with engine.connect() as conn:
            prior_label, prior_claims = fetch_prior_claims(
                conn, symbol, filing_date, filing_id, tables=prior_tables)
        themes, reason = extract_themes_v2(
            client, symbol, filing_type, filing_date, text_content,
            prior_label, prior_claims)
        if themes is None:
            return filing_id, symbol, None, reason
        store_themes_v2(engine, filing_id, symbol, filing_type, filing_date,
                        themes, table=table)
        if write_synopses:
            write_synopsis(engine, filing_id, themes.get("synopsis"))
        return filing_id, symbol, themes, None

    audit_f = open(audit_path, "a") if audit_path else None
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_one, row) for row in filings]
        for i, future in enumerate(as_completed(futures), 1):
            fid, sym, themes, err = future.result()
            with lock:
                if themes is not None:
                    stats["success"] += 1
                    if themes.get("synopsis_dropped"):
                        stats["synopsis_dropped"] += 1
                    if audit_f:
                        line = {
                            "filing_id": fid, "symbol": sym,
                            "strength": themes.get("narrative_strength"),
                            "trajectory": themes.get("trajectory"),
                            "groundedness": themes.get("management_tone"),
                            "strength_evidence": themes.get("strength_evidence"),
                            "trajectory_evidence": themes.get("trajectory_evidence"),
                            "synopsis": themes.get("synopsis"),
                            "usage": themes.get("usage"),
                        }
                        if themes.get("synopsis_dropped"):
                            line["synopsis_dropped"] = themes["synopsis_dropped"]
                        audit_f.write(json.dumps(line, default=str) + "\n")
                        audit_f.flush()
                else:
                    stats["failed"] += 1
                    stats["failures"].append({"filing_id": fid, "symbol": sym,
                                              "reason": err})
                    if audit_f:
                        # failed:true marks the line for cutover readers,
                        # which apply synopses from success lines only
                        audit_f.write(json.dumps({
                            "filing_id": fid, "symbol": sym,
                            "failed": True, "reason": err,
                        }, default=str) + "\n")
                        audit_f.flush()
                if i % 100 == 0 or i == total:
                    elapsed = time.time() - start
                    rate = i / elapsed if elapsed else 0
                    rem = (total - i) / rate if rate else 0
                    print(f"  attempted {i}/{total} | stored {stats['success']} "
                          f"| failed {stats['failed']} "
                          f"| synopsis_dropped {stats['synopsis_dropped']} "
                          f"| ~{rem/60:.0f}m remaining", flush=True)

    if audit_f:
        audit_f.close()
    print(f"v2 complete: {stats['success']} stored "
          f"({stats['synopsis_dropped']} with synopsis dropped), "
          f"{stats['failed']} failed ({time.time()-start:.0f}s)")
    return stats


def run_extraction(limit=None):
    """
    Main entry point. Extract themes from all unprocessed 10-K/10-Q filings.
    Uses parallel workers for speed.

    V3 #15 cutover (2026-08-23): the anchored rubric v2 IS the live
    extractor — new rows stamp rubric_version=2 into the swapped table.
    RUBRIC_V2=0 is the emergency fallback to v1 only.
    """
    if os.getenv("RUBRIC_V2", "1") == "1":
        return run_extraction_v2(limit=limit)
    engine = get_engine()

    print("=" * 70)
    print("PHASE 1 — RAW THEME EXTRACTION (parallel)")
    print("=" * 70)

    filings = get_unprocessed_filings(engine, limit=limit)
    total = len(filings)

    if total == 0:
        print("✅ All filings already processed")
        return

    print(f"📋 {total} filings to process | {MAX_WORKERS} parallel workers\n")

    success = 0
    failed = 0
    completed = 0
    start = time.time()
    lock = Lock()

    def process_one(row):
        """Process a single filing — each worker gets its own Anthropic client."""
        filing_id, symbol, filing_type, filing_date, text_content = row
        if not text_content:
            return False, symbol, filing_type

        client = Anthropic()
        themes = extract_themes_from_filing(
            client, symbol, filing_type, filing_date, text_content
        )
        if themes:
            store_themes(engine, filing_id, symbol, filing_type, filing_date, themes)
            return True, symbol, filing_type
        return False, symbol, filing_type

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_one, row): row for row in filings}

        for future in as_completed(futures):
            ok, symbol, filing_type = future.result()

            with lock:
                completed += 1
                if ok:
                    success += 1
                else:
                    failed += 1

                if completed % 20 == 0 or completed == total:
                    elapsed = time.time() - start
                    rate = completed / elapsed
                    remaining = (total - completed) / rate if rate > 0 else 0
                    print(f"  [{completed:4d}/{total}] ✓{success} ✗{failed} | "
                          f"~{remaining/60:.0f}m remaining")

    elapsed = time.time() - start
    print(f"\n{'='*70}")
    print(f"✅ Complete: {success} extracted, {failed} failed — {elapsed/60:.1f} min")
    print(f"{'='*70}")


if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run_extraction(limit=limit)
