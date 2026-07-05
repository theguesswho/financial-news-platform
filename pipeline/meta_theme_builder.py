"""
Phase 2: Build canonical meta-themes by clustering raw themes from all filings.

Takes all raw_themes extracted in Phase 1, sends them to Claude to identify
what's actually the same underlying concept across different companies/sectors,
then stores the canonical meta-themes.

Phase 3 is also here: score each stock's alignment to each meta-theme.
"""

import json
import os
import time
from collections import defaultdict

import numpy as np
from anthropic import Anthropic
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(override=True)

MODEL = "claude-sonnet-4-6"   # Need the smarter model for clustering judgment


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


# ─────────────────────────────────────────────────────────────
# PHASE 2: CLUSTER RAW THEMES INTO META-THEMES
# ─────────────────────────────────────────────────────────────

def load_all_raw_themes(engine):
    """Load all raw themes with their symbol and sector context."""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT ft.symbol, ft.filing_type, ft.filing_date,
                   ft.raw_themes, ft.trajectory,
                   f.title
            FROM filing_themes ft
            JOIN filings f ON f.id = ft.filing_id
            WHERE ft.raw_themes IS NOT NULL
            ORDER BY ft.filing_date DESC
        """))
        return result.fetchall()


def build_meta_themes(engine, client):
    """
    Collect all raw themes and ask Claude to cluster them into canonical meta-themes.
    """
    print("\n📊 Loading raw themes from database...")
    rows = load_all_raw_themes(engine)

    if not rows:
        print("⚠️  No filing_themes found. Run narrative_extractor.py first.")
        return []

    # Build a flat list: "SYMBOL: theme string"
    # Group by symbol so Claude can see cross-company patterns
    symbol_themes = defaultdict(list)
    for row in rows:
        symbol, filing_type, filing_date, raw_themes_json, trajectory, title = row
        themes = raw_themes_json if isinstance(raw_themes_json, list) else (json.loads(raw_themes_json) if raw_themes_json else [])
        for theme in themes:
            symbol_themes[symbol].append(theme)

    print(f"  {len(rows)} filings | {len(symbol_themes)} stocks | "
          f"{sum(len(v) for v in symbol_themes.values())} total raw themes")

    # Deduplicate raw themes across all stocks — send unique strings only
    all_unique_themes = list(dict.fromkeys(
        theme for themes in symbol_themes.values() for theme in themes
    ))

    # Send in two passes to keep output small enough to parse reliably
    # Pass 1: Get canonical theme names + descriptions only (small output)
    themes_sample = "\n".join(all_unique_themes[:600])  # up to 600 unique raw themes

    print("\n🧠 Pass 1: Identifying canonical meta-theme names...")

    prompt1 = f"""Below are narrative themes extracted from S&P 500 SEC filings across all sectors.

Identify 20–30 canonical meta-themes — the TRUE underlying structural forces that
different companies describe differently. Cluster by meaning, not wording.

Example: "AI-driven cost reduction" (bank) + "AI inventory optimisation" (retailer) +
"administrative automation" (healthcare) = one meta-theme: "AI Operational Efficiency"

The purpose of these themes is to catch mispricings like Dell in 2023: the market
priced it as a laptop maker while its filings showed genuine AI-server exposure.
A theme is only useful if it DISCRIMINATES — separates the companies genuinely
exposed to a structural force from those merely name-dropping it.

Return ONLY a compact JSON array — name, one-sentence description, momentum with
evidence, and a short list of sectors where this appears:

[
  {{
    "name": "3-5 word canonical name",
    "description": "One sentence on what structural force this represents",
    "momentum": "accelerating | stable | decelerating",
    "momentum_evidence": "One sentence citing the CONCRETE evidence: backlog growth, guidance raises, capacity commitments, order books, pricing power — not adjective density",
    "sectors_present": ["Technology", "Healthcare", "Financials"]
  }}
]

Rules:
- Cluster by UNDERLYING force, not surface wording
- Prefer NARROW, discriminating themes over broad ones. "AI Infrastructure
  Build-Out" spanning 120 companies is useless; "Data-center power and grid
  equipment demand" spanning 15 is signal
