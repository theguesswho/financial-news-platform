import json
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

root = Path(__file__).parent.parent
sys.path.insert(0, str(root))
load_dotenv(root / ".env", override=True)

from db.session import get_session
from db.models import Filing, EodPrice
from sqlalchemy import create_engine, text, desc

# ---------------------------------------------------------------------------
# Page config & CSS
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Financial Intelligence", page_icon="📈", layout="wide")

st.markdown("""
<style>
.block-container { max-width: 1100px; padding: 2rem 2rem 4rem; }

/* Filing cards */
.card {
    background: #f8f9fa;
    border: 1px solid #e0e0e0;
    border-radius: 10px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1.25rem;
}
.card-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 0.5rem;
}
.filing-type { font-size: 0.8rem; font-weight: 600; color: #666; text-transform: uppercase; letter-spacing: 0.05em; }
.filing-date { font-size: 1.05rem; font-weight: 700; color: #1a1a1a; }
.badge {
    font-size: 0.85rem;
    font-weight: 600;
    padding: 0.25rem 0.75rem;
    border-radius: 20px;
    white-space: nowrap;
}
.badge-bull  { background: #d4edda; color: #155724; }
.badge-bear  { background: #f8d7da; color: #721c24; }
.badge-neut  { background: #fff3cd; color: #856404; }
.badge-none  { background: #e2e3e5; color: #383d41; }
.section-label { font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: #888; margin: 0.75rem 0 0.25rem; }
.summary-text { font-size: 0.95rem; line-height: 1.6; color: #2c2c2c; }
.bullet-item { font-size: 0.9rem; color: #3c3c3c; margin: 0.15rem 0; }
.health-box { background: #eef2ff; border-left: 3px solid #4f46e5; padding: 0.5rem 0.75rem; border-radius: 0 6px 6px 0; font-size: 0.9rem; color: #2c2c2c; margin-top: 0.75rem; }
.source-link { font-size: 0.8rem; color: #888; margin-top: 0.75rem; }

/* Hidden Gem score pill */
.gem-score {
    display: inline-block;
    font-size: 1.1rem;
    font-weight: 800;
    padding: 0.2rem 0.7rem;
    border-radius: 12px;
}
.gem-high  { background: #d4edda; color: #155724; }
.gem-mid   { background: #fff3cd; color: #856404; }
.gem-low   { background: #f0f0f0; color: #555; }

/* Tier badges */
.tier-badge {
    display: inline-block;
    font-size: 0.8rem;
    font-weight: 700;
    padding: 0.2rem 0.6rem;
    border-radius: 20px;
    letter-spacing: 0.03em;
    white-space: nowrap;
}
.tier-strong { background: #1a1a2e; color: #ffffff; }
.tier-buy    { background: #0f4c75; color: #ffffff; }
.tier-watch  { background: #e8f4f8; color: #2c5f7a; border: 1px solid #b8dce8; }
</style>
""", unsafe_allow_html=True)


def safe_md(text: str) -> None:
    st.markdown(text.replace("$", r"\$"))


def sentiment_badge(score) -> str:
    if score is None:
        return '<span class="badge badge-none">Unscored</span>'
    if score >= 4:
        return f'<span class="badge badge-bull">🟢 Bullish ({score:+d})</span>'
    if score <= -4:
        return f'<span class="badge badge-bear">🔴 Bearish ({score:+d})</span>'
    return f'<span class="badge badge-neut">🟡 Neutral ({score:+d})</span>'


def gem_badge(score) -> str:
    if score >= 0.65:
        return f'<span class="gem-score gem-high">💎 {score:.3f}</span>'
    if score >= 0.45:
        return f'<span class="gem-score gem-mid">⭐ {score:.3f}</span>'
    return f'<span class="gem-score gem-low">{score:.3f}</span>'


