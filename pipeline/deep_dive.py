"""
Deep Dive Generator — Buffett-style credit memo for leaderboard stocks.

Generates a structured qualitative memo framed around Warren Buffett's
investment criteria: moat, management (tenure, pay, ownership), owner
earnings, financial fortress, and margin of safety.

Cache invalidation: the memo refreshes only when new filings arrive for
that ticker (new earnings call or 10-K/10-Q), not on a fixed time schedule.
Manual override via the Regenerate button.

Cost: ~$0.02 per memo (Sonnet 4.6, ~2.5k tokens in/out).
"""
import json
from datetime import datetime

import yfinance as yf
from anthropic import Anthropic
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv(override=True)

MODEL = "claude-sonnet-4-6"


# ── DB setup ──────────────────────────────────────────────────────────────────

def create_table(engine):
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS deep_dives (
                id                  SERIAL PRIMARY KEY,
                symbol              VARCHAR(10)  NOT NULL UNIQUE,
                content_json        JSONB        NOT NULL,
                generated_at        TIMESTAMP    NOT NULL DEFAULT NOW(),
                last_filing_date    DATE
            )
        """))
        # Add column if upgrading from old schema without it
        conn.execute(text("""
            ALTER TABLE deep_dives
            ADD COLUMN IF NOT EXISTS last_filing_date DATE
        """))
        conn.commit()


def _latest_filing_date(engine, symbol: str):
    """Return the most recent filing DATE for this symbol.

    filings.filing_date is a DateTime column; deep_dives.last_filing_date is
    DATE. Normalise here so both consumers compare date-to-date — comparing
    datetime to date raises TypeError (LDOS, 2026-07-19)."""
    from datetime import datetime as _dt
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT MAX(filing_date) FROM filings WHERE symbol = :s
        """), {"s": symbol}).fetchone()
    val = row[0] if row else None
    return val.date() if isinstance(val, _dt) else val


def get_cached(engine, symbol: str) -> dict | None:
    """
    Return cached deep dive if still valid.
    Invalid when: no cache exists, or a new filing has arrived since generation.
    """
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT content_json, generated_at, last_filing_date
            FROM deep_dives WHERE symbol = :s
        """), {"s": symbol}).fetchone()
    if row is None:
        return None

    content_json, generated_at, cached_filing_date = row

    # Check if a new filing has arrived since we generated the memo
    latest_filing = _latest_filing_date(engine, symbol)
    if latest_filing and cached_filing_date:
        if latest_filing > cached_filing_date:
            return None  # stale — new data available

    return content_json


def is_stale(engine, symbol: str) -> bool:
    """True if a newer filing exists than what was used to generate the memo."""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT last_filing_date FROM deep_dives WHERE symbol = :s
        """), {"s": symbol}).fetchone()
    if row is None:
        return False  # no memo at all — not "stale", just missing
    cached_filing_date = row[0]
    latest_filing = _latest_filing_date(engine, symbol)
    if latest_filing and cached_filing_date and latest_filing > cached_filing_date:
        return True
    return False


