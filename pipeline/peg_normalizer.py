"""
Sustainable-growth PEG — fixes a flattered core input.

Yahoo's pegRatio divides PE by RECENT trailing earnings growth, so a one-off
spike produces a fantasy PEG: HWM 2026-07 showed PEG 0.8 (forward PE 45 ÷ a
69% cyclical-recovery year) while the defensible number was ~2 (÷ ~20%
durable growth). Jacobs showed PEG 0.4 off spin-off-distorted comps. PEG is
50% of the value blend — these distortions moved the board.

Fix, using only data we already store:
    sustainable_growth = MIN( trailing 1y earnings growth,
                              3y earnings CAGR from fundamentals_history )
    peg_ratio          = pe_forward / (sustainable_growth * 100)

The MIN mechanically kills one-off spikes and dirty comps: they inflate the
1y number but not the multi-year CAGR. Annual earnings are derived as
revenue × net_margin from fundamentals_history (period_type 'A').

Vendor PEG is preserved in peg_vendor for audit. Runs after every
fundamentals refresh; NULL when no defensible growth exists (unchanged
behaviour — the value blend already handles missing PEG).
"""
from sqlalchemy import text


def _cagr(first: float, last: float, years: float):
    if first is None or last is None or first <= 0 or last <= 0 or years <= 0:
        return None
    return (last / first) ** (1.0 / years) - 1.0


def recompute_pegs(engine) -> dict:
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE fundamentals ADD COLUMN IF NOT EXISTS peg_vendor NUMERIC(12,2)"))

    with engine.connect() as conn:
        funds = conn.execute(text("""
            SELECT symbol, pe_forward, earnings_growth_yoy, peg_ratio, peg_vendor
            FROM fundamentals
        """)).fetchall()
        hist = conn.execute(text("""
            SELECT symbol, period_end, revenue, net_margin
            FROM fundamentals_history
            WHERE period_type = 'A' AND revenue IS NOT NULL AND net_margin IS NOT NULL
            ORDER BY symbol, period_end
        """)).fetchall()

    earnings_by_sym: dict[str, list] = {}
    for sym, pend, rev, nm in hist:
        e = float(rev) * float(nm)
        earnings_by_sym.setdefault(sym, []).append((pend, e))

    updates, stats = [], {"normalized": 0, "capped_by_cagr": 0, "nulled": 0, "no_history": 0}
    for sym, pe_fwd, g1, peg_now, peg_vendor_stored in funds:
        # keep the vendor's number for audit (first run captures current value)
        vendor = peg_vendor_stored if peg_vendor_stored is not None else peg_now

        g1 = float(g1) if g1 is not None else None
        series = earnings_by_sym.get(sym, [])

        g3 = None
        if len(series) >= 3:
            # last 3–4 annual points; positive endpoints required
            pts = series[-4:]
            years = (pts[-1][0] - pts[0][0]).days / 365.25
            g3 = _cagr(pts[0][1], pts[-1][1], years)

        # Current growth must itself be positive — a shrinking company gets no
        # PEG resurrection from its happier multi-year past (LDOS: -9.6% now,
        # 28% 3y CAGR, first draft emitted a flattering 0.29).
        if g1 is not None and g1 > 0 and g3 is not None and g3 > 0:
            growth = min(g1, g3)
            stats["capped_by_cagr" if g3 < g1 else "normalized"] += 1
        elif g1 is not None and g1 > 0 and g3 is None:
            growth = g1               # no history — status quo behaviour
            stats["no_history"] += 1
        else:
            growth = None
            stats["nulled"] += 1

        peg = None
        if growth and pe_fwd and float(pe_fwd) > 0:
            peg = round(float(pe_fwd) / (growth * 100), 2)
            if peg < 0 or peg > 99:
                peg = None
        updates.append({"s": sym, "peg": peg, "vendor": vendor})

    CHUNK = 150
    for i in range(0, len(updates), CHUNK):
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE fundamentals SET peg_ratio = :peg, peg_vendor = :vendor
                WHERE symbol = :s
            """), updates[i:i + CHUNK])

    print(f"PEG normalization: {stats}")
    return stats


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    from pipeline.hidden_gem_scorer import get_engine
    recompute_pegs(get_engine())
