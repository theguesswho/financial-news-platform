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
.mr-day { display: grid; grid-template-columns: 84px 1fr; gap: 14px;
          padding: 9px 0; border-bottom: 1px dashed rgba(128,128,128,.25); }
.mr-day:last-child { border-bottom: none; }
.mr-date { text-align: right; }
.mr-dow { font-weight: 700; font-size: 15px; }
.mr-dow.today { color: #3b82f6; }
.mr-dom { opacity: .55; font-size: 12.5px; }
.mr-ev { display: flex; flex-wrap: wrap; align-items: baseline; gap: 7px; margin-bottom: 6px; }
.mr-sym { font-weight: 700; }
.mr-why { opacity: .65; }
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


def _week_html(week_rows) -> str:
    by_day = {}
    for kind, sym, p in week_rows:
        slot = by_day.setdefault(p.get("date") or "", {"watch": [], "other": []})
        if kind == "other":
            slot["other"] = p.get("symbols") or []
        else:
            slot["watch"].append((sym, p))
    out = ['<div class="mr-h2">Earnings ahead</div>',
           '<div class="mr-sub">Who in our universe reports this week — '
           'and what we\'re looking for.</div>']
    for d in sorted(by_day):
        try:
            dd = date.fromisoformat(d)
            is_today = dd == date.today()
            dow = "Today" if is_today else f"{dd:%a}"
            dom = f"{dd:%b %-d}"
        except Exception:
            dow, dom, is_today = d, "", False
        items = []
        watch = by_day[d]["watch"]
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
                              f'{"s" if n > 1 else ""} on the line</span>')
            if p.get("review"):
                badges.append('<span class="mr-b rev">story under review</span>')
            why = _esc(p.get("watch"))
            items.append(f'<div class="mr-ev"><span class="mr-sym">{_esc(sym)}</span>'
                         + "".join(badges)
                         + (f'<span class="mr-why">{why}</span>' if why else "")
                         + "</div>")
        other = by_day[d]["other"]
        if other:
            shown = ", ".join(other[:14]) + (f" +{len(other)-14} more" if len(other) > 14 else "")
            items.append(f'<div class="mr-also">Also reporting: {_esc(shown)}</div>')
        out.append(f'<div class="mr-day"><div class="mr-date">'
                   f'<div class="mr-dow{" today" if is_today else ""}">{dow}</div>'
                   f'<div class="mr-dom">{dom}</div></div>'
                   f'<div>{"".join(items)}</div></div>')
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

    with st.sidebar:
        pick = st.selectbox("Report date", dates, index=dates.index(d),
                            format_func=lambda x: f"{x:%a %b %-d, %Y}")
    if pick != d:
        d, rows, dates = _load(engine, pick)

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
            parts.append('<div class="mr-kicker">Hidden Gems · Morning Report</div>')
            parts.append(f'<div class="mr-h1">{d:%A, %B %-d, %Y}</div>')
            chips = [f"<span class='mr-chip'><b>{p.get('board')}</b> stocks rated Buy or better</span>",
                     f"<span class='mr-chip'><b>{p.get('changes')}</b> changes overnight</span>"]
            us, spy = p.get("us_pct"), p.get("spy_pct")
            if us is not None and spy is not None:
                chips.append(f"<span class='mr-chip'>Our picks <b class='mr-up'>{us:+.1f}%</b>"
                             f" vs S&amp;P 500 <b>{spy:+.1f}%</b></span>")
            parts.append('<div class="mr-chips">' + "".join(chips) + "</div>")
            if week_rows:
                parts.append(_week_html(week_rows))
        elif section == "top_story":
            parts.append('<div class="mr-h2">Top story</div>')
            badge = BADGE_LABEL.get(kind or "", "")
            parts.append(
                f'<div class="mr-card {kind or "info"}">'
                + (f'<div class="mr-lead">{badge}</div>' if badge else "")
                + f'<h3>{_esc(headline)}</h3><p>{_esc(body)}</p></div>')
        elif section in SECTION_HEAD:
            title, sub = SECTION_HEAD[section]
            hdr = f'<div class="mr-h2">{title}</div>'
            if hdr not in parts:
                parts.append(hdr)
                if sub:
                    parts.append(f'<div class="mr-sub">{sub}</div>')
            badge = BADGE_LABEL.get(kind or "")
            b_html = f'<span class="mr-badge {kind}">{badge}</span>' if badge else ""
            parts.append(f'<div class="mr-card {kind or "info"}">'
                         f'<h3>{_esc(headline)}{b_html}</h3>'
                         f'<p>{_esc(body)}</p></div>')
        elif section == "scoreboard":
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
