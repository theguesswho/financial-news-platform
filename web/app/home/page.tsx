// The product home (Board as landing). One-line masthead with the tier
// counts and the Book-vs-SPY proof (linked to Track record), TODAY
// headlines linking into the full edition, the ranked table with filter
// tabs, Forces directory rail. 35-vs-41 wrinkle left visible on purpose.
//
// One clock (addendum #2): the table and counts run on the BOARD's date;
// TODAY runs on the edition's date and says so when the two differ (the
// newspaper lags the board). The Book line is drawn from the scorecard —
// its returns, its open-lot count, its first lot as the since-date —
// never from the edition masthead.

import Link from "next/link";
import {
  cropWords,
  firstLotDate,
  getBoard,
  getNarrativesLanding,
  getReportLatest,
  getScorecard,
  getWire,
  openLotCounts,
  reconcileWithBook,
} from "@/lib/api";
import Chrome from "@/components/mock/Chrome";
import HomeTable from "@/components/mock/HomeTable";

export const metadata = { title: "The Board" };

const TIER_DOT: [string, string][] = [
  ["Strong Buy", "var(--tier-sb)"],
  ["Buy", "var(--tier-buy)"],
  ["Watch", "var(--tier-watch)"],
];

const fmtPct = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
const nice = (d: string) =>
  new Date(d + "T00:00:00").toLocaleDateString("en-GB", {
    day: "numeric", month: "short",
  });

