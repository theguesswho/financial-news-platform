"""
Morning Report renderer (Home revamp Phase 2). Renders the stored
daily_report rows — one SELECT, no computation at page load. Visual spec:
scratch mockup v2 approved 2026-08-06 (day-rail earnings, stake badges,
cause-bearing story cards, meaning-line under every section header).
Cutover: set HOME_MODE=report on the web service; rollback: unset it
(the old feed also lives on the News Wire page permanently).
"""
import html
import json
from datetime import date

import streamlit as st
from sqlalchemy import text

CSS = """
<style>
.mr-wrap { max-width: 860px; }
.mr-kicker { font-size: 12.5px; letter-spacing: .14em; text-transform: uppercase;
             opacity: .6; margin-bottom: 2px; }
.mr-h1 { font-size: 30px; font-weight: 700; letter-spacing: -0.5px; margin: 0 0 10px; }
.mr-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.mr-chip { background: rgba(128,128,128,.12); border-radius: 999px;
           padding: 4px 12px; font-size: 13.5px; }
.mr-h2 { font-size: 13px; letter-spacing: .12em; text-transform: uppercase;
         opacity: .65; border-top: 1px solid rgba(128,128,128,.25);
         padding-top: 20px; margin: 26px 0 2px; font-weight: 600; }
.mr-sub { opacity: .55; font-size: 13.5px; font-style: italic; margin: 0 0 12px; }
.mr-week { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; }
@media (max-width: 900px) { .mr-week { grid-template-columns: repeat(2, 1fr); } }
.mr-col { border: 1px solid rgba(128,128,128,.22); border-radius: 10px;
          padding: 10px 11px; min-height: 70px; }
.mr-col.past .mr-colhead { opacity: .55; }
.mr-col.today { background: rgba(59,130,246,.07); border-color: rgba(59,130,246,.45); }
.mr-colhead { display: flex; justify-content: space-between; align-items: baseline;
              margin-bottom: 8px; border-bottom: 1px solid rgba(128,128,128,.18);
              padding-bottom: 5px; }
.mr-dow { font-weight: 700; font-size: 14px; }
.mr-dow.today { color: #3b82f6; }
.mr-dom { opacity: .55; font-size: 11.5px; }
.mr-ev { margin-bottom: 9px; }
.mr-evhead { display: flex; flex-wrap: wrap; align-items: baseline; gap: 5px; }
.mr-sym { font-weight: 700; font-size: 14.5px; }
.mr-why { opacity: .65; font-size: 12.8px; line-height: 1.4; margin-top: 1px; }
.mr-none { opacity: .4; font-size: 12.5px; font-style: italic; }
.mr-schip { font-size: 12.5px; font-weight: 600; opacity: .6;
            margin-left: 8px; white-space: nowrap; }
.mr-mini { font-size: 11.5px; font-weight: 600; opacity: .55; white-space: nowrap; }
.mr-b { font-size: 10.5px; font-weight: 700; letter-spacing: .05em; border-radius: 5px;
        padding: 2px 7px; text-transform: uppercase; white-space: nowrap; }
.mr-b.held { color: #b8860b; background: rgba(184,134,11,.14); }
.mr-b.sb   { color: #16a34a; background: rgba(22,163,74,.14); }
.mr-b.buy  { color: #3b82f6; background: rgba(59,130,246,.14); }
.mr-b.watch{ opacity: .75; background: rgba(128,128,128,.14); }
.mr-b.pred { color: #dc2626; background: rgba(220,38,38,.12); }
.mr-b.rev  { color: #d97706; background: rgba(217,119,6,.14); }
.mr-also { opacity: .5; font-size: 13px; }
.mr-card { border-left: 3px solid rgba(128,128,128,.35); background: rgba(128,128,128,.06);
           border-radius: 0 10px 10px 0; padding: 13px 16px; margin-bottom: 11px; }
.mr-card.exit { border-left-color: #dc2626; }
.mr-card.entry, .mr-card.upgrade, .mr-card.verdict-ok { border-left-color: #16a34a; }
.mr-card.downgrade { border-left-color: #d97706; }
.mr-card.info, .mr-card.birth { border-left-color: #3b82f6; }
.mr-card h3 { margin: 0 0 6px; font-size: 16.5px; font-weight: 700; }
.mr-card p { margin: 0; font-size: 15px; }
.mr-badge { font-size: 11.5px; font-weight: 700; border-radius: 6px; padding: 2px 8px;
            margin-left: 8px; white-space: nowrap; }
.mr-badge.exit { color: #dc2626; background: rgba(220,38,38,.12); }
.mr-badge.entry, .mr-badge.upgrade { color: #16a34a; background: rgba(22,163,74,.14); }
.mr-badge.downgrade { color: #d97706; background: rgba(217,119,6,.14); }
.mr-badge.birth, .mr-badge.info { color: #3b82f6; background: rgba(59,130,246,.14); }
.mr-lead { font-size: 11.5px; letter-spacing: .1em; text-transform: uppercase;
           color: #dc2626; font-weight: 700; margin-bottom: 4px; }
.mr-score { display: flex; gap: 12px; flex-wrap: wrap; align-items: center;
            background: rgba(128,128,128,.06); border: 1px solid rgba(128,128,128,.25);
            border-radius: 10px; padding: 12px 16px; font-size: 15px; }
.mr-big { font-size: 20px; font-weight: 700; }
.mr-up { color: #16a34a; }
.mr-foot { opacity: .55; font-size: 13px; margin-top: 6px; }
</style>
"""

