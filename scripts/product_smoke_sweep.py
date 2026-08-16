#!/usr/bin/env python3
"""Pre-deploy smoke sweep for the product read API (roadmap step 3).

Hits every endpoint the promoted pages consume, plus /stocks/{symbol}
for the full covered universe, and runs the law-17 honesty pass over
EVERY edition date in the archive.

Law-17 pass: the web UI replaces edition sentences that claim "no
position" in a name the book actually holds (web/lib/api.ts
NO_POSITION_CLAIM). The regex's failure mode is a phrasing it hasn't
seen. This script casts a deliberately BROAD net over every
symbol-carrying edition text, then checks each catch against the strict
regex (ported verbatim). A broad-net catch in an open-lot name that the
strict regex misses is a reported gap -> fix the regex with a GENERAL
pattern (never a one-name patch).

Usage: python scripts/product_smoke_sweep.py [base_url]
Exit 0 = clean; exit 1 = failures found.
"""

import concurrent.futures as cf
import json
import re
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8010"

# --- strict regex: verbatim port of web/lib/api.ts NO_POSITION_CLAIM ---
STRICT = re.compile(
    r"[^.!?]*\b(?:we\s+(?:do\s*not|don'?t)\s+(?:hold|own)\b(?!\s+(?:up|back|off|out|on)\b)"
    r"|we\s+(?:do\s*not|don'?t)\s+have\s+(?:a\s+|any\s+)?(?:position|stake|holding|exposure|shares)"
    r"|(?:holds?|holding|have|has)\s+no\s+(?:position|stake|holding)"
    r"|no\s+position\s+(?:is\s+)?held"
    r"|not\s+(?:a\s+(?:current\s+)?(?:position|holding)\b"
    r"|(?:currently\s+|presently\s+)?(?:held|owned)\b"
    r"(?!\s+(?:up|back|off|out|on|down|steady|firm|together|the|a|an|any|much|its|their|his|her)\b)))"
    r"[^.!?]*[.!?]\s*",
    re.IGNORECASE,
)

# --- broad net: any sentence pairing a negation with position/holding
# vocabulary, either order. Intentionally over-catches; every catch is
# reviewed against the strict regex and (if strict misses) by a human. ---
NEG = r"(?:no|not|n't|never|without|zero|neither|nor|isn'?t|aren'?t|doesn'?t|don'?t|didn'?t|hasn'?t|haven'?t)"
POS = r"(?:position|positions|holding|holdings|hold|holds|held|own|owns|owned|stake|lot|lots|exposure|book)"
BROAD = re.compile(
    rf"[^.!?]*(?:\b{NEG}[^.!?]*?\b{POS}\b|\b{POS}\b[^.!?]*?\b{NEG})[^.!?]*[.!?]",
    re.IGNORECASE,
)

failures = []   # hard failures: non-200 (other than expected 404s), empty payloads
law17_gaps = [] # broad-net catches the strict regex missed, in open-lot names
law17_hits = [] # strict-regex matches (these get rewritten by the UI - informational)
notes = []


def get(path, timeout=60):
    url = BASE + path
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        return -1, str(e)


def check(path, status, body, allow_empty=False):
    if status != 200:
        failures.append(f"{path}: HTTP {status}" + (f" ({body})" if status == -1 else ""))
        return False
    if body is None or (not allow_empty and (body == {} or body == [])):
        failures.append(f"{path}: empty payload")
        return False
    return True


def null_share(obj):
    """Fraction of leaf values that are null."""
    total = nulls = 0
    stack = [obj]
    while stack:
        v = stack.pop()
        if isinstance(v, dict):
            stack.extend(v.values())
        elif isinstance(v, list):
            stack.extend(v)
        else:
            total += 1
            nulls += v is None
    return (nulls / total) if total else 1.0


t0 = time.time()

# ---------- 1. core endpoints ----------
st, board = get("/board")
check("/board", st, board)
symbols = [r["symbol"] for r in board.get("board", []) + board.get("off_board", [])] if isinstance(board, dict) else []
print(f"/board ok — universe {len(symbols)}")