def store(engine, symbol: str, content: dict, filing_date):
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO deep_dives (symbol, content_json, generated_at, last_filing_date)
            VALUES (:s, :c, NOW(), :fd)
            ON CONFLICT (symbol) DO UPDATE SET
                content_json     = EXCLUDED.content_json,
                generated_at     = NOW(),
                last_filing_date = EXCLUDED.last_filing_date
        """), {"s": symbol, "c": json.dumps(content), "fd": filing_date})
        conn.commit()


# ── Data gathering ────────────────────────────────────────────────────────────

def _safe(v):
    try:
        f = float(v)
        return None if (f != f or abs(f) > 1e15) else f
    except Exception:
        return None

def _fmt_pct(v):
    if v is None: return "n/a"
    return f"{float(v)*100:.1f}%"

def _fmt_m(v):
    if v is None: return "n/a"
    v = float(v)
    if abs(v) >= 1e9: return f"${v/1e9:.2f}B"
    return f"${v/1e6:.0f}M"

def _fmt_x(v):
    if v is None: return "n/a"
    return f"{float(v):.1f}x"


# ── Shareholder profiles ─────────────────────────────────────────────────────
# Known qualitative characteristics of major institutional investors.
# Keyed by lowercase substrings that appear in holder names.

SHAREHOLDER_PROFILES = {
    "t. rowe price": (
        "Long-term fundamental investor. Known for concentrated, high-conviction "
        "positions held for years. Their presence at scale signals deep research "
        "conviction — they do not buy and hold passively."
    ),
    "price (t.rowe)": (
        "T. Rowe Price affiliate — same long-term fundamental mandate."
    ),
    "blackrock": (
        "World's largest asset manager. Holds primarily through index funds; "
        "position size reflects index weight, not active conviction. "
        "Votes on governance but rarely activist."
    ),
    "vanguard": (
        "Passive index investor. Position reflects index weight only. "
        "Highly stable, low-turnover holder. No active thesis on the business."
    ),
    "state street": (
        "Passive index and ETF manager (SPDR funds). Similar to Vanguard — "
        "index-weight driven, not a signal of active conviction."
    ),
    "geode": (
        "Fidelity's internal index arm — passive, index-weight driven."
    ),
    "janus henderson": (
        "Active fundamental manager with a quality-growth bias. "
        "Meaningful presence signals active research conviction."
    ),
    "pictet": (
        "European active manager, quality-growth style, long holding periods. "
        "Known for patient capital in high-ROIC compounders."
    ),
    "invesco": (
        "Mixed active and passive manager. Check whether position is in an "
        "ETF or active fund — passive if so, active conviction if not."
    ),
    "fidelity": (
        "Large active + passive manager. Significant active research capability; "
        "position in active funds signals conviction."
    ),
    "wellington": (
        "Large active manager, long-only, quality-growth bias. "
        "Patient, long-term holders when they take a position."
    ),
    "baillie gifford": (
        "Scottish active manager, famous for extreme long-term conviction positions. "
        "Presence is a strong quality signal."
    ),
    "capital group": (
        "Long-term active manager, fundamental research-driven. "
        "High-conviction, low-turnover investor."
    ),
    "morgan stanley": (
        "Mixed active and passive. Active funds include high-quality growth mandates."
    ),
}

def _shareholder_profile(name: str) -> str:
    name_lower = name.lower()
    for key, profile in SHAREHOLDER_PROFILES.items():
        if key in name_lower:
            return profile
    return "Institutional investor — no specific profile available."


def _parse_call_roster(content: str) -> list[str]:
    """Extract 'Name, Title' pairs from the opening of an earnings call transcript."""
    roster = []
    for line in content[:1500].split("\n"):
        line = line.strip()
        if not line:
            continue
        # Lines like "On the call today are Neil Barua, Chief Executive Officer"
        if "on the call today" in line.lower():
            # Extract everything after "are"
            idx = line.lower().find(" are ")
            if idx >= 0:
                people_str = line[idx + 5:].rstrip(".")
                # Split by "; and " or "; "
                for part in people_str.replace("; and ", "; ").split("; "):
                    part = part.strip().rstrip(".")
                    if part:
                        roster.append(part)
    return roster


def gather_context(engine, symbol: str) -> dict:
    """Pull all data needed for the deep dive prompt."""
    with engine.connect() as conn:
        fund = conn.execute(text(
            "SELECT * FROM fundamentals WHERE symbol=:s"
        ), {"s": symbol}).fetchone()
        fund_cols = [r[0] for r in conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='fundamentals' ORDER BY ordinal_position"
        )).fetchall()]
        fund_d = dict(zip(fund_cols, fund)) if fund else {}

        hist = conn.execute(text("""
            SELECT period_end, revenue, gross_margin, op_margin, net_margin, fcf, roic
            FROM fundamentals_history
            WHERE symbol=:s AND period_type='A'
            ORDER BY period_end ASC
            LIMIT 5
        """), {"s": symbol}).fetchall()

        qa = conn.execute(text("""
            SELECT adjusted_tier, direction, key_bull, key_bear, rationale
            FROM qual_assessments WHERE symbol=:s
        """), {"s": symbol}).fetchone()

        themes = conn.execute(text("""
            SELECT ft.raw_themes, ft.catalysts, ft.risks, ft.trajectory,
                   ft.management_tone, f.filing_type, f.filing_date
            FROM filing_themes ft
            JOIN filings f ON f.id = ft.filing_id
            WHERE ft.symbol=:s
            ORDER BY f.filing_date DESC
            LIMIT 4
        """), {"s": symbol}).fetchall()

        company_name = conn.execute(text(
            "SELECT company_name FROM screener_results WHERE symbol=:s"
        ), {"s": symbol}).scalar() or symbol

        latest_filing = conn.execute(text(
            "SELECT MAX(filing_date) FROM filings WHERE symbol=:s"
        ), {"s": symbol}).scalar()

    # ── Corporate story from filings ──────────────────────────────────────────
    corporate_events = _extract_corporate_story(engine, symbol)

    with engine.connect() as conn:
        # ── Earnings call leadership roster history ───────────────────────────
        call_rows = conn.execute(text("""
            SELECT filing_date, LEFT(content, 1500)
            FROM filings
            WHERE symbol=:s AND filing_type='EARN_CALL'
            ORDER BY filing_date ASC
        """), {"s": symbol}).fetchall()

    # Build call roster history: [{date, roster: [str]}]
    call_rosters = []
    for filing_date, intro in call_rows:
        roster = _parse_call_roster(intro or "")
        if roster:
            call_rosters.append({
                "date":   str(filing_date)[:10],
                "roster": roster,
            })

    # Detect leadership changes across calls
    leadership_changes = _detect_leadership_changes(call_rosters)

    # ── yfinance: share count, officers, shareholders ─────────────────────────
    share_history   = []
    insider_pct     = None
    officers        = []
    top_holders     = []

    try:
        ticker = yf.Ticker(symbol)
        info   = ticker.info or {}

        insider_pct = _safe(info.get("heldPercentInsiders"))

        raw_officers = info.get("companyOfficers", [])
        for o in raw_officers[:8]:
            name      = o.get("name", "").replace("Mr. ", "").replace("Ms. ", "").strip()
            title     = o.get("title", "")
            age       = o.get("age")
            total_pay = _safe(o.get("totalPay"))
            officers.append({
                "name":      name,
                "title":     title,
                "age":       age,
                "total_pay": total_pay,
            })

        bs = ticker.balance_sheet
        if bs is not None and not bs.empty:
            share_rows = [r for r in bs.index
                          if "ordinary" in r.lower() or "share issued" in r.lower()]
            if share_rows:
                row_data = bs.loc[share_rows[0]]
                for col, val in zip(bs.columns, row_data):
                    v = _safe(val)
                    if v:
                        share_history.append({
                            "year":     str(col)[:4],
                            "shares_m": round(v / 1e6, 2),
                        })

        ih = ticker.institutional_holders
        if ih is not None and not ih.empty:
            for _, row in ih.head(7).iterrows():
                name = row.get("Holder", "")
                top_holders.append({
                    "name":    name,
                    "pct":     _safe(row.get("pctHeld")),
                    "change":  _safe(row.get("pctChange")),
                    "profile": _shareholder_profile(name),
                })

    except Exception:
        pass

    return {
        "symbol":             symbol,
        "company":            company_name,
        "fund":               fund_d,
        "hist":               hist,
        "qa":                 qa,
        "themes":             themes,
        "share_history":      share_history,
        "insider_pct":        insider_pct,
        "officers":           officers,
        "top_holders":        top_holders,
        "call_rosters":       call_rosters,
        "leadership_changes": leadership_changes,
        "corporate_events":   corporate_events,
        "latest_filing":      latest_filing,
    }


def _extract_corporate_story(engine, symbol: str) -> list[dict]:
    """
    Mine earnings call transcripts and 10-K/10-Q filings for corporate events:
    acquisitions, divestitures, mergers, strategic pivots, buyback programs, debt moves.
    Returns a list of {date, event_type, snippet} dicts, oldest first.
    """
    EVENT_KEYWORDS = {
        "acquisition":  ["acqui", "purchased", "we bought", "completed the acquisition",
                         "closed on", "agreed to acquire"],
        "divestiture":  ["divest", "divestiture", "sold our", "sale of", "dispose",
                         "completing the sale", "agreed to sell"],
        "buyback":      ["share repurchase", "buyback", "repurchased", "buy back",
                         "repurchase program", "repurchase authorization"],
        "debt":         ["paid down", "debt repayment", "refinanc", "credit facility",
                         "bond mature", "paid off debt"],
        "pivot":        ["focused company", "strategic focus", "transformation",
                         "go-to-market transformation", "refocus", "simplified"],
        "leadership":   ["appointed", "chief executive", "new ceo", "new cfo",
                         "stepping down", "resigned", "transition"],
    }

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT filing_date, filing_type, content
            FROM filings
            WHERE symbol = :s
              AND filing_type IN ('EARN_CALL', '10-K', '8-K')
            ORDER BY filing_date ASC
        """), {"s": symbol}).fetchall()

    events = []
    seen_snippets = set()  # avoid near-duplicate hits

    for filing_date, filing_type, content in rows:
        if not content:
            continue
        lower = content.lower()
        date_str = str(filing_date)[:10]

        for event_type, keywords in EVENT_KEYWORDS.items():
            for kw in keywords:
                idx = 0
                while True:
                    idx = lower.find(kw, idx)
                    if idx < 0:
                        break
                    # Extract a clean sentence-ish snippet
                    start = max(0, idx - 120)
                    end   = min(len(content), idx + 280)
                    snippet = content[start:end].replace("\n", " ").strip()
                    # Deduplicate by first 60 chars
                    key = snippet[:60]
                    if key not in seen_snippets:
                        seen_snippets.add(key)
                        events.append({
                            "date":       date_str,
                            "type":       event_type,
                            "source":     filing_type,
                            "snippet":    snippet,
                        })
                    idx += len(kw)

    # Deduplicate aggressively — keep one per (date, event_type)
    seen = {}
    deduped = []
    for e in events:
        key = (e["date"], e["type"])
        if key not in seen:
            seen[key] = True
            deduped.append(e)

    return deduped