BADGE_LABEL = {"exit": "▼ EXIT", "entry": "▲ NEW", "upgrade": "▲ UPGRADE",
               "downgrade": "▼ DOWNGRADE", "birth": "NEW STORY"}
SECTION_HEAD = {
    "moves": ("What changed on the board", "Every move with its cause."),
    "coverage": ("News on our picks",
                 "Filings from Strong Buys, Buys, and held positions — and what each did to its score."),
    "stories": ("The stories we're tracking",
                "Company stories live only as their predictions come true."),
    "radar": ("Approaching the board", ""),
}


def _esc(s):
    return html.escape(str(s)) if s else ""


def _live_race(engine) -> dict | None:
    """Live scorecard for the race chips — the stored masthead value is the
    6am snapshot and drifts stale during the day (user 2026-08-08). Only
    used for the LATEST report; archived dates keep their morning numbers."""
    try:
        from pipeline.track_record import get_scorecard
        sc = get_scorecard(engine) or {}
        return {"us_pct": sc.get("portfolio_return_pct"),
                "spy_pct": sc.get("spy_return_pct"),
                "positions": sc.get("open_lots", sc.get("n_lots"))}
    except Exception:
        return None


def _load_standings(engine) -> dict:
    """symbol -> 'Buy · 3.5 · #15' from the latest board snapshot; stocks
    off the board show score only."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT symbol, COALESCE(assessed_tier, tier),
                   ROUND(gem_score * 10, 1), COALESCE(final_rank, rank)
            FROM leaderboard_history
            WHERE date = (SELECT MAX(date) FROM leaderboard_history)
        """)).fetchall()
    out = {}
    for sym, tier, score, rank in rows:
        sr = " · ".join(([f"{float(score):.1f}"] if score is not None else [])
                        + ([f"#{rank}"] if tier and rank else []))
        out[sym] = {"full": " · ".join(([tier] if tier else []) + ([sr] if sr else [])),
                    "sr": sr}
    return out


def _load(engine, for_date):
    with engine.connect() as conn:
        dates = [r[0] for r in conn.execute(text(
            "SELECT DISTINCT date FROM daily_report ORDER BY date DESC LIMIT 30")).fetchall()]
        if not dates:
            return None, []
        d = for_date if for_date in dates else dates[0]
        rows = conn.execute(text("""
            SELECT section, kind, symbol, headline, body, payload
            FROM daily_report WHERE date = :d ORDER BY position"""),
            {"d": d}).fetchall()
    return d, rows, dates


