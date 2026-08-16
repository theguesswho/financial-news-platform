// MOCK — What changed: the daily edition as a full newspaper. Every move
// with its plain-words why, grouped; past editions reachable by date.

import Link from "next/link";
import {
  getBoard,
  getReport,
  getReportLatest,
  getScorecard,
  fixPlurals,
  openLotCounts,
  reconcileWithBook,
} from "@/lib/api";
import Chrome from "@/components/mock/Chrome";

export const metadata = { title: "What changed" };

const SECTION_ORDER = ["moves", "coverage", "birth"];
const SECTION_TITLES: Record<string, string> = {
  moves: "Moves",
  coverage: "Coverage",
  birth: "New narratives",
};
const KIND_TITLES: Record<string, string> = {
  downgrade: "Downgrades",
  upgrade: "Upgrades",
  entry: "Entries",
  exit: "Exits",
};

export default async function ChangedMock({
  searchParams,
}: {
  searchParams: Promise<{ date?: string }>;
}) {
  const { date } = await searchParams;
  const [board, report, sc] = await Promise.all([
    getBoard(),
    date ? getReport(date) : getReportLatest(),
    getScorecard(),
  ]);
  const names = [...board.board, ...board.off_board].map((e) => ({
    symbol: e.symbol, company: e.company, tier: e.tier,
  }));
  const m = report.masthead;
  // Never contradict the book (addendum #4): a body claiming we hold
  // nothing while the scorecard has open lots in that name gets the
  // sentence replaced with the open-lot fact. Every symbol, every
  // edition — no special-casing.
  const lots = openLotCounts(sc);
  const fix = <T extends { symbol: string | null; headline: string; body?: string }>(
    s: T
  ): T => {
    const n = s.symbol ? (lots[s.symbol] ?? 0) : 0;
    return {
      ...s,
      headline: reconcileWithBook(s.headline, n),
      body: s.body ? reconcileWithBook(s.body, n) : s.body,
    };
  };

  // moves grouped by kind in a fixed honest order (downgrades first is
  // deliberate — bad news never below the fold), then other sections.
  const stories = [
    ...(report.top_story ? [{ ...report.top_story, section: "moves" }] : []),
    ...report.sections,
  ].map(fix);
  const seen = new Set<string>();
  const uniq = stories.filter((s) => {
    const k = `${s.kind}·${s.symbol}·${s.headline}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
  const moves = uniq.filter((s) => (s.section ?? "moves") === "moves");
  const movesByKind = (["downgrade", "exit", "entry", "upgrade"] as const)
    .map((kind) => ({ kind, items: moves.filter((s) => s.kind === kind) }))
    .filter((g) => g.items.length > 0);
  const otherKinds = moves.filter(
    (s) => !["downgrade", "exit", "entry", "upgrade"].includes(s.kind)
  );
  const rest = SECTION_ORDER.slice(1)
    .map((sec) => ({ sec, items: uniq.filter((s) => s.section === sec) }))
    .filter((g) => g.items.length > 0);

  const niceDate = new Date(report.date + "T00:00:00").toLocaleDateString("en-GB", {
    weekday: "short", day: "numeric", month: "short", year: "numeric",
  });

  return (
    <>
      <Chrome names={names} active="What changed" context={`edition ${report.date}`} />
      <main className="mx-auto max-w-[900px] px-6 py-8">
        <div className="kicker">
          {niceDate} · {m.changes} moves
          {m.changes_breakdown && <> · {fixPlurals(m.changes_breakdown)}</>}
        </div>
        <h1 className="mb-2 border-b-2 border-ink pb-3 text-[28px] font-bold tracking-tight">
          What changed
        </h1>
        <nav className="num mb-8 flex flex-wrap gap-x-3 gap-y-1 text-[12px] text-ink-3">
          {report.dates?.map((d) => (
            <Link key={d} href={d === report.date ? "#" : `/changed?date=${d}`}
              className={d === report.date ? "font-bold text-ink" : "hover:underline"}>
              {d}
            </Link>
          ))}
        </nav>

        {[...movesByKind, ...(otherKinds.length ? [{ kind: "other", items: otherKinds }] : [])].map(
          ({ kind, items }) => (
            <section key={kind} className="mb-8">
              <div className="kicker mb-2 border-b border-ink pb-1">
                {KIND_TITLES[kind] ?? "Also"}
              </div>
              {items.map((s, i) => (
                <article key={i} className="grid grid-cols-[3.4rem_minmax(0,1fr)] gap-x-4 border-b border-hairline py-3 last:border-b-0">
                  <span className="num pt-0.5 text-[11.5px] font-semibold text-ink-3">
                    {s.symbol ? (
                      <Link href={`/companies/${s.symbol}`} className="hover:underline">{s.symbol}</Link>
                    ) : ""}
                  </span>
                  <div>
                    <h3 className="mb-1 text-[15px] font-bold leading-snug">
                      {s.symbol ? (
                        <Link href={`/companies/${s.symbol}`} className="hover:underline">{s.headline}</Link>
                      ) : s.headline}
                    </h3>
                    {s.body && (
                      <p className="text-[13px] leading-relaxed text-ink-2">{s.body}</p>
                    )}
                  </div>
                </article>
              ))}
            </section>
          )
        )}

        {rest.map(({ sec, items }) => (
          <section key={sec} className="mb-8">
            <div className="kicker mb-2 border-b border-ink pb-1">
              {SECTION_TITLES[sec] ?? sec}
            </div>
            {items.map((s, i) => (
              <article key={i} className="grid grid-cols-[3.4rem_minmax(0,1fr)] gap-x-4 border-b border-hairline py-3 last:border-b-0">
                <span className="num pt-0.5 text-[11.5px] font-semibold text-ink-3">
                  {s.symbol ? (
                    <Link href={`/companies/${s.symbol}`} className="hover:underline">{s.symbol}</Link>
                  ) : ""}
                </span>
                <div>
                  <h3 className="mb-1 text-[15px] font-bold leading-snug">{s.headline}</h3>
                  {s.body && <p className="text-[13px] leading-relaxed text-ink-2">{s.body}</p>}
                </div>
              </article>
            ))}
          </section>
        ))}
      </main>
    </>
  );
}
