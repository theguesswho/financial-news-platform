"""
The Narrative Map — attention hierarchy first, full accountability below
(user-approved redesign 2026-08-09).

Layer 1  THE MAP        — the 9 meta forces, sized by exposed board weight,
                          colored by momentum. 10-second world view.
Layer 2  WHAT MOVED     — salience-ranked cards from ANY level: board
                          weight x recent change decides attention, not
                          taxonomy position.
Layer 3  THE LIBRARY    — the complete parented tree as a compact index.

Company-scope stories are deliberately EXCLUDED here — they are dossiers
with predictions, a different object (own page planned).
Salience is deterministic: board weight (tier-weighted exposure) plus a
bonus for ledger-recorded change in the last 7 days and accelerating
momentum. No LLM at page load.
"""
import html
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv(override=True)
st.set_page_config(page_title="Narratives | FinResearch", page_icon="🧭", layout="wide")


@st.cache_resource
def _engine():
    from pipeline.hidden_gem_scorer import get_engine
    return get_engine()


def esc(s):
    return html.escape(str(s)) if s else ""


st.markdown("""
<style>
.nv-wrap { max-width: 980px; }
.nv-title { font-size: 28px; font-weight: 700; margin: 0 0 2px; }
.nv-sub { opacity: .55; font-size: 13.5px; margin-bottom: 18px; }
.nv-h2 { font-size: 13px; letter-spacing: .12em; text-transform: uppercase;
         opacity: .65; border-top: 1px solid rgba(128,128,128,.25);
         padding-top: 20px; margin: 26px 0 4px; font-weight: 600; }
.nv-map { display: flex; flex-wrap: wrap; gap: 10px; margin: 10px 0 6px; }
.nv-block { border-radius: 12px; padding: 12px 14px; min-width: 150px;
            border: 1px solid rgba(128,128,128,.25); flex-grow: 1; }
.nv-block.accelerating { background: rgba(22,163,74,.10); border-color: rgba(22,163,74,.45); }
.nv-block.stable { background: rgba(128,128,128,.07); }
.nv-block.decelerating { background: rgba(217,119,6,.10); border-color: rgba(217,119,6,.45); }
.nv-block h4 { margin: 0 0 4px; font-size: 14.5px; }
.nv-block .meta { font-size: 12px; opacity: .6; }
.nv-card { border-left: 3px solid #3b82f6; background: rgba(128,128,128,.06);
           border-radius: 0 10px 10px 0; padding: 14px 16px; margin-bottom: 12px; }
.nv-card.accelerating { border-left-color: #16a34a; }
.nv-card.decelerating { border-left-color: #d97706; }
.nv-card h3 { margin: 0 0 5px; font-size: 17px; }
.nv-card p { margin: 0 0 8px; font-size: 14.5px; }
.nv-chip { font-size: 10.5px; font-weight: 700; letter-spacing: .05em;
           border-radius: 5px; padding: 2px 7px; text-transform: uppercase;
           margin-left: 7px; white-space: nowrap; }
.nv-chip.meta { color: #7c3aed; background: rgba(124,58,237,.12); }
.nv-chip.sector { color: #3b82f6; background: rgba(59,130,246,.12); }
.nv-chip.industry { color: #0891b2; background: rgba(8,145,178,.12); }
.nv-chip.acc { color: #16a34a; background: rgba(22,163,74,.14); }
.nv-chip.dec { color: #d97706; background: rgba(217,119,6,.14); }
.nv-chip.emerging { opacity: .7; background: rgba(128,128,128,.14); }
.nv-gems { font-size: 13.5px; opacity: .9; }
.nv-gems b { font-weight: 700; }
.nv-change { font-size: 12.5px; opacity: .6; }
.nv-idx { font-size: 14px; padding: 2px 0; }
.nv-idx .cnt { opacity: .5; font-size: 12px; }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=900)
def load_data():
    with _engine().connect() as conn:
        nars = conn.execute(text("""
            SELECT id, name, tier, COALESCE(scope,''), parent_id, momentum,
                   COALESCE(thesis, description), falsification
            FROM narratives
            WHERE status IN ('active', 'declining')
              AND COALESCE(scope, '') != 'company'
            ORDER BY id""")).fetchall()
        expo = conn.execute(text("""
            SELECT ne.narrative_id, ne.symbol, ne.exposure,
                   COALESCE(lh.assessed_tier, lh.tier),
                   ROUND(lh.gem_score * 10, 1)
            FROM narrative_exposures ne
            JOIN leaderboard_history lh ON lh.symbol = ne.symbol
                AND lh.date = (SELECT MAX(date) FROM leaderboard_history)
            WHERE COALESCE(lh.assessed_tier, lh.tier) IS NOT NULL
            ORDER BY lh.gem_score DESC""")).fetchall()
        changes = dict(conn.execute(text("""
            SELECT eh.narrative_id, COUNT(*) FROM exposure_history eh
            WHERE eh.judged_at > NOW() - INTERVAL '7 days'
              AND eh.op IN ('add','strengthen','weaken','remove')
            GROUP BY eh.narrative_id""")).fetchall())
    return nars, expo, changes


TIER_W = {"Strong Buy": 3.0, "Buy": 2.0, "Watch": 1.0}
LEVEL = {"macro": ("meta", "META"), "sector": ("sector", "SECTOR")}

nars, expo, changes = load_data()
by_id = {n[0]: n for n in nars}
kids: dict = {}
for n in nars:
    # macros are roots by definition — never render one as a child
    if n[4] in by_id and n[2] != "macro":
        kids.setdefault(n[4], []).append(n[0])

gems_by_n: dict = {}
weight = {}
for nid, sym, ex, tier, score in expo:
    if nid not in by_id:
        continue
    gems_by_n.setdefault(nid, []).append((sym, tier, float(score)))
    weight[nid] = weight.get(nid, 0) + TIER_W.get(tier, 0) * float(ex)


def rollup(nid):
    return weight.get(nid, 0) + sum(rollup(c) for c in kids.get(nid, []))


def salience(nid):
    mom_bonus = 5 if (by_id[nid][5] or "") == "accelerating" else 0
    return weight.get(nid, 0) + 2 * changes.get(nid, 0) + mom_bonus


def _clip(s, limit=380):
    s = s or ""
    if len(s) <= limit:
        return s
    return s[:limit].rsplit(" ", 1)[0] + " …"


def level_chip(n):
    key, label = LEVEL.get(n[2], ("industry", "INDUSTRY"))
    chips = f'<span class="nv-chip {key}">{label}</span>'
    if n[2] in ("emerging", "candidate"):
        chips += f'<span class="nv-chip emerging">{n[2]}</span>'
    mom = (n[5] or "stable")
    if mom == "accelerating":
        chips += '<span class="nv-chip acc">accelerating</span>'
    elif mom == "decelerating":
        chips += '<span class="nv-chip dec">decelerating</span>'
    return chips


st.markdown('<div class="nv-wrap">', unsafe_allow_html=True)
st.markdown(f'<div class="nv-title">🧭 The Narrative Map</div>'
            f'<div class="nv-sub">What the platform believes, what is moving, '
            f'and the full library beneath — company-specific stories live on '
            f'their own page. {datetime.utcnow():%A, %B %d, %Y}</div>',
            unsafe_allow_html=True)

# ── Layer 1: the map ─────────────────────────────────────────────────────────
st.markdown('<div class="nv-h2">The map — the forces we are positioned for</div>',
            unsafe_allow_html=True)
macros = sorted((n for n in nars if n[2] == "macro"),
                key=lambda n: -rollup(n[0]))
blocks = ""
for m in macros:
    w = rollup(m[0])
    grow = max(1, int(w * 2))
    nkids = len(kids.get(m[0], []))
    mom = (m[5] or "stable")
    blocks += (f'<div class="nv-block {esc(mom)}" style="flex-grow:{grow}">'
               f'<h4>{esc(m[1])}</h4>'
               f'<div class="meta">weight {w:.1f} · {nkids} narrative{"s" if nkids != 1 else ""} · {esc(mom)}</div></div>')
st.markdown(f'<div class="nv-map">{blocks}</div>', unsafe_allow_html=True)

# ── Layer 2: what moved ──────────────────────────────────────────────────────
st.markdown('<div class="nv-h2">What matters now — ranked by board weight and '
            'recent change</div>', unsafe_allow_html=True)
ranked = sorted(nars, key=lambda n: -salience(n[0]))[:8]
for n in ranked:
    nid = n[0]
    parent = by_id.get(n[4])
    crumb = f'{esc(parent[1])} → ' if parent else ''
    top = gems_by_n.get(nid, [])[:5]
    gems_html = " · ".join(
        f'<b>{esc(s)}</b> {sc:.1f} {esc(t)}' for s, t, sc in top) or "no board stocks exposed"
    ch = changes.get(nid, 0)
    change_line = (f'{ch} exposure change{"s" if ch != 1 else ""} recorded this week'
                   if ch else "no ledger changes this week")
    mom = (n[5] or "stable")
    st.markdown(
        f'<div class="nv-card {esc(mom)}">'
        f'<h3>{crumb}{esc(n[1])}{level_chip(n)}</h3>'
        f'<p>{esc(_clip(n[6]))}</p>'
        f'<div class="nv-gems">{gems_html}</div>'
        f'<div class="nv-change">{change_line} · board weight {weight.get(nid, 0):.1f}</div>'
        f'</div>', unsafe_allow_html=True)
    if n[7]:
        with st.expander("What would kill this narrative"):
            st.write(n[7])

# ── Layer 3: the library ─────────────────────────────────────────────────────
st.markdown('<div class="nv-h2">The library — every narrative, in its place</div>',
            unsafe_allow_html=True)
for m in macros:
    total = rollup(m[0])
    nk = len(kids.get(m[0], []))
    with st.expander(f"{m[1]}  ·  weight {total:.1f}  ·  "
                     f"{nk} direct {'child' if nk == 1 else 'children'}"):
        def render_line(nid, depth):
            n = by_id[nid]
            pad = "&nbsp;" * (depth * 6)
            cnt = len(gems_by_n.get(nid, []))
            st.markdown(
                f'<div class="nv-idx">{pad}{esc(n[1])}{level_chip(n)} '
                f'<span class="cnt">· {cnt} board stock{"s" if cnt != 1 else ""}'
                f' · weight {weight.get(nid, 0):.1f}</span></div>',
                unsafe_allow_html=True)
            for c in sorted(kids.get(nid, []), key=lambda x: -rollup(x)):
                render_line(c, depth + 1)
        for c in sorted(kids.get(m[0], []), key=lambda x: -rollup(x)):
            render_line(c, 1)
        if not kids.get(m[0]):
            st.caption("no child narratives yet")

st.markdown("</div>", unsafe_allow_html=True)