def _detect_leadership_changes(call_rosters: list[dict]) -> list[str]:
    """
    Compare consecutive call rosters to surface executive arrivals and departures.
    Returns list of human-readable change strings, e.g. 'CFO changed: Kristian Talvitie → Jen DiRico (Feb 2026)'.
    """
    if len(call_rosters) < 2:
        return []

    changes = []

    def _role_map(roster: list[str]) -> dict[str, str]:
        """Map role keyword → name from roster entries like 'Neil Barua, Chief Executive Officer'."""
        role_map = {}
        for entry in roster:
            parts = [p.strip() for p in entry.split(",", 1)]
            if len(parts) == 2:
                name, title = parts
                title_lower = title.lower()
                if "chief executive" in title_lower or "ceo" in title_lower:
                    role_map["CEO"] = name
                elif "chief financial" in title_lower or "cfo" in title_lower:
                    role_map["CFO"] = name
                elif "chief revenue" in title_lower or "cro" in title_lower:
                    role_map["CRO"] = name
                elif "chief operating" in title_lower or "coo" in title_lower:
                    role_map["COO"] = name
                elif "president" in title_lower:
                    role_map["President"] = name
        return role_map

    prev_map  = _role_map(call_rosters[0]["roster"])
    prev_date = call_rosters[0]["date"]

    for call in call_rosters[1:]:
        curr_map  = _role_map(call["roster"])
        curr_date = call["date"]

        for role in set(list(prev_map.keys()) + list(curr_map.keys())):
            prev_name = prev_map.get(role)
            curr_name = curr_map.get(role)
            if prev_name and curr_name and prev_name != curr_name:
                changes.append(
                    f"{role} changed: {prev_name} → {curr_name} (from {curr_date[:7]})"
                )
            elif prev_name and not curr_name:
                changes.append(
                    f"{role} {prev_name} no longer on calls after {prev_date[:7]}"
                )
            elif curr_name and not prev_name:
                changes.append(
                    f"{role} {curr_name} first appeared on calls from {curr_date[:7]}"
                )

        prev_map  = curr_map
        prev_date = curr_date

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for c in changes:
        if c not in seen:
            seen.add(c)
            deduped.append(c)
    return deduped


