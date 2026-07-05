"""
Narrative exposure scoring — LLM judgment with cited evidence.

Replaces cosine-similarity alignment: for each stock, Haiku reads that stock's
own recent filing themes and catalysts and judges its GENUINE, MATERIAL
exposure to each active narrative — or assigns none. Every exposure must cite
concrete evidence (segments, backlog, revenue share, products). Most stocks
should have 0–2 exposures; broad matching is the failure mode this replaces.

Cost: ~505 Haiku calls ≈ USD 3 per full pass. Run weekly + for new filings.
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from anthropic import Anthropic
from sqlalchemy import text

HAIKU = "claude-haiku-4-5-20251001"
MAX_WORKERS = 12
MIN_EXPOSURE = 0.25   # below this, not material — don't store


def _load_narratives(engine) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, name, tier, thesis, sector_scope FROM narratives
            WHERE status = 'active' ORDER BY tier DESC, id
        """)).fetchall()
    return [{"id": r[0], "name": r[1], "tier": r[2], "thesis": r[3], "scope": r[4]}
            for r in rows]


def _load_stock_context(engine, symbols: list[str] | None = None) -> dict:
    """Per stock: sector + the themes/catalysts from its most recent filings."""
    sym_filter = "AND ft.symbol = ANY(:syms)" if symbols else ""
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT ft.symbol, fu.sector, fu.industry, ft.filing_type,
                   ft.filing_date::date, ft.raw_themes, ft.catalysts
            FROM filing_themes ft
            LEFT JOIN fundamentals fu ON fu.symbol = ft.symbol
            WHERE ft.filing_date >= NOW() - INTERVAL '15 months' {sym_filter}
            ORDER BY ft.symbol, ft.filing_date DESC
        """), {"syms": symbols} if symbols else {}).fetchall()

    ctx: dict[str, dict] = {}
    for sym, sector, industry, ftype, fdate, raw, cats in rows:
        slot = ctx.setdefault(sym, {"sector": sector, "industry": industry, "themes": []})
        if len(slot["themes"]) >= 12:
            continue
        try:
            items = raw if isinstance(raw, list) else (json.loads(raw) if raw else [])
        except Exception:
            items = []
        for t in items[:4]:
            slot["themes"].append(f"[{ftype} {fdate}] {t}")
    return ctx


def _judge_one(client, sym: str, ctx: dict, narratives: list[dict]) -> list[dict]:
    nar_block = "\n".join(
        f"{n['id']}. {n['name']} ({n['tier']}{', ' + n['scope'] if n['scope'] else ''}): {n['thesis']}"
        for n in narratives
    )
    themes_block = "\n".join(ctx["themes"]) or "no extracted themes"

    prompt = f"""You assess whether a company has GENUINE, MATERIAL business exposure to structural narratives — the bar is money, not mentions.

Company: {sym} | Sector: {ctx.get('sector')} | Industry: {ctx.get('industry')}

Evidence from this company's own filings and earnings calls (most recent first):
{themes_block}

NARRATIVES:
{nar_block}

Rules:
- Material = the narrative moves this company's revenue, backlog, or margins in a way its own filings evidence. Merely operating in the sector, or name-dropping AI, is NOT exposure.
- Most companies have 0-2 genuine exposures. Returning an empty list is a good answer.
- exposure: 0.25-0.5 = meaningful contributor; 0.5-0.75 = major driver; >0.75 = the business IS the narrative.
- evidence must cite specifics FROM THE COMPANY'S OWN evidence above (segment, product, backlog, growth figure).

Return ONLY valid JSON array (empty [] if none):
[{{"narrative_id": <int>, "exposure": <0.25-1.0>, "evidence": "<one sentence citing specifics>"}}]"""

    resp = client.messages.create(model=HAIKU, max_tokens=600,
                                  messages=[{"role": "user", "content": prompt}])
    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()
    try:
        start = raw.index("[")
        out = json.loads(raw[start:raw.rindex("]") + 1])
        return [o for o in out
                if isinstance(o, dict) and o.get("narrative_id")
                and float(o.get("exposure", 0)) >= MIN_EXPOSURE]
    except Exception:
        return []


def run_exposure_scoring(engine, symbols: list[str] | None = None) -> dict:
    narratives = _load_narratives(engine)
    if not narratives:
        print("No active narratives — seed the brain first.")
        return {"scored": 0}
    valid_ids = {n["id"] for n in narratives}

    ctx = _load_stock_context(engine, symbols)
    print(f"Judging exposures: {len(ctx)} stocks × {len(narratives)} narratives...")

    results: dict[str, list] = {}
    lock = Lock()
    done = 0

    def work(sym):
        client = Anthropic()
        return sym, _judge_one(client, sym, ctx[sym], narratives)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(work, s) for s in ctx]
        for fut in as_completed(futures):
            sym, exps = fut.result()
            with lock:
                results[sym] = exps
                done += 1
                if done % 50 == 0:
                    print(f"  {done}/{len(ctx)}", flush=True)

    rows = []
    for sym, exps in results.items():
        for e in exps:
            if e["narrative_id"] not in valid_ids:
                continue
            rows.append({"symbol": sym, "nid": int(e["narrative_id"]),
                         "exp": round(float(e["exposure"]), 3),
                         "ev": str(e.get("evidence", ""))[:600]})

    with engine.begin() as conn:
        if symbols:
            conn.execute(text("DELETE FROM narrative_exposures WHERE symbol = ANY(:s)"),
                         {"s": symbols})
        else:
            conn.execute(text("DELETE FROM narrative_exposures"))
        CHUNK = 500
        upsert = text("""
            INSERT INTO narrative_exposures (symbol, narrative_id, exposure, evidence, updated_at)
            VALUES (:symbol, :nid, :exp, :ev, NOW())
            ON CONFLICT (symbol, narrative_id) DO UPDATE SET
                exposure = EXCLUDED.exposure, evidence = EXCLUDED.evidence, updated_at = NOW()
        """)
        for i in range(0, len(rows), CHUNK):
            conn.execute(upsert, rows[i:i + CHUNK])

    n_exposed = len({r['symbol'] for r in rows})
    print(f"✅ {len(rows)} exposures across {n_exposed} stocks "
          f"({len(ctx) - n_exposed} stocks with none — that's healthy)")
    return {"scored": len(ctx), "exposures": len(rows), "stocks_exposed": n_exposed}


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    from pipeline.hidden_gem_scorer import get_engine
    run_exposure_scoring(get_engine())