def _week_html(week_rows, week_dates=None, standings=None) -> str:
    standings = standings or {}
    by_day = {}
    for kind, sym, p in week_rows:
        slot = by_day.setdefault(p.get("date") or "", {"watch": [], "other": []})
        if kind == "other":
            slot["other"] = p.get("symbols") or []
        else:
            slot["watch"].append((sym, p))
    days = week_dates or sorted(by_day)
    out = ['<div class="mr-h2">This week</div>',
           '<div class="mr-sub">Who in our universe reports Monday to Friday — '
           'and what we\'re looking for.</div>', '<div class="mr-week">']
    for d in days:
        try:
            dd = date.fromisoformat(d)
            is_today = dd == date.today()
            is_past = dd < date.today()
            dow = "Today" if is_today else f"{dd:%A}"
            dom = f"{dd:%b %-d}" + (" · reported" if is_past else "")
        except Exception:
            dow, dom, is_today, is_past = d, "", False, False
        slot = by_day.get(d, {"watch": [], "other": []})
        items = []
        watch = slot["watch"]
        watch.sort(key=lambda x: (not x[1].get("held"),
                                  not x[1].get("predictions"), x[0] or ""))
        for sym, p in watch:
            badges = []
            if p.get("held"):
                badges.append('<span class="mr-b held">Held</span>')
            t = p.get("tier")
            if t:
                cls = {"Strong Buy": "sb", "Buy": "buy"}.get(t, "watch")
                badges.append(f'<span class="mr-b {cls}">{_esc(t)}</span>')
            n = p.get("predictions") or 0
            if n:
                badges.append(f'<span class="mr-b pred">{n} prediction'
                              f'{"s" if n > 1 else ""}</span>')
            if p.get("review"):
                badges.append('<span class="mr-b rev">under review</span>')
            why = _esc(p.get("watch"))
            sr = (standings.get(sym) or {}).get("sr")
            sr_html = f'<span class="mr-mini">{_esc(sr)}</span>' if sr else ""
            items.append('<div class="mr-ev"><div class="mr-evhead">'
                         f'<span class="mr-sym">{_esc(sym)}</span>{sr_html}{"".join(badges)}</div>'
                         + (f'<div class="mr-why">{why}</div>' if why else "")
                         + "</div>")
        other = slot["other"]
        if other:
            shown = ", ".join(other[:8]) + (f" +{len(other)-8} more" if len(other) > 8 else "")
            items.append(f'<div class="mr-also">Also: {_esc(shown)}</div>')
        if not items:
            items.append('<div class="mr-none">nothing scheduled</div>')
        cls = "mr-col" + (" today" if is_today else "") + (" past" if is_past else "")
        out.append(f'<div class="{cls}"><div class="mr-colhead">'
                   f'<span class="mr-dow{" today" if is_today else ""}">{dow}</span>'
                   f'<span class="mr-dom">{dom}</span></div>{"".join(items)}</div>')
    out.append("</div>")
    return "".join(out)