def build_prompt(ctx: dict) -> str:
    sym                = ctx["symbol"]
    company            = ctx["company"]
    fund               = ctx["fund"]
    hist               = ctx["hist"]
    qa                 = ctx["qa"]
    themes             = ctx["themes"]
    shares             = ctx["share_history"]
    insiders           = ctx["insider_pct"]
    officers           = ctx["officers"]
    holders            = ctx["top_holders"]
    leadership_changes = ctx.get("leadership_changes", [])
    call_rosters       = ctx.get("call_rosters", [])
    corporate_events   = ctx.get("corporate_events", [])

    # 5-year history table
    hist_lines = ["Year    Revenue      GrossM%  OpMgn%  NetMgn%  FCF         ROIC%"]
    for r in hist:
        period_end, rev, gm, om, nm, fcf, roic = r
        yr = str(period_end)[:4]
        hist_lines.append(
            f"{yr}    {_fmt_m(rev):>10}  {_fmt_pct(gm):>7}  {_fmt_pct(om):>6}  "
            f"{_fmt_pct(nm):>7}  {_fmt_m(fcf):>10}  {_fmt_pct(roic):>6}"
        )
    hist_str = "\n".join(hist_lines) if len(hist_lines) > 1 else "(no annual history)"

    # Share count trend
    if shares:
        sorted_shares = sorted(shares, key=lambda x: x["year"])
        share_lines   = [f"  {s['year']}: {s['shares_m']:.1f}M shares" for s in sorted_shares]
        if len(sorted_shares) >= 2:
            first = sorted_shares[0]["shares_m"]
            last  = sorted_shares[-1]["shares_m"]
            delta = last - first
            trend = (
                f"▼ reduced by {abs(delta):.1f}M shares — buybacks outpacing dilution"
                if delta < -0.5 else
                f"▲ increased by {delta:.1f}M — net dilution (stock comp > buybacks)"
                if delta > 0.5 else
                f"≈ flat (net {delta:+.1f}M) — buybacks roughly offsetting stock comp"
            )
            share_lines.append(f"  Trend: {trend}")
        share_str = "\n".join(share_lines)
    else:
        share_str = "(not available)"

    # Management team (from yfinance proxy data)
    if officers:
        mgmt_lines = []
        for o in officers:
            pay_str = f"  pay ${o['total_pay']/1e6:.2f}M" if o.get("total_pay") else "  pay n/a (may be new)"
            age_str = f"  age {o['age']}" if o.get("age") else ""
            mgmt_lines.append(f"  {o['name']} — {o['title']}{age_str}{pay_str}")
        mgmt_str = "\n".join(mgmt_lines)
    else:
        mgmt_str = "(not available)"

    # Leadership changes detected from earnings call transcripts
    if leadership_changes:
        changes_str = "\n".join(f"  • {c}" for c in leadership_changes)
    else:
        changes_str = "  No leadership changes detected across available call transcripts."

    # Most recent call roster (who is currently running the business)
    if call_rosters:
        latest_roster = call_rosters[-1]
        roster_str = f"  As of {latest_roster['date']}: " + " | ".join(latest_roster["roster"])
    else:
        roster_str = "  (no earnings calls in database)"

    # Top shareholders with qualitative profiles
    if holders:
        holder_lines = []
        for h in holders:
            chg_str = f"  (position {h['change']*100:+.1f}% recently)" if h.get("change") is not None else ""
            holder_lines.append(
                f"  {h['name']}: {_fmt_pct(h['pct'])}{chg_str}\n"
                f"    → {h['profile']}"
            )
        holder_str = "\n".join(holder_lines)
    else:
        holder_str = "(not available)"

    insider_str = f"{insiders*100:.2f}%" if insiders else "n/a"

    # Corporate story — group by type, keep most informative snippet per type per year
    if corporate_events:
        # Group by (quarter, type) — one representative snippet per event type per quarter
        grouped: dict[tuple, tuple] = {}
        for e in corporate_events:
            quarter = e["date"][:7]  # YYYY-MM
            key = (quarter, e["type"])
            if key not in grouped or len(e["snippet"]) > len(grouped[key][1]):
                grouped[key] = (e["date"], e["snippet"])

        # Sort chronologically, cap at 14 entries, trim each snippet to 160 chars
        sorted_events = sorted(grouped.items(), key=lambda x: x[0][0])[-14:]
        story_lines = []
        for (ym, etype), (date, snippet) in sorted_events:
            short = snippet.strip()[:160].rsplit(" ", 1)[0] + "…"
            story_lines.append(f"  [{date}] [{etype.upper()}] {short}")
        story_str = "\n".join(story_lines)
    else:
        story_str = "  (no corporate events found in available filings)"

    # Qual assessment
    qa_str = "(not yet assessed)"
    if qa:
        qa_str = (
            f"Tier: {qa[0]}  |  Direction: {qa[1]}\n"
            f"Bull: {qa[2]}\n"
            f"Bear: {qa[3]}\n"
            f"Note: {qa[4]}"
        )

    # Recent filing signals
    theme_lines = []
    for t in themes:
        raw, cats, risks, traj, tone, ftype, fdate = t
        theme_lines.append(f"  [{ftype} {str(fdate)[:10]}] trajectory={traj}, tone={tone}")
    themes_str = "\n".join(theme_lines) or "(none)"

    return f"""You are writing a one-page credit memo on {sym} ({company}) for Warren Buffett.
Buffett's framework: durable competitive advantage, honest capable management,
consistent owner earnings, sensible price. He buys businesses, not stocks.
He avoids complexity, values integrity and long-term thinking.

QUANTITATIVE DATA:
  Sector / Industry: {fund.get('sector','n/a')} / {fund.get('industry','n/a')}
  Market Cap: {_fmt_m(fund.get('market_cap'))}    EV: {_fmt_m(fund.get('enterprise_value'))}
  Price vs 52w High: {_fmt_pct(fund.get('price_vs_52w_high'))}
  Fwd P/E: {_fmt_x(fund.get('pe_forward'))}    PEG: {_fmt_x(fund.get('peg_ratio'))}
  EV/EBITDA: {_fmt_x(fund.get('ev_to_ebitda'))}    EV/FCF: {_fmt_x(fund.get('ev_to_fcf'))}
  Price/FCF: {_fmt_x(fund.get('price_to_fcf'))}    P/B: {_fmt_x(fund.get('price_to_book'))}
  ROIC: {_fmt_pct(fund.get('roic'))}    ROE: {_fmt_pct(fund.get('roe'))}
  Gross Margin: {_fmt_pct(fund.get('gross_margin'))}    Op Margin: {_fmt_pct(fund.get('operating_margin'))}
  Net Margin: {_fmt_pct(fund.get('net_margin'))}    FCF Margin: {_fmt_pct(fund.get('fcf_margin'))}
  Debt/Equity: {_fmt_x(fund.get('debt_to_equity'))}    Current Ratio: {_fmt_x(fund.get('current_ratio'))}
  Rev Growth (YoY): {_fmt_pct(fund.get('revenue_growth_yoy'))}
  Earnings Growth (YoY): {_fmt_pct(fund.get('earnings_growth_yoy'))}
  Analyst Target: ${fund.get('analyst_target_price','n/a')}  ({fund.get('analysts_count','?')} analysts, {fund.get('analyst_rating','n/a')})

5-YEAR ANNUAL HISTORY (oldest → newest):
{hist_str}

SHARE COUNT HISTORY (annual):
{share_str}

MANAGEMENT TEAM (from latest proxy filing):
{mgmt_str}

CURRENT LEADERSHIP ON EARNINGS CALLS:
{roster_str}

EXECUTIVE CHANGES DETECTED FROM EARNINGS CALL TRANSCRIPTS:
{changes_str}

CORPORATE STORY — key events from filings (chronological):
{story_str}

TOP INSTITUTIONAL SHAREHOLDERS (with investor profile):
{holder_str}
  Insider (management + board) ownership: {insider_str}

EXISTING QUALITATIVE ASSESSMENT:
{qa_str}

RECENT FILING SIGNALS:
{themes_str}

Write the credit memo as a JSON object with exactly these 9 keys.
Each prose value is a concise paragraph (3–5 sentences) — specific, grounded in the
data above, no generic waffle. Reference actual names, numbers, and percentages.

BUFFETT TIER DEFINITIONS (for the buffett_tier and buffett_rationale fields):

  "Buffett Stock" — Meets ALL of the following without exception:
    1. MOAT CERTAINTY: The competitive advantage is structural and near-certain to persist
       for 10+ years — not "probably fine" or "likely durable." Think FICO's credit score
       monopoly, Moody's regulatory entrenchment, Otis elevator service lock-in, Visa/MA
       network effects. The moat must be PROVEN across a full economic cycle, not just asserted
       from recent margin data. Active disruption threats (AI, regulation, new entrants gaining
       real share) are disqualifying even if the business is currently performing well.
    2. OWNER EARNINGS QUALITY: FCF has compounded consistently for 5+ years. ROIC durably
       above 15% with no sign of structural compression. Earnings quality is high — FCF
       matches or exceeds reported earnings, SBC is not masking true profitability.
    3. MANAGEMENT: Long-tenured, demonstrably honest, modest pay relative to value created.
       Capital allocation track record is excellent (buybacks at sensible prices, no value-
       destroying acquisitions, no financial engineering). Insider ownership meaningful or
       founder-led. No material succession uncertainty.
    4. BALANCE SHEET: Financial fortress — debt taken on for operational reasons, not financial
       engineering. Survives a bad decade without existential stress.
    5. PRICE: Reasonable margin of safety. Not "cheap enough to overlook everything else" —
       the price must be sensible for a long-term hold, not a distressed valuation propping
       up a weakening business.
    Buffett would write a large check without hesitation. Genuinely rare — maybe 1 in 30.
    When in doubt, do NOT award this tier. Err toward "Potential Buffett."

  "Potential Buffett" — Passes most Buffett criteria but has ONE specific, named gap:
    e.g. perfect business but currently expensive (SPGI at 26x EV/FCF),
    or genuine moat but active disruption threat not yet resolved (ADBE vs AI tools),
    or excellent economics but management continuity uncertainty (PTC leadership churn),
    or moat present but not proven across a full cycle yet.
    The gap must be specific and resolvable — not "generally fine with minor issues."
    Buffett would watch closely and buy on weakness or resolution of the named gap.

  "No Buffett" — Missing one or more foundational requirements. Could be a fine investment
    on other frameworks but does not meet the Buffett standard. Assign this when the moat
    is genuinely uncertain, the business is capital-intensive/commodity-like, management
    has destroyed value, or earnings quality is poor.

{{
  "business_quality": "What does this company do and why do customers keep paying? Is ROIC consistently above cost of capital? Is this the kind of business Buffett would call 'wonderful'?",
  "corporate_story": "Narrate the recent strategic journey using the corporate events data. Acquisitions, divestitures, buybacks — is management building value or destroying it through activity?",
  "economic_moat": "Specific source of competitive advantage with concrete numerical evidence. How durable is it?",
  "management_and_capital_allocation": "Assess by name. CEO tenure and compensation signal. Recent leadership changes and what they mean. Buybacks vs dilution. Insider ownership.",
  "ownership_quality": "Long-term fundamental investors vs passive index holders. What does the register tell us about market conviction?",
  "financial_fortress": "Debt load in context of how it was incurred. FCF consistency. Can it survive a bad decade?",
  "owner_earnings": "FCF margin, trend, yield on EV. Earnings quality. Can the owner take this cash home?",
  "verdict": "One crisp verdict: too hard pile, hold, or large check? Single most important thing to monitor. Be direct.",
  "buffett_tier": "Buffett Stock" | "Potential Buffett" | "No Buffett",
  "buffett_rationale": "One sentence: the single most important reason for this tier. For Buffett Stock name what seals it. For Potential Buffett name the one gap. For No Buffett name the disqualifying factor."
}}

Return ONLY valid JSON. No markdown, no preamble."""


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_deep_dive(engine, symbol: str, force: bool = False) -> dict:
    """
    Generate (or return cached) deep dive for a symbol.
    Cache invalidated when new filings arrive, not on a fixed TTL.
    """
    create_table(engine)

    if not force:
        cached = get_cached(engine, symbol)
        if cached:
            return cached

    ctx    = gather_context(engine, symbol)
    prompt = build_prompt(ctx)

    client = Anthropic()
    resp   = client.messages.create(
        model      = MODEL,
        max_tokens = 2500,
        messages   = [{"role": "user", "content": prompt}],
    )

    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"): raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]

    content = json.loads(raw)
    content["_meta"] = {
        "symbol":       symbol,
        "company":      ctx["company"],
        "generated_at": datetime.utcnow().isoformat(),
        "model":        MODEL,
    }
    store(engine, symbol, content, ctx["latest_filing"])
    return content


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
    from dotenv import load_dotenv
    load_dotenv(override=True)
    from pipeline.hidden_gem_scorer import get_engine
    sym = sys.argv[1] if len(sys.argv) > 1 else "PTC"
    engine = get_engine()
    result = generate_deep_dive(engine, sym, force=True)
    for k, v in result.items():
        if not k.startswith("_"):
            print(f"\n{'='*60}")
            print(f"  {k.upper().replace('_',' ')}")
            print(f"{'='*60}")
            print(v)
