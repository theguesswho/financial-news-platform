"""
Quality v3 + shrunk value — OFFLINE calculator (QUALITY_DURABILITY_SPEC P3).
Nothing here touches live scoring; compute_p3_universe() produces the
candidate scores that feed the before/after board diff for user sign-off.

Quality (per metric, over up to 10 canonical annual years + TTM):
  level       — TTM (or latest FY when TTM absent), winsorized per spec
  slope       — recency-weighted least squares over the annual road
  consistency — 1 / (1 + normalized MAD of residuals around the trend)
  cycle_pos   — TTM vs own 10y peak (recovering-vs-new-highs signal)

Sector metric profiles (spec 4b): STANDARD / BANK / REIT — metric sets
swapped, weights renormalized, percentiles within profile groups.

Value shrinkage (spec 4c): industry and sector percentiles blended by
w = n/(n+8).

Cyclical doctrine (user 2026-08-09): high residual volatility flags a
stock CYCLICAL; a cyclical is board-eligible only when PUNISHED (TTM in
the bottom third of its own 10y range, or deep price drawdown) — the
supercycle exception lives in the story layer, not here.
"""
import math
from statistics import median

from sqlalchemy import text

SHRINK_K = 8
CYCLICAL_MAD_THRESHOLD = 0.15   # normalized residual vol above this = cyclical (user lean 2026-08-09: EVR-class oscillation must flag)
PUNISHED_RANGE_POSITION = 0.33  # TTM in bottom third of own 10y range

BANK_INDUSTRIES = ("Banks", "Bank", "Insurance", "Credit Services",
                   "Financial Conglomerates", "Mortgage")
REIT_INDUSTRIES = ("REIT",)


def profile_for(industry: str | None) -> str:
    ind = industry or ""
    if any(k in ind for k in REIT_INDUSTRIES):
        return "REIT"
    if any(k in ind for k in BANK_INDUSTRIES):
        return "BANK"
    return "STANDARD"


def trend_fit(series: list) -> dict | None:
    """series: chronological [(year_index, value)]. Returns level/slope/
    consistency/cycle_pos components, or None if under 3 points."""
    pts = [(i, v) for i, v in series if v is not None]
    if len(pts) < 3:
        return None
    # recency weights: newest year weight 1.0, halving every 4 years back
    n = len(pts)
    ws = [0.5 ** ((n - 1 - k) / 4) for k in range(n)]
    sw = sum(ws)
    mx = sum(w * p[0] for w, p in zip(ws, pts)) / sw
    my = sum(w * p[1] for w, p in zip(ws, pts)) / sw
    sxx = sum(w * (p[0] - mx) ** 2 for w, p in zip(ws, pts))
    if sxx == 0:
        return None
    slope = sum(w * (p[0] - mx) * (p[1] - my) for w, p in zip(ws, pts)) / sxx
    resid = [p[1] - (my + slope * (p[0] - mx)) for p in pts]
    mad = median(abs(r) for r in resid)
    scale = max(abs(my), 0.02)
    nmad = mad / scale
    values = [p[1] for p in pts]
    vmin, vmax = min(values), max(values)
    latest = values[-1]
    cycle_pos = (latest - vmin) / (vmax - vmin) if vmax > vmin else 0.5
    return {"slope": slope, "nmad": nmad, "cycle_pos": cycle_pos,
            "latest": latest, "peak": vmax, "n": n}


def _pct(vals, v, higher_better=True):
    good = sorted(x for x in vals if x is not None)
    if not good or v is None:
        return None
    below = sum(1 for x in good if (x < v if higher_better else x > v))
    return (below + 0.5) / len(good)