st, scorecard = get("/board/scorecard")
check("/board/scorecard", st, scorecard)
open_lots = {}
for lot in (scorecard or {}).get("lots", []):
    if not lot.get("closed"):
        open_lots[lot["symbol"]] = open_lots.get(lot["symbol"], 0) + 1
print(f"/board/scorecard ok — {sum(open_lots.values())} open lots in {len(open_lots)} names")

for p in ["/narratives", "/narratives/landing"]:
    st, body = get(p)
    check(p, st, body)
print("/narratives + /narratives/landing ok")

# ---------- 2. every force page (narrative id + roster) ----------
st, narr = get("/narratives")
force_ids = []
if st == 200 and narr:
    force_ids = sorted({n["id"] for n in narr.get("library", []) if n.get("id") is not None})
for fid in force_ids:
    for p in (f"/narratives/{fid}", f"/narratives/{fid}/roster"):
        st, body = get(p, timeout=120)
        check(p, st, body)
print(f"force pages ok — {len(force_ids)} ids × 2 endpoints")

# ---------- 3. every edition date + law-17 pass ----------
st, latest = get("/reports/latest")
check("/reports/latest", st, latest)
dates = (latest or {}).get("dates", [])


def edition_texts(rep):
    """Yield (symbol, where, text) for every symbol-carrying text in an edition."""
    ts = rep.get("top_story") or {}
    if ts.get("symbol"):
        for f in ("headline", "body"):
            if ts.get(f):
                yield ts["symbol"], f"top_story.{f}", ts[f]
    for i, s in enumerate(rep.get("sections") or []):
        if s.get("symbol"):
            for f in ("headline", "body"):
                if s.get(f):
                    yield s["symbol"], f"sections[{i}].{f}", s[f]


for d in dates:
    st, rep = get(f"/reports/{d}")
    if not check(f"/reports/{d}", st, rep):
        continue
    for sym, where, text in edition_texts(rep):
        lots = open_lots.get(sym, 0)
        strict_m = STRICT.search(text)
        if strict_m and lots > 0:
            law17_hits.append((d, sym, where, strict_m.group(0).strip()))
        if lots > 0:
            for m in BROAD.finditer(text):
                sent = m.group(0).strip()
                if not STRICT.search(sent):
                    law17_gaps.append((d, sym, where, sent))
print(f"editions ok — {len(dates)} dates; law-17: {len(law17_hits)} strict hits, {len(law17_gaps)} broad-net catches to review")

# ---------- 4. every dossier ----------
def sweep_symbol(sym):
    st, body = get(f"/stocks/{sym}", timeout=120)
    if st != 200:
        return (sym, f"HTTP {st}", None)
    if not body:
        return (sym, "empty", None)
    ns = null_share(body)
    return (sym, "ok", ns)


null_heavy = []
with cf.ThreadPoolExecutor(max_workers=8) as ex:
    for sym, status_s, ns in ex.map(sweep_symbol, symbols):
        if status_s != "ok":
            failures.append(f"/stocks/{sym}: {status_s}")
        elif ns is not None and ns > 0.6:
            null_heavy.append((sym, round(ns, 2)))
print(f"dossiers swept — {len(symbols)} symbols, {len(null_heavy)} null-heavy (>60% null leaves)")

# expected 404s must actually 404
for p in ["/stocks/NOTASYMBOL", "/reports/1999-01-01"]:
    st, _ = get(p)
    if st != 404:
        failures.append(f"{p}: expected 404, got {st}")

# ---------- report ----------
print(f"\n=== sweep done in {time.time()-t0:.0f}s ===")
if null_heavy:
    print(f"null-heavy dossiers ({len(null_heavy)}):", null_heavy[:20], "..." if len(null_heavy) > 20 else "")
if law17_hits:
    print("\nlaw-17 STRICT hits (UI rewrites these — informational):")
    for d, sym, where, sent in law17_hits:
        print(f"  {d} {sym} {where}: {sent[:160]}")
if law17_gaps:
    print("\nlaw-17 BROAD-NET catches the strict regex MISSED (review each):")
    for d, sym, where, sent in law17_gaps:
        print(f"  {d} {sym} {where}: {sent[:200]}")
if failures:
    print(f"\nFAILURES ({len(failures)}):")
    for f in failures[:50]:
        print(" ", f)
    sys.exit(1)
print("\nno hard failures")
