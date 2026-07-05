"""
Meta-Narrative Themes — the structural forces we track, and the best-scored
stocks exposed to each one.

Themes are persistent entities evolved weekly from all filings; each shows its
emergence curve (companies discussing it per quarter), momentum with evidence,
and the hidden-gem stocks aligned to it — with their discount to theme peers
(the Dell test).
"""

import sys
import json
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import text

root = Path(__file__).parent.parent
sys.path.insert(0, str(root))
load_dotenv(root / ".env", override=True)

from pipeline.hidden_gem_scorer import get_engine

st.set_page_config(page_title="Meta-Narrative Themes", page_icon="🧭", layout="wide")

st.markdown("""
<style>
.block-container { max-width: 1080px; padding: 3.5rem 2rem 4rem; }
header[data-testid="stHeader"] { display: none; }

.page-title    { font-size: 1.75rem; font-weight: 800; color: #0f172a; }
.page-subtitle { font-size: 0.85rem; color: #64748b; margin-top: 0.2rem; margin-bottom: 1.5rem; }

.theme-card {
    background: #fff; border: 1px solid #e5e7eb; border-radius: 10px;
    padding: 1.1rem 1.3rem; margin-bottom: 1.1rem;
}
.theme-name { font-size: 1.05rem; font-weight: 700; color: #0f172a; }
.theme-desc { font-size: 0.83rem; color: #475569; margin: 0.25rem 0 0.4rem; line-height: 1.45; }
.theme-evidence { font-size: 0.78rem; color: #64748b; font-style: italic; }
.mom-accelerating { background:#dcfce7; color:#166534; }
.mom-stable       { background:#f1f5f9; color:#475569; }
.mom-decelerating, .mom-fading { background:#fee2e2; color:#991b1b; }
.mom-pill { font-size:0.68rem; font-weight:700; padding:2px 8px; border-radius:10px;
            text-transform:uppercase; letter-spacing:0.05em; }
.stock-row { display:flex; justify-content:space-between; align-items:center;
             padding:0.35rem 0; border-top:1px solid #f1f5f9; font-size:0.84rem; }
.stock-sym  { font-weight:700; color:#0f172a; width:60px; }
.stock-tier { font-size:0.72rem; font-weight:600; padding:1px 7px; border-radius:4px; }
.t-sb    { background:#fef2f2; color:#991b1b; }
.t-buy   { background:#f0fdf4; color:#166534; }
.t-watch { background:#fefce8; color:#854d0e; }
.stock-meta { color:#64748b; font-size:0.78rem; }
.disc-good { color:#059669; font-weight:700; }
.disc-bad  { color:#94a3b8; }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def _engine():
    return get_engine()


@st.cache_data(ttl=900)
def load_themes():
    with _engine().connect() as conn:
        themes = conn.execute(text("""
            SELECT id, name, description, momentum, thesis, tier, sector_scope,
                   parent_id, falsification
            FROM narratives
            WHERE status IN ('active', 'declining')
            ORDER BY (tier = 'macro') DESC, (momentum = 'accelerating') DESC, name
        """)).fetchall()

        gems = conn.execute(text("""
            SELECT ne.narrative_id, lh.symbol,
                   COALESCE(lh.assessed_tier, lh.tier) AS tier,
                   lh.gem_score, ne.exposure, ne.evidence,
                   tvg.pe_discount, tvg.stock_pe_fwd, tvg.peer_median_pe
            FROM narrative_exposures ne
            JOIN leaderboard_history lh
                ON lh.symbol = ne.symbol
                AND lh.date = (SELECT MAX(date) FROM leaderboard_history)
                AND lh.tier IS NOT NULL
            LEFT JOIN theme_valuation_gaps tvg
                ON tvg.symbol = ne.symbol AND tvg.meta_theme_id = ne.narrative_id
            ORDER BY ne.narrative_id, lh.gem_score DESC
        """)).fetchall()
    return themes, gems


themes, gems = load_themes()

by_theme_gems: dict = {}
for row in gems:
    by_theme_gems.setdefault(row[0], []).append(row)

st.markdown(f"""
<div class="page-title">🧭 The Meta-Narrative</div>
<div class="page-subtitle">The secular tailwinds we are heading into — macro forces first, then
the sector narratives beneath them, each with the falsification conditions that would kill it and
the best-scored gems genuinely exposed. Exposure is judged from each company's own filings, with
cited evidence. &nbsp;·&nbsp; {datetime.utcnow().strftime('%A, %B %d, %Y')}</div>
""", unsafe_allow_html=True)

tier_cls = {"Strong Buy": "t-sb", "Buy": "t-buy", "Watch": "t-watch"}


def render_narrative(t, indent=False):
    tid, name, desc, momentum, thesis, ntier, scope, parent_id, fals = t
    mom = (momentum or "stable").lower()
    theme_gems = by_theme_gems.get(tid, [])[:5]

    rows_html = ""
    for _, sym, tier, gem_score, exposure, evidence, pe_disc, pe_s, med_pe in theme_gems:
        disc_html = ""
        if pe_disc is not None and float(pe_disc) > 0.10:
            disc_html = (f'<span class="disc-good">{float(pe_disc)*100:.0f}% below narrative peers'
                         f' ({float(pe_s):.1f}x vs {float(med_pe):.1f}x)</span>')
        elif pe_disc is not None:
            disc_html = '<span class="disc-bad">in line with narrative peers</span>'
        ev_short = (evidence or "")[:160]
        rows_html += f"""
<div class="stock-row">
  <span class="stock-sym">{sym}</span>
  <span class="stock-tier {tier_cls.get(tier, 't-watch')}">{tier or '—'}</span>
  <span class="stock-meta" style="flex:1; margin:0 0.8rem;">exposure {float(exposure):.2f} · {ev_short}</span>
  <span>{disc_html}</span>
</div>"""
    if not rows_html:
        rows_html = '<div class="stock-row"><span class="stock-meta">No hidden-gem stocks currently exposed.</span></div>'

    try:
        fals_list = fals if isinstance(fals, list) else (json.loads(fals) if fals else [])
    except Exception:
        fals_list = []
    fals_html = "".join(f'<div class="theme-evidence">✗ {f}</div>' for f in fals_list[:3])

    scope_html = f'<span class="stock-meta">&nbsp;· {scope}</span>' if scope else ""
    margin = "margin-left:1.6rem;" if indent else ""
    st.markdown(f"""
<div class="theme-card" style="{margin}">
  <div style="display:flex; justify-content:space-between; align-items:center;">
    <span class="theme-name">{name}{scope_html}</span>
    <span class="mom-pill mom-{mom}">{momentum or 'stable'}</span>
  </div>
  <div class="theme-desc">{thesis or desc or ''}</div>
  {rows_html}
</div>
""", unsafe_allow_html=True)
    if fals_html:
        with st.expander("What would kill this narrative"):
            st.markdown(fals_html, unsafe_allow_html=True)


macros = [t for t in themes if t[5] == "macro"]
sectors_by_parent: dict = {}
orphans = []
for t in themes:
    if t[5] != "macro":
        if t[7]:
            sectors_by_parent.setdefault(t[7], []).append(t)
        else:
            orphans.append(t)

for m in macros:
    render_narrative(m)
    for s in sectors_by_parent.get(m[0], []):
        render_narrative(s, indent=True)

if orphans:
    st.markdown('<div class="page-subtitle" style="margin-top:1rem;">Sector narratives (unparented)</div>', unsafe_allow_html=True)
    for s in orphans:
        render_narrative(s, indent=True)
