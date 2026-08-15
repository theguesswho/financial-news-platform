// MOCK — the product home (Board as landing). One-line masthead with the
// tier counts and the Book-vs-SPY proof (linked to Track record), TODAY
// headlines linking into the full edition, the ranked table with filter
// tabs, Forces directory rail. 35-vs-41 wrinkle left visible on purpose.

import Link from "next/link";
import { getBoard, getNarrativesLanding, getReportLatest } from "@/lib/api";
import Chrome from "@/components/mock/Chrome";
import HomeTable from "@/components/mock/HomeTable";

export const metadata = { title: "The Board" };

const TIER_DOT: [string, string][] = [
  ["Strong Buy", "var(--tier-sb)"],
  ["Buy", "var(--tier-buy)"],
  ["Watch", "var(--tier-watch)"],
];

export default async function HomeMock() {
  const [board, report, landing] = await Promise.all([
    getBoard(),
    getReportLatest(),
    getNarrativesLanding(),
  ]);
  const m = report.masthead;
  const names = [...board.board, ...board.off_board].map((e) => ({
    symbol: e.symbol, company: e.company, tier: e.tier,
  }));
  const withCall = board.board.length;
  const counts = [board.counts.strong_buy, board.counts.buy, board.counts.watch];
  const today = [
    ...(report.top_story ? [report.top_story] : []),
    ...report.sections.filter((s) => s.headline && s.symbol),
  ].slice(0, 3);
  const weakening = landing.weakening.filter((w) => w.net_30d < 0);

  return (
    <>
      <Chrome names={names} active="The Board" context={`edition ${report.date}`} />

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
          {m.us_pct != null && m.spy_pct != null && (
            <Link href="/record" className="ml-auto hover:underline">
              <span className="kicker mr-1 text-[10px]">Book</span>
              <b style={{ color: m.us_pct >= 0 ? "var(--up)" : "var(--down)" }}>
                {m.us_pct >= 0 ? "+" : ""}{m.us_pct}%
              </b>{" "}
              vs SPY{" "}
              <b style={{ color: m.spy_pct >= 0 ? "var(--up)" : "var(--down)" }}>
                {m.spy_pct >= 0 ? "+" : ""}{m.spy_pct}%
              </b>{" "}
              since {m.since} · {m.positions} positions
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
                  <span className="kicker">Today</span>
                  <Link href="/changed" className="num ml-auto text-[12px] text-ink-2 hover:underline">
                    all {m.changes} moves →
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