def get_tier(score: float) -> str | None:
    """
    Conviction tier — narrative is a gate, not just a component.
    Scores are lower than the old formula by design: you cannot reach
    Strong Buy without a strong secular tailwind narrative (n > ~0.80).

      Strong Buy  > 0.58  — narrative firing + cheap + quality
      Buy         0.46–0.58 — two legs strong, narrative present
      Watch       0.34–0.46 — interesting but narrative weak or partial
    Below 0.34 = no narrative signal, do not flag.
    """
    if score >= 0.58:
        return "Strong Buy"
    if score >= 0.46:
        return "Buy"
    if score >= 0.34:
        return "Watch"
    return None


def tier_badge(score: float) -> str:
    tier = get_tier(score)
    if tier == "Strong Buy":
        return '<span class="tier-badge tier-strong">🔥 Strong Buy</span>'
    if tier == "Buy":
        return '<span class="tier-badge tier-buy">✅ Buy</span>'
    if tier == "Watch":
        return '<span class="tier-badge tier-watch">👀 Watch</span>'
    return ""


# ---------------------------------------------------------------------------
# DB connections
# ---------------------------------------------------------------------------
@st.cache_resource
def get_db():
    return get_session()


@st.cache_resource
def get_engine_cached():
    from db.session import get_engine as _ge
    return _ge()


session = get_db()

# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 📈 Financial Intelligence")
    st.markdown("---")
    view = st.radio("View", ["💎 Hidden Gems", "🔍 Company Deep Dive"], index=0)
    st.markdown("---")
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()