def compute_p3_universe(engine) -> dict:
    """Full offline computation. Returns {symbol: {...components...}}."""
    with engine.connect() as conn:
        fund = {r[0]: r for r in conn.execute(text("""
            SELECT symbol, sector, industry, pe_forward, ev_to_ebitda,
                   price_to_fcf, price_to_book, market_cap, price_vs_52w_high
            FROM fundamentals""")).fetchall()}
        ttm = {r[0]: r for r in conn.execute(text("""
            SELECT symbol, roic, roe, gross_margin, op_margin, net_margin
            FROM fundamentals_ttm""")).fetchall()}
        annual = {}
        for r in conn.execute(text("""
            SELECT symbol, fiscal_year, revenue, op_margin, net_margin, fcf,
                   roic, roe, da
            FROM fundamentals_annual ORDER BY symbol, fiscal_year""")).fetchall():
            annual.setdefault(r[0], []).append(r)

    def wins(v, lim=1.5):
        if v is None:
            return None
        v = float(v)
        return None if abs(v) > lim else v

    out = {}
    for sym, f in fund.items():
        # Row hygiene (fiscal-calendar audit 2026-08-10, V2_CONSIDERATIONS):
        # 1) drop no-revenue stub rows (LHX's 2019 L3/Harris transition);
        # 2) key each fiscal year to the calendar year it mostly covers —
        #    a 52/53-week year ending Jan 1-14 belongs to the PRIOR year
        #    (LHX FY2020 ended 2021-01-01 and used to collide with FY2021,
        #    silently dropping a real year; 19 symbols had this);
        # 3) on residual collision keep the better-populated row;
        # 4) fake-zero guard: revenue present but ROIC and op margin BOTH
        #    exactly zero is vendor zero-fill, not a reading — treat the
        #    zeroed metrics as missing (a fake 0 ROIC year manufactured a
        #    fake improvement trend that inflated TXT's quality).
        raw_rows = [r for r in annual.get(sym, []) if r[2] and float(r[2]) > 0]

        def _fy_key(d):
            s = str(d)
            y, m, day = int(s[:4]), int(s[5:7]), int(s[8:10])
            return y - 1 if (m == 1 and day <= 14) else y

        def _filled(r):
            return sum(1 for v in (r[3], r[5], r[6]) if v is not None
                       and float(v) != 0)

        by_year = {}
        for r in raw_rows:
            k = _fy_key(r[1])
            if k not in by_year or _filled(r) > _filled(by_year[k]):
                by_year[k] = r

        def _clean(r):
            if (r[6] is not None and float(r[6]) == 0
                    and r[3] is not None and float(r[3]) == 0):
                r = list(r); r[3] = None; r[6] = None; r = tuple(r)
            return r
        rows = [_clean(by_year[y]) for y in sorted(by_year)][-10:]
        if not rows:
            continue
        t = ttm.get(sym)
        prof = profile_for(f[2])

        # metric series by profile
        if prof == "BANK":
            metrics = {
                "roe": [(i, wins(r[7])) for i, r in enumerate(rows)],
                "net_margin": [(i, wins(r[4], 1.0)) for i, r in enumerate(rows)],
                "revenue": [(i, math.log(float(r[2])) if r[2] and float(r[2]) > 0 else None)
                            for i, r in enumerate(rows)],
            }
            ttm_level = wins(t[2]) if t else None      # roe ttm
        elif prof == "REIT":
            ffo = [(i, (float(r[4] or 0) * float(r[2] or 0) + float(r[8] or 0)) or None)
                   for i, r in enumerate(rows)]
            ffo = [(i, math.log(v) if v and v > 0 else None) for i, v in ffo]
            metrics = {
                "ffo": ffo,
                "revenue": [(i, math.log(float(r[2])) if r[2] and float(r[2]) > 0 else None)
                            for i, r in enumerate(rows)],
            }
            ttm_level = wins(t[5], 1.0) if t else None  # net margin as ttm proxy
        else:
            metrics = {
                "roic": [(i, wins(r[6])) for i, r in enumerate(rows)],
                "op_margin": [(i, wins(r[3], 1.0)) for i, r in enumerate(rows)],
                "fcf": [(i, math.log(float(r[5])) if r[5] and float(r[5]) > 0 else None)
                        for i, r in enumerate(rows)],
                "revenue": [(i, math.log(float(r[2])) if r[2] and float(r[2]) > 0 else None)
                            for i, r in enumerate(rows)],
            }
            ttm_level = wins(t[1]) if t else None       # roic ttm

        fits = {k: trend_fit(v) for k, v in metrics.items()}
        fits = {k: v for k, v in fits.items() if v}
        if not fits:
            continue
        # aggregate components across the profile's metrics
        slope_score = sum(1 for v in fits.values() if v["slope"] > 0) / len(fits)
        nmad_avg = sum(v["nmad"] for v in fits.values()) / len(fits)
        consistency = 1 / (1 + 3 * nmad_avg)
        primary = fits.get("roic") or fits.get("roe") or fits.get("ffo") \
            or next(iter(fits.values()))
        cycle_pos = primary["cycle_pos"]
        level = ttm_level if ttm_level is not None else primary["latest"]
        cyclical = nmad_avg > CYCLICAL_MAD_THRESHOLD
        punished = cycle_pos <= PUNISHED_RANGE_POSITION or \
            (f[8] is not None and float(f[8]) <= 0.75)  # >=25% off high
        out[sym] = {"profile": prof, "level": level, "slope_score": slope_score,
                    "consistency": consistency, "cycle_pos": cycle_pos,
                    "nmad": round(nmad_avg, 3), "cyclical": cyclical,
                    "punished": punished, "sector": f[1], "industry": f[2],
                    "pe_forward": f[3], "ev_to_ebitda": f[4],
                    "price_to_fcf": f[5], "price_to_book": f[6]}

    # ── quality percentiles within profile groups + composition ─────────────
    for prof in ("STANDARD", "BANK", "REIT"):
        grp = [s for s, d in out.items() if d["profile"] == prof]
        levels = [out[s]["level"] for s in grp]
        for s in grp:
            lp = _pct(levels, out[s]["level"]) or 0.5
            d = out[s]
            d["quality_v3"] = round(max(0.05,
                0.40 * lp + 0.20 * d["slope_score"]
                + 0.30 * d["consistency"] + 0.10 * (1 - d["cycle_pos"] * d["cyclical"])), 4)

    # ── value with hierarchical shrinkage (profile-aware metric sets) ───────
    by_ind, by_sec = {}, {}
    for s, d in out.items():
        by_ind.setdefault(d["industry"], []).append(s)
        by_sec.setdefault(d["sector"], []).append(s)

    def value_pct(s, group):
        d = out[s]
        if d["profile"] == "BANK":
            specs = [("pe_forward", .60), ("price_to_book", .40)]
        elif d["profile"] == "REIT":
            specs = [("price_to_fcf", .60), ("pe_forward", .40)]
        else:
            specs = [("pe_forward", .45), ("ev_to_ebitda", .35), ("price_to_fcf", .20)]
        parts, wts = [], []
        for k, w in specs:
            vals = [float(out[g][k]) for g in group
                    if out[g][k] is not None and float(out[g][k]) > 0]
            v = d[k]
            p = _pct(vals, float(v), higher_better=False) if v and float(v) > 0 else None
            if p is not None:
                parts.append(p * w)
                wts.append(w)
        return sum(parts) / sum(wts) if wts else None

    for s, d in out.items():
        vi = value_pct(s, by_ind.get(d["industry"], [s]))
        vs = value_pct(s, by_sec.get(d["sector"], [s]))
        n = len(by_ind.get(d["industry"], []))
        w = n / (n + SHRINK_K)
        if vi is None and vs is None:
            d["value_v3"] = None
            continue
        vi = vi if vi is not None else vs
        vs = vs if vs is not None else vi
        d["value_v3"] = round(max(0.05, w * vi + (1 - w) * vs), 4)
    return out


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    from pipeline.hidden_gem_scorer import get_engine
    res = compute_p3_universe(get_engine())
    for s in ("EVR", "GDDY", "HUBB", "ERIE", "NI", "CDE", "JPM", "O"):
        print(s, res.get(s))
