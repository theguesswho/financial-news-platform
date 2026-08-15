// Phase-2 lab, round 2: user narrowed to B and C — two refinements of
// each. B1/B2 test the judgment strip (state vs trajectory); C1/C2 test
// the row (position vs movement). The chosen form graduates into
// Companies and (collapsed) The Board.

import { getBoard, getStock } from "@/lib/api";
import VariantB1 from "@/components/signature/VariantB1";
import VariantB2 from "@/components/signature/VariantB2";
import VariantC1 from "@/components/signature/VariantC1";
import VariantC2 from "@/components/signature/VariantC2";

export const metadata = { title: "Signature view lab" };

export default async function SignatureLab({
  searchParams,
}: {
  searchParams: Promise<{ symbol?: string }>;
}) {
  const board = await getBoard();
  const symbol = (await searchParams).symbol?.toUpperCase() ?? board.board[0]?.symbol;
  const stock = await getStock(symbol);

  const options = board.board.map((e) => ({
    symbol: e.symbol,
    company: e.company,
    tier: e.tier,
  }));

  const idx = board.board.findIndex((e) => e.symbol === symbol);
  const neighbors =
    idx >= 0
      ? board.board.slice(Math.max(0, idx - 1), Math.max(0, idx - 1) + 3)
      : board.board.slice(0, 3);

  // C2 sample: rows around the selection plus the day's movers, so the
  // "what changed" column is exercised by real cases, not placeholders.
  const movers = board.board.filter(
    (e) => e.is_new || e.tier_move || e.exit_grace || (e.rank_change ?? 0) !== 0
  );
  const c2set = [...neighbors];
  for (const m of movers) {
    if (c2set.length >= 7) break;
    if (!c2set.some((e) => e.symbol === m.symbol)) c2set.push(m);
  }
  c2set.sort((a, b) => (a.rank ?? 99) - (b.rank ?? 99));

  return (
    <main className="mx-auto max-w-[1060px] px-6 py-10">
      <div className="kicker">Phase 2 · design lab · round 2</div>
      <h1 className="mb-1 text-[28px] font-bold tracking-tight">The signature view</h1>
      <p className="mb-8 max-w-[68ch] text-[14px] text-ink-2">
        Narrowed to the B and C families, two refinements each — all live on
        the {board.date} snapshot. The B variants carry the real company
        toggle the dossier will use: a dropdown over the board plus
        prev/next stepping in rank order.
      </p>

      <section className="mb-10">
        <div className="kicker mb-2">B1 — triptych with the band ruler</div>
        <p className="mb-3 max-w-[68ch] text-[13px] text-ink-3">
          Judgment as <b>state</b>: where the score sits today, the last 30
          readings as a fading trail. Calmest form.
        </p>
        <VariantB1 stock={stock} options={options} />
      </section>

      <section className="mb-10">
        <div className="kicker mb-2">B2 — triptych with the path</div>
        <p className="mb-3 max-w-[68ch] text-[13px] text-ink-3">
          Judgment as <b>trajectory</b>: the composite&apos;s route through the
          bands, so &quot;how it got here&quot; needs no extra click.
        </p>
        <VariantB2 stock={stock} options={options} />
      </section>

      <section className="mb-10">
        <div className="kicker mb-2">C1 — the position row</div>
        <p className="mb-3 max-w-[68ch] text-[13px] text-ink-3">
          Each row carries the band strip — where every stock sits, scanned
          vertically. Opened state shows the row unfolding into the dossier.
        </p>
        <VariantC1 stock={stock} neighbors={neighbors} />
      </section>

      <section className="mb-10">
        <div className="kicker mb-2">C2 — the movement row</div>
        <p className="mb-3 max-w-[68ch] text-[13px] text-ink-3">
          The band strip gives way to <b>what changed</b> — NEW, raises and
          lowers, rank moves, grace seats — straight from the board payload.
          The sample below includes today&apos;s actual movers.
        </p>
        <VariantC2 rows={c2set} active={symbol} />
      </section>
    </main>
  );
}