# ===========================================================================
# VIEW 1: HIDDEN GEMS SCREENER
# ===========================================================================
if view == "💎 Hidden Gems":
    st.markdown("## 💎 Hidden Gem Screener")
    st.caption(
        "Stocks benefiting from accelerating meta-themes, priced as if they aren't. "
        "Score = Narrative × Value × Quality (geometric mean — must score on all three). "
        "PE ceiling 75× applied — stocks priced for perfection are excluded."
    )

    # ── Load scores ──────────────────────────────────────────────────────────
    @st.cache_data(ttl=3600)
    def load_company_names():
        engine = get_engine_cached()
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT DISTINCT ON (symbol) symbol,
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(title, '^[0-9A-Z\\-]+ — ', ''),
                        ' \\([0-9]{4}-[0-9]{2}-[0-9]{2}\\)$', ''
                    ) as company_name
                FROM filings
                WHERE filing_type IN ('10-K','10-Q') AND title LIKE '%—%'
                ORDER BY symbol, filing_date DESC
            """)).fetchall()
        return {r[0]: r[1] for r in rows}

    @st.cache_data(ttl=3600)
    def load_gem_scores():
        from pipeline.hidden_gem_scorer import score_all_stocks
        engine = get_engine_cached()
        return score_all_stocks(engine)

    with st.spinner("Computing hidden gem scores…"):
        gems = load_gem_scores()
        company_names = load_company_names()

    # Pre-compute tiers for all gems
    for g in gems:
        g["tier"] = get_tier(g["hidden_gem_score"])

    strong_buy_n = sum(1 for g in gems if g["tier"] == "Strong Buy")
    buy_n        = sum(1 for g in gems if g["tier"] == "Buy")
    watch_n      = sum(1 for g in gems if g["tier"] == "Watch")

    # ── Sidebar filters ───────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### Filters")
        tier_filter = st.multiselect(
            "Conviction tier",
            options=["Strong Buy", "Buy", "Watch"],
            default=[],
            placeholder="All tiers",
        )
        min_score = st.slider("Min gem score", 0.0, 1.0, 0.50, 0.01)
        top_n = st.slider("Show top N", 10, 100, 30)
        show_themes = st.multiselect(
            "Filter by theme (optional)",
            options=sorted({t["theme"] for g in gems for t in g["top_themes"]}),
        )

    # ── Apply filters ─────────────────────────────────────────────────────────
    filtered = [g for g in gems if g["hidden_gem_score"] >= min_score]
    if tier_filter:
        filtered = [g for g in filtered if g["tier"] in tier_filter]
    if show_themes:
        filtered = [g for g in filtered if any(t["theme"] in show_themes for t in g["top_themes"])]
    filtered = filtered[:top_n]

    st.markdown(
        f"**{len(filtered)} stocks** pass the filter  "
        f"(min score {min_score:.2f}, universe {len(gems)})"
    )

    if not filtered:
        st.warning("No stocks match the current filters.")
        st.stop()

    # ── Summary metrics ───────────────────────────────────────────────────────
    scores = [g["hidden_gem_score"] for g in filtered]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Top score", f"{scores[0]:.3f}")
    c2.metric("Avg score", f"{sum(scores)/len(scores):.3f}")
    c3.metric("🔥 Strong Buy", strong_buy_n)
    c4.metric("✅ Buy", buy_n)
    c5.metric("👀 Watch", watch_n)

    st.markdown("---")

    # ── Table view ────────────────────────────────────────────────────────────
    rows = []
    for i, g in enumerate(filtered, 1):
        top_theme = g["top_themes"][0]["theme"] if g["top_themes"] else "—"
        rows.append({
            "Rank":      i,
            "Tier":      g["tier"] or "—",
            "Symbol":    g["symbol"],
            "Company":   company_names.get(g["symbol"], ""),
            "Gem Score": round(g["hidden_gem_score"], 3),
            "Narrative": round(g["narrative_score"], 3),
            "Value":     round(g["value_score"], 3),
            "Quality":   round(g["quality_score"], 3),
            "Fwd PE":    round(g["pe_forward"], 1) if g.get("pe_forward") else None,
            "PEG":       round(g["peg_ratio"], 2)  if g.get("peg_ratio")  else None,
            "Rev Gr %":  round((g["revenue_growth"]  or 0) * 100, 1),
            "Earn Gr %": round((g["earnings_growth"] or 0) * 100, 1),
            "ROIC %":    round((g["roic"]            or 0) * 100, 1),
            "Top Theme": top_theme[:50],
        })

    df = pd.DataFrame(rows)

    TIER_ORDER = {"Strong Buy": 0, "Buy": 1, "Watch": 2, "—": 3}

    def style_row(row):
        tier = row.get("Tier", "—")
        if tier == "Strong Buy":
            return ["background-color: #1a1a2e; color: #ffffff; font-weight: bold"] * len(row)
        if tier == "Buy":
            return ["background-color: #dbe9f7; color: #0f3357"] * len(row)
        if tier == "Watch":
            return ["background-color: #f0f7fb; color: #2c5f7a"] * len(row)
        return [""] * len(row)

    def highlight_score(val):
        if isinstance(val, float):
            if val >= 0.58:
                return "font-weight: bold"
            if val >= 0.46:
                return "font-weight: 600"
        return ""

    styled = (
        df.style
        .apply(style_row, axis=1)
        .map(highlight_score, subset=["Gem Score"])
        .format({"Gem Score": "{:.3f}", "Narrative": "{:.3f}", "Value": "{:.3f}",
                 "Quality": "{:.3f}", "Rev Gr %": "{:+.1f}%", "Earn Gr %": "{:+.1f}%",
                 "ROIC %": "{:.1f}%"}, na_rep="—")
        .set_properties(**{"text-align": "center"}, subset=["Rank", "Tier", "Gem Score",
                                                             "Narrative", "Value", "Quality",
                                                             "Fwd PE", "PEG", "Rev Gr %",
                                                             "Earn Gr %", "ROIC %"])
        .set_properties(**{"text-align": "left"}, subset=["Company", "Top Theme"])
    )
    st.dataframe(styled, use_container_width=True, height=min(50 + 35 * len(df), 900))

    # ── Detail panel for selected stock ───────────────────────────────────────
    st.markdown("---")
    st.markdown("### Stock Detail")

    sym_select = st.selectbox(
        "Select a stock for detail",
        options=[g["symbol"] for g in filtered],
        index=0,
    )

    gem = next(g for g in filtered if g["symbol"] == sym_select)
    rank = next(i for i, g in enumerate(filtered, 1) if g["symbol"] == sym_select)

    tb = tier_badge(gem["hidden_gem_score"])
    if tb:
        st.markdown(tb, unsafe_allow_html=True)
        st.markdown("")  # spacing

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Gem Score", f"{gem['hidden_gem_score']:.3f}", f"Rank #{rank}")
    c2.metric("Narrative", f"{gem['narrative_score']:.3f}")
    c3.metric("Value", f"{gem['value_score']:.3f}")
    c4.metric("Quality", f"{gem['quality_score']:.3f}")
    c5.metric("Fwd PE", f"{gem['pe_forward']:.1f}×" if gem.get('pe_forward') else "N/A")
    c6.metric("ROIC", f"{(gem['roic'] or 0)*100:.1f}%")

    c1b, c2b, c3b = st.columns(3)
    c1b.metric("Revenue Growth", f"{(gem['revenue_growth'] or 0)*100:+.1f}%")
    c2b.metric("Earnings Growth", f"{(gem['earnings_growth'] or 0)*100:+.1f}%")
    c3b.metric("FCF Growth", f"{(gem['fcf_growth'] or 0)*100:+.1f}%")

    if gem["top_themes"]:
        st.markdown("**Accelerating meta-themes this stock is aligned to:**")
        for t in gem["top_themes"]:
            st.markdown(f"- **{t['theme']}** — alignment score {t['score']:.3f}")

    # Mini price chart
    prices = session.query(EodPrice).filter(EodPrice.symbol == sym_select).order_by(EodPrice.date).limit(252).all()
    if prices:
        pdf = pd.DataFrame({"Price ($)": [float(p.close) for p in prices]}, index=[p.date for p in prices])
        st.line_chart(pdf, height=200)

    # Meta-theme cross-sector coverage
    st.markdown("---")
    st.markdown("### 🌐 All Accelerating Meta-Themes")
    st.caption("Themes appearing across multiple sectors signal structural macro shifts, not just sector stories.")

    @st.cache_data(ttl=3600)
    def load_meta_themes():
        engine = get_engine_cached()
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT name, description, momentum, company_count,
                       constituent_themes
                FROM meta_themes
                ORDER BY CASE momentum WHEN 'accelerating' THEN 0 WHEN 'stable' THEN 1 ELSE 2 END,
                         company_count DESC
            """)).fetchall()
        return rows

    themes_data = load_meta_themes()

    accel = [(r[0], r[1], r[2], r[3]) for r in themes_data if r[2] == "accelerating"]
    stable = [(r[0], r[1], r[2], r[3]) for r in themes_data if r[2] == "stable"]
    decel  = [(r[0], r[1], r[2], r[3]) for r in themes_data if r[2] == "decelerating"]

    for label, group, icon in [
        ("Accelerating", accel, "🚀"),
        ("Stable", stable, "➡️"),
        ("Decelerating", decel, "📉"),
    ]:
        if group:
            with st.expander(f"{icon} {label} themes ({len(group)})", expanded=(label == "Accelerating")):
                tdf = pd.DataFrame(group, columns=["Theme", "Description", "Momentum", "Companies"])
                st.dataframe(tdf[["Theme", "Companies", "Description"]], use_container_width=True, hide_index=True)