- SECTOR-SPECIFIC themes are explicitly welcome where a structural force is
  concentrated in one industry (e.g. grid electrification for utilities/
  industrial power, GLP-1 knock-on effects for med-tech, defence re-armament)
- Momentum labels must be earned by evidence in the themes (order books,
  backlog, guidance, capacity expansion). When companies merely TALK about a
  force without numbers, label it "stable". Expect a majority of themes to be
  stable — accelerating should be the exception, not the default
- Be specific: "AI Operational Efficiency" not just "AI"
- Include one "Idiosyncratic / Other" bucket

Return ONLY valid JSON. No markdown, no explanation.

RAW THEMES FROM S&P 500 FILINGS:
{themes_sample}"""

    response1 = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt1}]
    )

    raw1 = response1.content[0].text.strip()
    if raw1.startswith("```"):
        raw1 = raw1.split("```")[1]
        if raw1.startswith("json"):
            raw1 = raw1[4:]
        raw1 = raw1.rsplit("```", 1)[0]

    try:
        meta_themes = json.loads(raw1)
    except json.JSONDecodeError:
        # Truncated output: salvage complete objects up to the last full '}'
        cut = raw1.rfind("},")
        if cut == -1:
            raise
        meta_themes = json.loads(raw1[:cut + 1] + "]")
    print(f"  ✓ Identified {len(meta_themes)} meta-themes")

    # Pass 2: For each meta-theme, find which symbols match (done in scoring phase)
    # Store constituent_themes as empty for now — scoring uses semantic matching
    for theme in meta_themes:
        theme["constituent_themes"] = []
        theme["representative_symbols"] = []

    return meta_themes


def store_meta_themes(engine, meta_themes):
    """Store canonical meta-themes in database."""
    with engine.connect() as conn:
        for theme in meta_themes:
            conn.execute(text("""
                INSERT INTO meta_themes
                    (name, description, constituent_themes, momentum)
                VALUES
                    (:name, :description, :constituent_themes, :momentum)
                ON CONFLICT (name) DO UPDATE SET
                    description        = EXCLUDED.description,
                    constituent_themes = EXCLUDED.constituent_themes,
                    momentum           = EXCLUDED.momentum,
                    updated_at         = NOW()
            """), {
                "name":               theme["name"],
                "description":        theme.get("description", ""),
                "constituent_themes": json.dumps({
                    "raw_themes":           theme.get("constituent_themes", []),
                    "representative_symbols": theme.get("representative_symbols", []),
                    "sectors_present":      theme.get("sectors_present", []),
                    "momentum_evidence":    theme.get("momentum_evidence", ""),
                }),
                "momentum":           theme.get("momentum", "stable"),
            })
        conn.commit()
    print(f"  ✓ Stored {len(meta_themes)} meta-themes")


# ─────────────────────────────────────────────────────────────
# PHASE 3: SCORE EACH STOCK AGAINST EACH META-THEME
# ─────────────────────────────────────────────────────────────

def score_stock_alignments(engine, client):
    """
    Score each stock's alignment to each meta-theme using semantic embeddings.

    Method:
    1. Build a weighted-average embedding per stock across all their filings
       (recency × narrative_strength weighted)
    2. Compute cosine similarity between every stock embedding and every meta-theme
       embedding — producing a (stocks × meta-themes) similarity matrix
    3. Z-score normalise PER COLUMN (per meta-theme) so alignment becomes a
       relative signal: "this company talks about this theme more than average"
       Financial filings all use similar language, so absolute cosine similarity
       clusters everything together. Z-scoring reveals genuine specialisation.
    4. Store alignment_score as percentile rank (0–1) within each meta-theme,
       only for stocks in the top 30% (z-score > ~0.5)

    Requires embedding_builder.py to have been run first.
    """
    print("\n📐 Scoring stock–theme alignments (semantic embeddings + z-score)...")

    # Load meta-theme embeddings
    with engine.connect() as conn:
        mt_rows = conn.execute(text("""
            SELECT id, name, momentum, embedding
            FROM meta_themes
            WHERE embedding IS NOT NULL
        """)).fetchall()

    if not mt_rows:
        print("⚠️  No meta-theme embeddings found. Run embedding_builder.py first.")
        return

    mt_ids    = [r[0] for r in mt_rows]
    mt_names  = [r[1] for r in mt_rows]
    mt_matrix = np.array([
        json.loads(r[3]) if isinstance(r[3], str) else r[3]
        for r in mt_rows
    ], dtype=np.float32)

    print(f"  {len(mt_ids)} meta-themes loaded")

    # Load per-stock filing themes with embeddings, most recent first
    with engine.connect() as conn:
        ft_rows = conn.execute(text("""
            SELECT symbol, filing_date, trajectory, narrative_strength, embedding
            FROM filing_themes
            WHERE embedding IS NOT NULL
            ORDER BY symbol, filing_date DESC
        """)).fetchall()

    if not ft_rows:
        print("⚠️  No filing embeddings found. Run embedding_builder.py first.")
        return

    # Group by symbol, preserving recency order
    stock_filings = defaultdict(list)
    for sym, fdate, traj, strength, emb_json in ft_rows:
        emb = np.array(
            json.loads(emb_json) if isinstance(emb_json, str) else emb_json,
            dtype=np.float32
        )
        stock_filings[sym].append({
            "date":      fdate,
            "trajectory": traj,
            "strength":  float(strength) if strength else 0.5,
            "embedding": emb,
        })

    symbols = list(stock_filings.keys())
    total_stocks = len(symbols)
    print(f"  {total_stocks} stocks — building stock embeddings...")

    def recency_weights(n):
        """Exponential decay: most recent filing weighted most heavily."""
        w = np.array([0.7 ** i for i in range(n)], dtype=np.float32)
        return w / w.sum()

    # Build stock embedding matrix: (n_stocks, 384)
    stock_matrix = np.zeros((total_stocks, mt_matrix.shape[1]), dtype=np.float32)
    # Also build recent/older split for trajectory detection
    recent_matrix = np.zeros_like(stock_matrix)
    older_matrix  = np.zeros_like(stock_matrix)
    per_filing_sims_all = {}  # symbol → array of per-filing sims (n_filings, n_themes)

    for idx, symbol in enumerate(symbols):
        filings = stock_filings[symbol]
        n = len(filings)
        w = recency_weights(n)
        strengths = np.array([f["strength"] for f in filings], dtype=np.float32)
        filing_embs = np.stack([f["embedding"] for f in filings])  # (n, 384)

        cw = w * strengths
        cw /= cw.sum() + 1e-8

        stock_emb = (filing_embs * cw[:, None]).sum(axis=0)
        norm = np.linalg.norm(stock_emb)
        stock_matrix[idx] = stock_emb / norm if norm > 1e-8 else stock_emb

        recent_emb = filing_embs[:min(2, n)].mean(axis=0)
        rn = np.linalg.norm(recent_emb)
        recent_matrix[idx] = recent_emb / rn if rn > 1e-8 else recent_emb

        if n > 2:
            older_emb = filing_embs[2:].mean(axis=0)
            on = np.linalg.norm(older_emb)
            older_matrix[idx] = older_emb / on if on > 1e-8 else older_emb
        else:
            older_matrix[idx] = recent_matrix[idx]

        per_filing_sims_all[symbol] = filing_embs @ mt_matrix.T  # (n, n_themes)

    print(f"  Computing similarity matrix ({total_stocks} × {len(mt_ids)})...")

    # Full cosine similarity matrix: (n_stocks, n_meta_themes)
    sim_matrix    = stock_matrix  @ mt_matrix.T
    recent_sims   = recent_matrix @ mt_matrix.T
    older_sims    = older_matrix  @ mt_matrix.T

    # Z-score normalise per meta-theme (per column)
    # This converts absolute similarities into relative standing within each theme
    col_mean = sim_matrix.mean(axis=0)   # shape: (n_themes,)
    col_std  = sim_matrix.std(axis=0)
    col_std  = np.where(col_std < 1e-8, 1.0, col_std)  # avoid divide-by-zero
    z_matrix = (sim_matrix - col_mean) / col_std        # (n_stocks, n_themes)

    # Convert z-scores to percentile rank within each meta-theme
    # Companies in top 30% (z > ~0.52) are considered meaningfully aligned
    from scipy.stats import norm as _norm
    percentile_matrix = _norm.cdf(z_matrix)  # 0–1, 0.5 = average company

    PERCENTILE_THRESHOLD = 0.70  # top 30% — genuinely above-average alignment

    print(f"  Storing alignments (threshold: top {int((1-PERCENTILE_THRESHOLD)*100)}%)...")

    engine_conn = engine.connect()
    stored = 0

    for idx, symbol in enumerate(symbols):
        filings = stock_filings[symbol]
        n = len(filings)

        for j, mt_id in enumerate(mt_ids):
            pct = float(percentile_matrix[idx, j])
            if pct < PERCENTILE_THRESHOLD:
                continue

            # Raw cosine sim as the displayed score (0-1 range, meaningful magnitude)
            raw_sim = float(sim_matrix[idx, j])

            # Trajectory from embedding drift
            r_sim = float(recent_sims[idx, j])
            o_sim = float(older_sims[idx, j])
            if r_sim > o_sim * 1.10:
                traj = "accelerating"
            elif r_sim < o_sim * 0.90:
                traj = "decelerating"
            else:
                traj = "stable"

            # Per-filing similarity scores
            per_sims = [round(float(per_filing_sims_all[symbol][fi, j]), 4)
                        for fi in range(n)]

            engine_conn.execute(text("""
                INSERT INTO stock_theme_alignment
                    (symbol, meta_theme_id, alignment_score, trajectory, quarter_scores)
                VALUES
                    (:symbol, :meta_theme_id, :score, :trajectory, :quarter_scores)
                ON CONFLICT (symbol, meta_theme_id) DO UPDATE SET
                    alignment_score = EXCLUDED.alignment_score,
                    trajectory      = EXCLUDED.trajectory,
                    quarter_scores  = EXCLUDED.quarter_scores,
                    updated_at      = NOW()
            """), {
                "symbol":         symbol,
                "meta_theme_id":  mt_id,
                "score":          round(raw_sim, 4),
                "trajectory":     traj,
                "quarter_scores": json.dumps(per_sims),
            })
            stored += 1

    engine_conn.commit()
    engine_conn.close()

    # Update company_count on meta_themes
    with engine.connect() as conn:
        conn.execute(text("""
            UPDATE meta_themes mt SET
                company_count = (
                    SELECT COUNT(DISTINCT symbol)
                    FROM stock_theme_alignment sta
                    WHERE sta.meta_theme_id = mt.id
                )
        """))
        conn.commit()

    print(f"\n  ✓ {stored} alignments stored | {total_stocks} stocks | {len(mt_ids)} meta-themes")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def run_meta_theme_build():
    engine = get_engine()
    client = Anthropic()

    print("=" * 70)
    print("PHASE 2 — META-THEME CLUSTERING")
    print("=" * 70)

    meta_themes = build_meta_themes(engine, client)
    if not meta_themes:
        return

    store_meta_themes(engine, meta_themes)

    print("\n" + "=" * 70)
    print("PHASE 3 — STOCK ALIGNMENT SCORING")
    print("=" * 70)

    score_stock_alignments(engine, client)

    print("\n" + "=" * 70)
    print("✅ META-NARRATIVE BUILD COMPLETE")
    print("=" * 70)

    # Quick summary
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT name, company_count, momentum
            FROM meta_themes
            ORDER BY company_count DESC
            LIMIT 20
        """))
        print("\nTop Meta-Themes by Company Count:")
        print(f"  {'Theme':<40} {'Companies':>10} {'Momentum':<15}")
        print("  " + "-" * 67)
        for row in result:
            print(f"  {row[0]:<40} {row[1] or 0:>10} {row[2] or 'stable':<15}")


if __name__ == "__main__":
    run_meta_theme_build()