export default async function HomeMock() {
  const [board, report, landing, sc, wire] = await Promise.all([
    getBoard(),
    getReportLatest(),
    getNarrativesLanding(),
    getScorecard(),
    getWire(),
  ]);
  const m = report.masthead;
  const names = [...board.board, ...board.off_board].map((e) => ({
    symbol: e.symbol, company: e.company, tier: e.tier,
  }));
  const withCall = board.board.length;
  const counts = [board.counts.strong_buy, board.counts.buy, board.counts.watch];
  const lots = openLotCounts(sc);
  const since = firstLotDate(sc);
  const today = [
    ...(report.top_story ? [report.top_story] : []),
    ...report.sections.filter((s) => s.headline && s.symbol),
  ]
    .slice(0, 3)
    .map((s) => ({
      ...s,
      headline: reconcileWithBook(s.headline, s.symbol ? (lots[s.symbol] ?? 0) : 0),
    }));
  const weakening = landing.weakening.filter((w) => w.net_30d < 0);

  return (
    <>
      <Chrome names={names} active="The Board" context={`board ${board.date}`} />

      {/* one-line masthead */}
      <div className="border-b border-hairline bg-surface">
        <div className="num mx-auto flex max-w-[1280px] flex-wrap items-baseline gap-x-5 gap-y-1 px-6 py-2 text-[12.5px] text-ink-2">
          <span>{board.counts.universe} covered</span>
          <span><b>{m.board} on the board</b></span>
          {TIER_DOT.map(([tier, color], i) => (
            <span key={tier} className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-2" style={{ background: color }} />
              {counts[i]} {tier}
            </span>
          ))}
          <span className="text-ink-3">
            the edition counts {m.board}; {withCall} carry a call today
          </span>
          {sc.n_lots > 0 && (
            <Link href="/record" className="ml-auto hover:underline">
              <span className="kicker mr-1 text-[10px]">Book</span>
              <b style={{ color: sc.portfolio_return_pct >= 0 ? "var(--up)" : "var(--down)" }}>
                {fmtPct(sc.portfolio_return_pct)}
              </b>{" "}
              vs SPY{" "}
              <b style={{ color: sc.spy_return_pct >= 0 ? "var(--up)" : "var(--down)" }}>
                {fmtPct(sc.spy_return_pct)}
              </b>{" "}
              since {nice(since)} · {sc.open_lots} open lots
            </Link>
          )}
        </div>
      </div>

      <main className="mx-auto max-w-[1280px] px-6 py-6">
        <div className="grid grid-cols-1 gap-10 xl:grid-cols-[minmax(0,1fr)_300px]">
          <div>
            {/* TODAY */}
            {today.length > 0 && (
              <section className="mb-6">
                <div className="mb-1.5 flex items-baseline border-b border-ink pb-1">
                  <span className="kicker">
                    Today
                    {report.date !== board.date && (
                      <span className="normal-case tracking-normal text-ink-3">
                        {" "}· edition {nice(report.date)}
                      </span>
                    )}
                  </span>
                  <Link href="/changed" className="num ml-auto text-[12px] text-ink-2 hover:underline">
                    all {m.changes} moves in the edition →
                  </Link>
                </div>
                {today.map((s, i) => (
                  <Link
                    key={i}
                    href={s.symbol ? `/companies/${s.symbol}` : "/changed"}
                    className="group grid grid-cols-[3.4rem_minmax(0,1fr)] gap-x-4 border-b border-hairline py-2 last:border-b-0"
                  >
                    <span className="num pt-0.5 text-[11px] font-semibold tracking-[0.05em] text-ink-3">
                      {s.symbol}
                    </span>
                    <span className="text-[13.5px] font-semibold leading-snug group-hover:underline">
                      {s.headline}
                    </span>
                  </Link>
                ))}
              </section>
            )}

            <HomeTable rows={board.board} />
          </div>

          {/* right rail */}
          <aside>
            {/* News Wire pane above Forces (Edmund 2026-08-19, FIXPACK
                B2b): one-line filing headlines from the earnings feed —
                never the report writer's headlines — each cropped, never
                rewritten, linking into its item on the wire. No scores or
                tier badges here: it is news, not a rating. Nulls omitted;
                observed dates only; newest first, capped at 5. */}
            {wire.items.length > 0 && (
              <>
                <div className="mb-1.5 flex items-baseline border-b border-ink pb-1">
                  <span className="kicker">News Wire</span>
                  <Link href="/wire" className="num ml-auto text-[12px] text-ink-2 hover:underline">
                    all →
                  </Link>
                </div>
                <div className="mb-7">
                  {wire.items.slice(0, 5).map((it) => {
                    // one shared character budget: the company takes its
                    // short form (≤18 chars, board-style), the snippet
                    // gets the remaining width — both cropped at word
                    // boundaries, never rewritten (B2b). The CSS truncate
                    // is only a safety net.
                    const name = it.company ? cropWords(it.company, 18) : null;
                    const budget = Math.max(42 - (name ? name.length + 3 : 0), 18);
                    return (
                      <Link
                        key={it.id}
                        href={`/wire#f${it.id}`}
                        className="flex items-baseline gap-2 border-b border-hairline px-1 py-2 last:border-b-0 hover:bg-surface"
                      >
                        <span className="num shrink-0 text-[10.5px] font-bold tracking-[0.05em]">
                          {it.symbol}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-[12px] text-ink-2">
                          {name && (
                            <>
                              <span className="font-semibold text-ink">{name}</span>{" "}
                              —{" "}
                            </>
                          )}
                          {cropWords(it.headline, budget)}
                        </span>
                        {it.date && (
                          <span className="num shrink-0 text-[10.5px] text-ink-3">
                            {nice(it.date)}
                          </span>
                        )}
                      </Link>
                    );
                  })}
                </div>
              </>
            )}

            <div className="mb-1.5 flex items-baseline border-b border-ink pb-1">
              <span className="kicker">Forces</span>
              <Link href="/forces" className="num ml-auto text-[12px] text-ink-2 hover:underline">
                all →
              </Link>
            </div>
            <div className="mb-2 grid grid-cols-[minmax(0,1fr)_auto_auto] gap-x-4 px-1 py-1">
              {["Force", "wt", "n"].map((h) => (
                <span key={h} className="kicker text-[9.5px]">{h}</span>
              ))}
            </div>
            <div className="mb-7">
              {landing.forces.map((f) => (
                <Link
                  key={f.id}
                  href={`/forces/${f.id}`}
                  className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-baseline gap-x-4 border-b border-hairline px-1 py-2 last:border-b-0 hover:bg-surface"
                >
                  <span className="min-w-0 truncate text-[12.5px] font-semibold">{f.name}</span>
                  <span className="num text-[12px]">{f.board_weight.toFixed(0)}</span>
                  <span className="num text-[12px] text-ink-3">{f.board_companies}</span>
                </Link>
              ))}
            </div>

            <div className="kicker mb-1.5 border-b border-ink pb-1">Losing support</div>
            <div>
              {weakening.length === 0 && (
                <p className="px-1 py-2 text-[12px] italic text-ink-3">nothing on net right now</p>
              )}
              {weakening.map((w) => (
                <div key={w.id} className="flex items-baseline justify-between gap-3 border-b border-hairline px-1 py-2 last:border-b-0">
                  <span className="min-w-0 truncate text-[12.5px] font-semibold">{w.name}</span>
                  <span className="num shrink-0 text-[12px]" style={{ color: "var(--down)" }}>
                    {w.net_30d}
                  </span>
                </div>
              ))}
            </div>
          </aside>
        </div>
      </main>
    </>
  );
}
