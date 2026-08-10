// The Board — front door. Reading the instrument: the current opportunity
// set, ranked and tiered, movement visible, countdowns honest.

import { getBoard } from "@/lib/api";
import BoardRow, { BoardHeader } from "@/components/board/BoardRow";

export const metadata = { title: "The Board" };

export default async function TheBoard() {
  const board = await getBoard();
  const groups = (["Strong Buy", "Buy", "Watch"] as const).map((tier) => ({
    tier,
    rows: board.board.filter((e) => e.tier === tier),
  }));
  const c = board.counts;

  return (
    <main className="mx-auto max-w-[1100px] px-6 py-10">
      <div className="kicker">as of {board.date}</div>
      <h1 className="mb-1 text-[28px] font-bold tracking-tight">The Board</h1>
      <p className="mb-8 max-w-[72ch] text-[14px] text-ink-2">
        Every stock the instrument currently rates, scored 0–10 through one
        identical lens and ranked by conviction: {c.strong_buy} Strong{" "}
        {c.strong_buy === 1 ? "Buy" : "Buys"}, {c.buy} {c.buy === 1 ? "Buy" : "Buys"},{" "}
        {c.watch} on Watch{c.new > 0 && (
          <>
            {" "}— {c.new} new today
          </>
        )}. Click any row for the instrument&apos;s call — the reasoning, the
        bull case, and the bear case.
      </p>

      {groups.map(
        ({ tier, rows }) =>
          rows.length > 0 && (
            <section key={tier} className="mb-8">
              <div className="kicker mb-2">
                {tier}
                {tier === "Strong Buy" && " — the instrument's strongest calls"}
                {tier === "Watch" && " — on the board, conviction thinner"}
              </div>
              <div className="overflow-hidden rounded-xl border border-hairline bg-surface">
                <BoardHeader />
                {rows.map((e) => (
                  <BoardRow key={e.symbol} e={e} />
                ))}
              </div>
            </section>
          )
      )}

      {board.off_board.length > 0 && (
        <section className="mb-8">
          <div className="kicker mb-2">below the line</div>
          <p className="mb-2 max-w-[72ch] text-[12.5px] text-ink-3">
            Nearest the Watch line ({"≥"}3.0) of the{" "}
            {board.off_board.length} covered names currently off the board —
            every one scored through the same lens, none hidden.
          </p>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-ink-2">
            {board.off_board
              .filter((e) => (e.score_raw ?? 0) >= 3.0)
              .map((e) => (
                <span key={e.symbol} className="num">
                  <b>{e.symbol}</b> {fmtScore(e.score_raw)}
                </span>
              ))}
          </div>
        </section>
      )}
    </main>
  );
}

function fmtScore(v: number | null) {
  return v == null ? "—" : v.toFixed(1);
}
