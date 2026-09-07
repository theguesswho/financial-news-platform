"""Freeze diff, V3 #20/#21 (2026-09-07). Snapshots (logs/freeze_20260906):
  before : 2026-09-06 21:18 SGT — historical_metrics dead, growth on Yahoo
  mid    : 2026-09-06 21:44 SGT — after #21 refresh only (same evening)
  mid2   : 2026-09-07 18:15 SGT — after the 06:00 UTC daily (Yahoo re-fetch,
           prices moved), BEFORE the FMP growth re-home
  after  : 2026-09-07 ~19:30 SGT — after #21 + #20
  before->mid  = #21 alone;  mid->mid2 = one day of drift (not ours);
  mid2->after  = #20 alone;  before->after = total."""
import json, sys, os
sys.path.insert(0, "/Users/eha/Desktop/financial-news-platform")
from pipeline.tiers import tier_for, BOARD_EXIT, WATCH
D = os.path.dirname(os.path.abspath(__file__))
def load(tag):
    d = json.load(open(f"{D}/snap_{tag}.json")); d["res"] = {r["symbol"]: r for r in d["results"]}; return d
def gem(d, s): r = d["res"].get(s); return r["hidden_gem_score"] if r else None
def mult(r):
    if r is None: return None
    rg = r["revenue_growth"] or 0.0; eg = r["earnings_growth"] or 0.0; n = r["narrative_score"]
    if r["divestiture"]: return 1.0
    if rg < 0 and eg < 0: return 0.5
    if eg < 0 and rg >= 0 and n < 0.40: return 0.75
    return 1.0
def t10(x): return f"{x*10:.2f}" if x is not None else "—"
def diff(ta, tb, full=True):
    a, b = load(ta), load(tb)
    syms = sorted(set(a["res"]) | set(b["res"]))
    print(f"\n==================== {ta} -> {tb} ====================")
    ba = {s for s in a["res"] if gem(a, s) > WATCH}; bb = {s for s in b["res"] if gem(b, s) > WATCH}
    print(f"board (gem > WATCH {WATCH}): {len(ba)} -> {len(bb)}   [exit line BOARD_EXIT {BOARD_EXIT}]")
    print("ENTER:", [(s, t10(gem(a, s)), t10(gem(b, s)), tier_for(gem(b, s))) for s in sorted(bb - ba)])
    print("DROP below WATCH:", [(s, t10(gem(a, s)), t10(gem(b, s))) for s in sorted(ba - bb)])
    print("  of which below BOARD_EXIT (true exits):", [s for s in sorted(ba - bb) if gem(b, s) is not None and gem(b, s) <= BOARD_EXIT])
    print("TIER FLIPS (names on board either side):", [(s, tier_for(gem(a, s)), tier_for(gem(b, s)), t10(gem(a, s)), t10(gem(b, s))) for s in sorted(ba | bb) if tier_for(gem(a, s)) != tier_for(gem(b, s))])
    mults = [(s, mult(a["res"][s]), mult(b["res"][s]), t10(gem(a, s)), t10(gem(b, s)), a["res"][s]["revenue_growth"], b["res"][s]["revenue_growth"], a["res"][s]["earnings_growth"], b["res"][s]["earnings_growth"])
             for s in syms if s in a["res"] and s in b["res"] and mult(a["res"][s]) != mult(b["res"][s])]
    print(f"GROWTH MULTIPLIER CHANGED: {len(mults)} (harsher {sum(1 for m in mults if m[2] < m[1])}, softer {sum(1 for m in mults if m[2] > m[1])})")
    if full:
        for m in mults: print(f"    {m[0]:6} {m[1]}->{m[2]}  gem {m[3]}->{m[4]}  rev {m[5]}->{m[6]}  earn {m[7]}->{m[8]}")
    hm = {s: (a["hm"].get(s, {}).get("rev_ttm"), b["hm"].get(s, {}).get("rev_ttm")) for s in syms if a["hm"].get(s, {}).get("rev_ttm") != b["hm"].get(s, {}).get("rev_ttm")}
    print(f"TTM revenue (historical_metrics) changed: {len(hm)} names; had no rows before: {sum(1 for s in hm if s not in a['hm'])}")
    vals = [(s, a["res"][s].get("value_score"), b["res"][s].get("value_score")) for s in syms if s in a["res"] and s in b["res"] and a["res"][s].get("value_score") != b["res"][s].get("value_score")]
    print(f"VALUE LEG (scorer value_score, holds the P/S rank): moved {len(vals)}; of which with a TTM-revenue change: {sum(1 for v in vals if v[0] in hm)}")
    onb = [(s, t10(x), t10(y), t10(gem(a, s)), t10(gem(b, s)), a["hm"].get(s, {}).get("rev_ttm"), b["hm"].get(s, {}).get("rev_ttm")) for s, x, y in vals if s in (ba | bb)]
    print(f"  value_score moves on board names ({len(onb)}) [sym, value a->b, gem a->b, rev_ttm a->b]:")
    for o in (onb if full else onb[:15]): print("    ", o)
    v3 = [s for s in syms if s in a["p3"] and s in b["p3"] and a["p3"][s].get("value_v3") != b["p3"][s].get("value_v3")]
    print(f"  (P3 value_v3 — multiples-based, no historical_metrics input — moved {len(v3)}; price drift only)")
    big = sorted([(s, round(gem(a, s)*10, 2), round(gem(b, s)*10, 2)) for s in syms if s in a["res"] and s in b["res"] and abs(gem(a, s) - gem(b, s)) >= 0.02], key=lambda x: -abs(x[1]-x[2]))
    print(f"gem moved >= 0.2 (10-scale): {len(big)}", big[:30])
    return {"enter": sorted(bb - ba), "drop": sorted(ba - bb), "mults": mults, "vals": vals, "hm": hm}
if __name__ == "__main__":
    pairs = sys.argv[1:] or ["before", "mid", "mid2", "after"]
    for i in range(len(pairs) - 1): diff(pairs[i], pairs[i+1], full=("--brief" not in os.environ.get("DIFF_OPTS", "")))
    if len(pairs) > 2: diff(pairs[0], pairs[-1])
