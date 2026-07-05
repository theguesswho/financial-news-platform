"""
One-time backdated meta-narrative baseline.

Uses stored per-filing embeddings (filing_themes, dated 2022→now) against the
active canonical meta-theme embeddings to reconstruct, quarter by quarter, how
each theme's footprint evolved: how many companies were genuinely talking about
it, and how strongly. Writes quarterly snapshots into theme_history so the
emergence curves start with 4 years of context instead of from zero.

Backfilled momentum is derived from company-count growth quarter-over-quarter —
cruder than the evidence-based labels the live builder produces, but an honest
baseline. Rows are tagged in momentum_evidence as backfilled.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from sqlalchemy import text
from pipeline.hidden_gem_scorer import get_engine

MENTION_Z = 1.0   # a filing "mentions" a theme when its z-scored similarity >= this


def quarter_end(d):
    q = (d.month - 1) // 3
    last_month = q * 3 + 3
    if last_month == 12:
        return d.replace(month=12, day=31)
    import calendar
    return d.replace(month=last_month, day=calendar.monthrange(d.year, last_month)[1])


def run_backfill():
    engine = get_engine()

    with engine.connect() as conn:
        themes = conn.execute(text("""
            SELECT id, name, embedding FROM meta_themes
            WHERE embedding IS NOT NULL AND COALESCE(status,'active') = 'active'
        """)).fetchall()
        filings = conn.execute(text("""
            SELECT symbol, filing_date, embedding FROM filing_themes
            WHERE embedding IS NOT NULL AND filing_date IS NOT NULL
            ORDER BY filing_date
        """)).fetchall()

    if not themes or not filings:
        print("Missing embeddings — run embedding_builder first.")
        return

    t_ids = [t[0] for t in themes]
    t_names = {t[0]: t[1] for t in themes}
    T = np.array([json.loads(t[2]) if isinstance(t[2], str) else t[2] for t in themes], dtype=np.float32)
    T /= np.linalg.norm(T, axis=1, keepdims=True)

    F = np.array([json.loads(f[2]) if isinstance(f[2], str) else f[2] for f in filings], dtype=np.float32)
    F /= np.linalg.norm(F, axis=1, keepdims=True)

    print(f"{len(filings)} filings × {len(themes)} themes...")
    sims = F @ T.T                                   # (filings × themes)
    z = (sims - sims.mean(axis=0)) / (sims.std(axis=0) + 1e-9)

    # Aggregate mentions per (quarter, theme)
    agg: dict[tuple, dict] = {}
    for i, (sym, fdate, _) in enumerate(filings):
        qend = quarter_end(fdate.date() if hasattr(fdate, "date") else fdate)
        for j in np.where(z[i] >= MENTION_Z)[0]:
            key = (qend, t_ids[j])
            slot = agg.setdefault(key, {"companies": set(), "mentions": 0, "strength": 0.0})
            slot["companies"].add(sym)
            slot["mentions"] += 1
            slot["strength"] += float(sims[i, j])

    # Derive momentum from company-count growth QoQ
    by_theme: dict[int, list] = {}
    for (qend, tid), v in sorted(agg.items()):
        by_theme.setdefault(tid, []).append((qend, len(v["companies"]), v["mentions"],
                                             v["strength"] / max(v["mentions"], 1)))

    rows = []
    for tid, series in by_theme.items():
        prev_companies = None
        for qend, n_comp, n_ment, avg_sim in series:
            if prev_companies is None or prev_companies == 0:
                momentum = "stable"
            else:
                growth = (n_comp - prev_companies) / prev_companies
                momentum = ("accelerating" if growth >= 0.25 and n_comp >= 5
                            else "decelerating" if growth <= -0.25
                            else "stable")
            rows.append({
                "tid": tid, "name": t_names[tid], "date": qend,
                "momentum": momentum,
                "evidence": f"[backfilled] {n_comp} companies, {n_ment} filings mentioned this theme in the quarter",
                "companies": n_comp, "avg": round(avg_sim, 4),
            })
            prev_companies = n_comp

    with engine.begin() as conn:
        for r in rows:
            conn.execute(text("""
                INSERT INTO theme_history
                    (meta_theme_id, theme_name, snapshot_date, momentum,
                     momentum_evidence, company_count, avg_alignment)
                VALUES (:tid, :name, :date, :momentum, :evidence, :companies, :avg)
                ON CONFLICT (meta_theme_id, snapshot_date) DO NOTHING
            """), r)

    print(f"✅ Backfilled {len(rows)} quarterly snapshots across {len(by_theme)} themes")

    # Show the emergence story for a couple of headline themes
    with engine.connect() as conn:
        sample = conn.execute(text("""
            SELECT theme_name, snapshot_date, company_count, momentum
            FROM theme_history
            WHERE theme_name ILIKE '%AI%' OR theme_name ILIKE '%power%' OR theme_name ILIKE '%grid%'
            ORDER BY theme_name, snapshot_date
        """)).fetchall()
    cur = None
    for name, d, n, m in sample:
        if name != cur:
            print(f"\n{name}:")
            cur = name
        print(f"  {d}  {n:>4} companies  [{m}]")


if __name__ == "__main__":
    run_backfill()