# ===========================================================================
# VIEW 2: COMPANY DEEP DIVE
# ===========================================================================
else:
    with st.sidebar:
        all_symbols = [
            row[0]
            for row in session.query(Filing.symbol).distinct().order_by(Filing.symbol).all()
        ]
        if not all_symbols:
            st.warning("No filings yet.")
            st.stop()

        selected = st.selectbox("Company", all_symbols)
        filing_types = st.multiselect("Filing types", ["10-K", "10-Q", "8-K"], default=["10-K", "10-Q"])
        n = st.slider("Show last N filings", 1, 20, 5)

    # Load data
    q = session.query(Filing).filter(Filing.symbol == selected).order_by(desc(Filing.filing_date))
    if filing_types:
        q = q.filter(Filing.filing_type.in_(filing_types))
    filings = q.limit(n).all()

    prices = (
        session.query(EodPrice)
        .filter(EodPrice.symbol == selected)
        .order_by(EodPrice.date)
        .limit(90)
        .all()
    )

    st.markdown(f"## {selected}")

    if prices:
        latest, prev = prices[-1], prices[-2] if len(prices) > 1 else prices[-1]
        pct = (float(latest.close) - float(prev.close)) / float(prev.close) * 100 if prev.close else 0
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Price", f"${float(latest.close):.2f}", f"{pct:+.2f}%")
        c2.metric("As of", str(latest.date))
        c3.metric("Filings shown", len(filings))
        c4.metric("Analyzed", sum(1 for f in filings if f.master_analysis))

    # Hidden gem score for this company
    @st.cache_data(ttl=3600)
    def get_gem_for(symbol):
        from pipeline.hidden_gem_scorer import score_all_stocks
        engine = get_engine_cached()
        results = score_all_stocks(engine)
        stock = next((s for s in results if s["symbol"] == symbol), None)
        rank = next((i for i, s in enumerate(results, 1) if s["symbol"] == symbol), None)
        return stock, rank, len(results)

    gem, gem_rank, total = get_gem_for(selected)
    if gem:
        st.markdown("#### Hidden Gem Signal")
        tb = tier_badge(gem["hidden_gem_score"])
        if tb:
            st.markdown(tb, unsafe_allow_html=True)
            st.markdown("")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Gem Score", f"{gem['hidden_gem_score']:.3f}", f"Rank #{gem_rank} / {total}")
        c2.metric("Narrative", f"{gem['narrative_score']:.3f}")
        c3.metric("Value", f"{gem['value_score']:.3f}")
        c4.metric("Quality", f"{gem['quality_score']:.3f}")
        c5.metric("Fwd PE", f"{gem['pe_forward']:.1f}×" if gem.get('pe_forward') else "N/A")

        if gem["top_themes"]:
            theme_str = " · ".join(t["theme"] for t in gem["top_themes"])
            st.caption(f"🏷️ Aligned themes: {theme_str}")

    if prices:
        df = pd.DataFrame(
            {"Close ($)": [float(p.close) for p in prices]},
            index=[p.date for p in prices],
        )
        with st.expander("Price chart (last 90 days)", expanded=True):
            st.line_chart(df, height=220)

    st.markdown("---")

    if not filings:
        st.info(f"No {' / '.join(filing_types)} filings found for {selected}.")
        st.stop()

    for filing in filings:
        date_str = filing.filing_date.strftime("%Y-%m-%d") if filing.filing_date else "—"
        badge = sentiment_badge(filing.sentiment_score)

        analysis = {}
        if filing.llm_analysis:
            try:
                analysis = json.loads(filing.llm_analysis)
            except (json.JSONDecodeError, TypeError):
                pass

        st.markdown(f"""
<div class="card">
  <div class="card-header">
    <div>
      <div class="filing-type">{filing.filing_type}</div>
      <div class="filing-date">{date_str}</div>
    </div>
    {badge}
  </div>
</div>
""", unsafe_allow_html=True)

        if analysis.get("summary"):
            st.markdown('<div class="section-label">Summary</div>', unsafe_allow_html=True)
            safe_md(analysis["summary"])

        risks = analysis.get("key_risks", [])
        opps = analysis.get("key_opportunities", [])
        if risks or opps:
            col_r, col_o = st.columns(2)
            with col_r:
                if risks:
                    st.markdown('<div class="section-label">Key Risks</div>', unsafe_allow_html=True)
                    for r in risks:
                        safe_md(f"• {r}")
            with col_o:
                if opps:
                    st.markdown('<div class="section-label">Key Opportunities</div>', unsafe_allow_html=True)
                    for o in opps:
                        safe_md(f"• {o}")

        if analysis.get("financial_health"):
            st.markdown(
                f'<div class="health-box">💼 {analysis["financial_health"]}</div>',
                unsafe_allow_html=True,
            )

        if filing.master_analysis:
            with st.expander("Full investment brief"):
                lines = [
                    l for l in filing.master_analysis.splitlines()
                    if "sentiment score:" not in l.lower()
                ]
                safe_md("\n".join(lines).strip())

        st.markdown(
            f'<div class="source-link"><a href="{filing.url}" target="_blank">View original filing ↗</a></div>',
            unsafe_allow_html=True,
        )
        st.markdown("---")