def render_report(engine):
    st.markdown(CSS, unsafe_allow_html=True)
    loaded = _load(engine, None)
    if loaded[0] is None:
        st.info("No Morning Report stored yet — the first one arrives with "
                "tomorrow's 6:00 UTC run. Meanwhile, the News Wire page has "
                "the live feed.")
        return
    d, rows, dates = loaded
    standings = _load_standings(engine)

    with st.sidebar:
        pick = st.selectbox("Report date", dates, index=dates.index(d),
                            format_func=lambda x: f"{x:%a %b %-d, %Y}")
    if pick != d:
        d, rows, dates = _load(engine, pick)
    live = _live_race(engine) if d == dates[0] else None

    parts = ['<div class="mr-wrap">']
    week_rows, deferred = [], []
    for section, kind, symbol, headline, body, payload in rows:
        p = json.loads(payload) if payload else {}
        if section == "week_ahead":
            week_rows.append((kind, symbol, p))
        else:
            deferred.append((section, kind, symbol, headline, body, p))

    for section, kind, symbol, headline, body, p in deferred:
        if section == "masthead":
            if live:
                p = {**p, **{k: v for k, v in live.items() if v is not None}}
            parts.append('<div class="mr-kicker">Hidden Gems · Morning Report</div>')
            parts.append(f'<div class="mr-h1">{d:%A, %B %-d, %Y}</div>')
            ch = p.get("changes_breakdown")
            chips = [f"<span class='mr-chip'><b>{p.get('board')}</b> stocks rated Buy or better</span>",
                     f"<span class='mr-chip'><b>{p.get('changes')}</b> changes overnight"
                     + (f" <span style='opacity:.6'>({_esc(ch)})</span>" if ch else "")
                     + "</span>"]
            us, spy = p.get("us_pct"), p.get("spy_pct")
            if us is not None and spy is not None:
                chips.append(f"<span class='mr-chip'>Our picks <b class='mr-up'>{us:+.1f}%</b>"
                             f" vs S&amp;P 500 <b>{spy:+.1f}%</b></span>")
            parts.append('<div class="mr-chips">' + "".join(chips) + "</div>")
            if week_rows:
                parts.append(_week_html(week_rows, p.get("week_dates"), standings))
        elif section == "top_story":
            parts.append('<div class="mr-h2">Top story</div>')
            badge = BADGE_LABEL.get(kind or "", "")
            st_full = (standings.get(symbol) or {}).get("full") if symbol else None
            chip = f'<span class="mr-schip">{_esc(st_full)}</span>' if st_full else ""
            parts.append(
                f'<div class="mr-card {kind or "info"}">'
                + (f'<div class="mr-lead">{badge}</div>' if badge else "")
                + f'<h3>{_esc(headline)}{chip}</h3><p>{_esc(body)}</p></div>')
        elif section in SECTION_HEAD:
            title, sub = SECTION_HEAD[section]
            hdr = f'<div class="mr-h2">{title}</div>'
            if hdr not in parts:
                parts.append(hdr)
                if sub:
                    parts.append(f'<div class="mr-sub">{sub}</div>')
            if kind == "ledger":
                parts.append(f'<div class="mr-also" style="padding:2px 4px 10px">'
                             f'<b>{_esc(headline)}:</b> {_esc(body)}</div>')
                continue
            badge = BADGE_LABEL.get(kind or "")
            b_html = f'<span class="mr-badge {kind}">{badge}</span>' if badge else ""
            st_full = (standings.get(symbol) or {}).get("full") if symbol else None
            chip = f'<span class="mr-schip">{_esc(st_full)}</span>' if st_full else ""
            parts.append(f'<div class="mr-card {kind or "info"}">'
                         f'<h3>{_esc(headline)}{b_html}{chip}</h3>'
                         f'<p>{_esc(body)}</p></div>')
        elif section == "scoreboard":
            if live:
                p = {**p, **{k: v for k, v in live.items() if v is not None}}
            parts.append('<div class="mr-h2">How we\'re doing vs the market</div>')
            us, spy = p.get("us_pct"), p.get("spy_pct")
            if us is not None and spy is not None:
                parts.append(
                    f'<div class="mr-score"><span>Our picks '
                    f'<span class="mr-big mr-up">{us:+.1f}%</span></span><span>vs</span>'
                    f'<span>S&amp;P 500 <span class="mr-big">{spy:+.1f}%</span></span>'
                    f'<span class="mr-foot">· {p.get("positions")} positions · '
                    f'since {_esc(p.get("since"))}</span></div>')
            parts.append('<div class="mr-foot">Every pick is tracked against a '
                         'same-day S&amp;P 500 purchase. Exits stay on the record.</div>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)
