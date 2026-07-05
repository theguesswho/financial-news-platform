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
            SELECT id, name, description, momentum,
                   constituent_themes->>'momentum_evidence' AS evidence,
                   company_count
            FROM meta_themes
            WHERE COALESCE(status,'active') = 'active'
              AND name NOT ILIKE '%idiosyncratic%'
            ORDER BY (momentum = 'accelerating') DESC, company_count DESC NULLS LAST
            LIMIT 12
        """)).fetchall()

        gems = conn.execute(text("""
            SELECT sta.meta_theme_id, lh.symbol,
                   COALESCE(lh.assessed_tier, lh.tier) AS tier,
                   lh.gem_score, sta.alignment_score,
                   tvg.pe_discount, tvg.stock_pe_fwd, tvg.peer_median_pe
            FROM stock_theme_alignment sta
            JOIN leaderboard_history lh
                ON lh.symbol = sta.symbol
                AND lh.date = (SELECT MAX(date) FROM leaderboard_history)
                AND lh.tier IS NOT NULL
            LEFT JOIN theme_valuation_gaps tvg
                ON tvg.symbol = sta.symbol AND tvg.meta_theme_id = sta.meta_theme_id
            ORDER BY sta.meta_theme_id, lh.gem_score DESC
        """)).fetchall()

        history = conn.execute(text("""
            SELECT meta_theme_id, snapshot_date, company_count
            FROM theme_history
            WHERE snapshot_date >= '2024-10-01'
            ORDER BY meta_theme_id, snapshot_date
        """)).fetchall()
    return themes, gems, history


themes, gems, history = load_themes()

by_theme_gems: dict = {}
for row in gems:
    by_theme_gems.setdefault(row[0], []).append(row)

by_theme_hist: dict = {}
for tid, d, n in history:
    by_theme_hist.setdefault(tid, []).append((d, n))

st.markdown(f"""
<div class="page-title">🧭 Meta-Narrative Themes</div>
<div class="page-subtitle">The structural forces extracted from every filing we track — and the
best-scored stocks exposed to each. Updated weekly; emergence curves since Q4 2024.
&nbsp;·&nbsp; {datetime.utcnow().strftime('%A, %B %d, %Y')}</div>
""", unsafe_allow_html=True)

tier_cls = {"Strong Buy": "t-sb", "Buy": "t-buy", "Watch": "t-watch"}

for t in themes:
    tid, name, desc, momentum, evidence, n_comp = t
    mom = (momentum or "stable").lower()
    theme_gems = by_theme_gems.get(tid, [])[:5]

    rows_html = ""
    for _, sym, tier, gem_score, align, pe_disc, pe_s, med_pe in theme_gems:
        disc_html = ""
        if pe_disc is not None and float(pe_disc) > 0.10:
            disc_html = (f'<span class="disc-good">{float(pe_disc)*100:.0f}% below theme peers'
                         f' ({float(pe_s):.1f}x vs {float(med_pe):.1f}x)</span>')
        elif pe_disc is not None:
            disc_html = f'<span class="disc-bad">in line with theme peers</span>'
        rows_html += f"""
<div class="stock-row">
  <span class="stock-sym">{sym}</span>
  <span class="stock-tier {tier_cls.get(tier, 't-watch')}">{tier or '—'}</span>
  <span class="stock-meta">gem {float(gem_score):.3f} · alignment {float(align):.2f}</span>
  <span>{disc_html}</span>
</div>"""

    if not rows_html:
        rows_html = '<div class="stock-row"><span class="stock-meta">No hidden-gem stocks currently aligned.</span></div>'

    st.markdown(f"""
<div class="theme-card">
  <div style="display:flex; justify-content:space-between; align-items:center;">
    <span class="theme-name">{name}</span>
    <span class="mom-pill mom-{mom}">{momentum or 'stable'}</span>
  </div>
  <div class="theme-desc">{desc or ''}</div>
  {'<div class="theme-evidence">Evidence: ' + evidence + '</div>' if evidence else ''}
  {rows_html}
</div>
""", unsafe_allow_html=True)

    hist = by_theme_hist.get(tid, [])
    if len(hist) >= 3:
        hdf = pd.DataFrame(hist, columns=["quarter", "companies"])
        hdf["quarter"] = pd.to_datetime(hdf["quarter"])
        with st.expander(f"Emergence curve — companies discussing this per quarter"):
            st.line_chart(hdf.set_index("quarter")["companies"], height=140)
