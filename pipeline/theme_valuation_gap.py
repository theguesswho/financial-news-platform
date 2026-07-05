"""
Theme-relative valuation gap — the "Dell detector".

The core mispricing this platform hunts: a stock deeply exposed to an
accelerating structural theme, still priced at its legacy-category multiple
(Dell 2023: real AI-server exposure, laptop-maker valuation).

For each stock this computes, per strongly-aligned theme:
  - the peer set (other stocks aligned >= PEER_ALIGNMENT to the same theme)
  - the peer median forward PE and EV/EBITDA
  - the stock's discount/premium to those medians

Pure SQL + arithmetic over existing tables (stock_theme_alignment,
meta_themes, fundamentals) — no LLM cost. Refreshed daily by the scheduler.
"""
from statistics import median

from sqlalchemy import text

STRONG_ALIGNMENT = 0.40   # LLM-judged exposure: stock genuinely exposed
PEER_ALIGNMENT   = 0.40   # peers used for the valuation benchmark
MIN_PEERS        = 3      # below this the median is noise
TOP_THEMES       = 3      # narratives stored per stock


def create_table(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS theme_valuation_gaps (
                id              SERIAL PRIMARY KEY,
                symbol          VARCHAR(10) NOT NULL,
                meta_theme_id   INTEGER NOT NULL,
                theme_name      VARCHAR(200),
                theme_momentum  VARCHAR(20),
                alignment_score DOUBLE PRECISION,
                peer_count      INTEGER,
                stock_pe_fwd    NUMERIC(12,2),
                peer_median_pe  NUMERIC(12,2),
                pe_discount     NUMERIC(10,4),   -- 0.30 = 30% cheaper than theme peers
                stock_ev_ebitda NUMERIC(12,2),
                peer_median_ev  NUMERIC(12,2),
                ev_discount     NUMERIC(10,4),
                updated_at      TIMESTAMP DEFAULT NOW(),
                UNIQUE (symbol, meta_theme_id)
            )
        """))


def compute_theme_gaps(engine) -> dict:
    """Recompute the full table. Idempotent; replaces all rows each run."""
    create_table(engine)

    with engine.connect() as conn:
        # LLM-judged exposures to accelerating active narratives (the brain) —
        # a discount to peers in a declining narrative is not a signal
        alignments = conn.execute(text("""
            SELECT ne.symbol, ne.narrative_id, nar.name, nar.momentum,
                   ne.exposure
            FROM narrative_exposures ne
            JOIN narratives nar ON nar.id = ne.narrative_id
            WHERE ne.exposure >= :strong
              AND nar.status = 'active'
              AND nar.momentum = 'accelerating'
            ORDER BY ne.symbol, ne.exposure DESC
        """), {"strong": STRONG_ALIGNMENT}).fetchall()

        # Peer pools per narrative
        peers_rows = conn.execute(text("""
            SELECT ne.narrative_id, ne.symbol,
                   f.pe_forward, f.ev_to_ebitda
            FROM narrative_exposures ne
            JOIN fundamentals f ON f.symbol = ne.symbol
            WHERE ne.exposure >= :peer
        """), {"peer": PEER_ALIGNMENT}).fetchall()

        fund_rows = conn.execute(text(
            "SELECT symbol, pe_forward, ev_to_ebitda FROM fundamentals"
        )).fetchall()

    theme_peers: dict[int, list] = {}
    for tid, sym, pe, ev in peers_rows:
        theme_peers.setdefault(tid, []).append((sym, pe, ev))

    funds = {r[0]: (r[1], r[2]) for r in fund_rows}

    # Keep top N themes per stock
    per_stock: dict[str, list] = {}
    for sym, tid, name, momentum, align in alignments:
        bucket = per_stock.setdefault(sym, [])
        if len(bucket) < TOP_THEMES:
            bucket.append((tid, name, momentum, align))

    rows = []
    for sym, themes in per_stock.items():
        pe_s, ev_s = funds.get(sym, (None, None))
        for tid, name, momentum, align in themes:
            pool = [(s, pe, ev) for s, pe, ev in theme_peers.get(tid, []) if s != sym]
            pe_pool = [float(pe) for _, pe, _ in pool if pe is not None and 0 < float(pe) < 150]
            ev_pool = [float(ev) for _, _, ev in pool if ev is not None and 0 < float(ev) < 100]
            if len(pe_pool) < MIN_PEERS and len(ev_pool) < MIN_PEERS:
                continue

            med_pe = median(pe_pool) if len(pe_pool) >= MIN_PEERS else None
            med_ev = median(ev_pool) if len(ev_pool) >= MIN_PEERS else None

            pe_disc = None
            if med_pe and pe_s and 0 < float(pe_s) < 150:
                pe_disc = round(1 - float(pe_s) / med_pe, 4)
            ev_disc = None
            if med_ev and ev_s and 0 < float(ev_s) < 100:
                ev_disc = round(1 - float(ev_s) / med_ev, 4)

            rows.append({
                "symbol": sym, "tid": tid, "name": name, "momentum": momentum,
                "align": round(float(align), 4),
                "peers": max(len(pe_pool), len(ev_pool)),
                "pe_s": round(float(pe_s), 2) if pe_s else None,
                "med_pe": round(med_pe, 2) if med_pe else None,
                "pe_disc": pe_disc,
                "ev_s": round(float(ev_s), 2) if ev_s else None,
                "med_ev": round(med_ev, 2) if med_ev else None,
                "ev_disc": ev_disc,
            })

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM theme_valuation_gaps"))
        for r in rows:
            conn.execute(text("""
                INSERT INTO theme_valuation_gaps
                    (symbol, meta_theme_id, theme_name, theme_momentum,
                     alignment_score, peer_count,
                     stock_pe_fwd, peer_median_pe, pe_discount,
                     stock_ev_ebitda, peer_median_ev, ev_discount, updated_at)
                VALUES
                    (:symbol, :tid, :name, :momentum, :align, :peers,
                     :pe_s, :med_pe, :pe_disc, :ev_s, :med_ev, :ev_disc, NOW())
                ON CONFLICT (symbol, meta_theme_id) DO UPDATE SET
                    alignment_score = EXCLUDED.alignment_score,
                    peer_count      = EXCLUDED.peer_count,
                    stock_pe_fwd    = EXCLUDED.stock_pe_fwd,
                    peer_median_pe  = EXCLUDED.peer_median_pe,
                    pe_discount     = EXCLUDED.pe_discount,
                    stock_ev_ebitda = EXCLUDED.stock_ev_ebitda,
                    peer_median_ev  = EXCLUDED.peer_median_ev,
                    ev_discount     = EXCLUDED.ev_discount,
                    updated_at      = NOW()
            """), r)

    print(f"Theme valuation gaps: {len(rows)} stock-theme pairs "
          f"({len(per_stock)} stocks)")
    return {"pairs": len(rows), "stocks": len(per_stock)}


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    from pipeline.hidden_gem_scorer import get_engine
    compute_theme_gaps(get_engine())
