// MOCK — Track record. The proof behind the masthead's Book-vs-SPY line:
// $100 lots against paired SPY twins, aggregated per name first, daily
// lots on demand. Losses shown with the same weight as wins.

import { getBoard, getScorecard } from "@/lib/api";
import Chrome from "@/components/mock/Chrome";
import RecordTable from "@/components/mock/RecordTable";

export const metadata = { title: "Track record" };

const fmtPct = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;

export default async function RecordMock() {
  const [board, sc] = await Promise.all([getBoard(), getScorecard()]);
  const names = [...board.board, ...board.off_board].map((e) => ({
    symbol: e.symbol, company: e.company, tier: e.tier,
  }));
  const companies = Object.fromEntries(names.map((n) => [n.symbol, n.company]));
  const firstLot = sc.lots.reduce(
    (min, l) => (l.lot_date < min ? l.lot_date : min),
    sc.lots[0]?.lot_date ?? ""
  );

  return (
    <>
      <Chrome names={names} active="Track record" context={`as of ${board.date}`} />
      <main className="mx-auto max-w-[1100px] px-6 py-8">
        <div className="kicker">Scorecard</div>
        <h1 className="mb-3 text-[28px] font-bold tracking-tight">Track record</h1>

        <div className="mb-1 flex flex-wrap items-baseline gap-x-4 text-[17px]">
          <b className="num" style={{ color: sc.portfolio_return_pct >= 0 ? "var(--up)" : "var(--down)" }}>
            {fmtPct(sc.portfolio_return_pct)}
          </b>
          <span className="text-[14px] text-ink-2">
            vs SPY{" "}
            <b className="num" style={{ color: sc.spy_return_pct >= 0 ? "var(--up)" : "var(--down)" }}>
              {fmtPct(sc.spy_return_pct)}
            </b>
          </span>
          {firstLot && <span className="text-[13px] text-ink-3">first lot {firstLot}</span>}
        </div>
        <div className="num mb-1 text-[13.5px] text-ink-2">
          <b>{sc.lots_beating_spy}</b> of {sc.n_lots} lots beating ·{" "}
          <b>{sc.open_lots}</b> open · <b>{sc.closed_lots}</b> closed
        </div>
        <p className="mb-7 text-[12.5px] text-ink-3">
          Not live capital: every Strong Buy day buys a $100 lot at the next
          close, paired against $100 of SPY bought the same day. {sc.n_lots}{" "}
          lots · ${sc.total_invested.toFixed(0)} at work, now worth $
          {sc.portfolio_value.toFixed(2)} vs the twins&apos; $
          {sc.spy_value.toFixed(2)}. Wins and losses both stay on this page.
        </p>

        <RecordTable lots={sc.lots} companies={companies} />
      </main>
    </>
  );
}
