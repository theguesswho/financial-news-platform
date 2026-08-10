// Variant C — "The signature row". The view designed row-first: the exact
// anatomy a Board line will have, shown closed for three stocks and open
// for the selected one. Proves the Board = this view collapsed.

import { BoardEntry, Stock } from "@/lib/api";
import { BandStrip, componentSeries, fmt, pct, scored, Sparkline, TierChip } from "./shared";

function MiniBar({ v }: { v: number | null }) {
  return (
    <div className="h-[5px] w-[52px] rounded-full bg-hairline">
      {v != null && (
        <div
          className="h-full rounded-full bg-ink-2"
          style={{ width: `${Math.min(v * 10, 100)}%` }}
        />
      )}
    </div>
  );
}

function Row({ e, active }: { e: BoardEntry; active?: boolean }) {
  return (
    <div
      className={`grid grid-cols-[2.2rem_minmax(10rem,1.4fr)_auto_1fr_auto_auto] items-center gap-x-5 border-b border-hairline px-4 py-3 ${active ? "bg-page" : ""}`}
    >
      <span className="num text-[13px] text-ink-3">{e.rank ?? "—"}</span>
      <span className="min-w-0">
        <span className="font-bold">{e.symbol}</span>{" "}
        <span className="block truncate text-[12px] text-ink-2 sm:inline">
          {e.company}
        </span>
      </span>
      <TierChip tier={e.tier} grace={false} />
      <span className="hidden justify-self-center md:block">
        <BandStrip score={e.score} width={190} height={22} />
      </span>
      <span className="hidden items-center gap-3 lg:flex">
        {(["quality", "value", "gap"] as const).map((k) => (
          <span key={k} className="flex flex-col items-start gap-0.5">
            <span className="num text-[12px] font-semibold">{fmt(e.components[k === "gap" ? "gap" : k])}</span>
            <MiniBar v={e.components[k]} />
          </span>
        ))}
      </span>
      <span className="num justify-self-end text-[17px] font-bold">{fmt(e.score)}</span>
    </div>
  );
}

export default function VariantC1({
  stock,
  neighbors,
}: {
  stock: Stock;
  neighbors: BoardEntry[]; // the selected stock's row + two nearby board rows
}) {
  const pts = scored(stock.history);
  const trail = pts.slice(-30, -1).map((p) => p.score);
  return (
    <div className="overflow-hidden rounded-xl border border-hairline bg-surface">
      <div className="grid grid-cols-[2.2rem_minmax(10rem,1.4fr)_auto_1fr_auto_auto] gap-x-5 border-b border-hairline px-4 py-2">
        {["#", "Company", "Tier", "Where it sits", "Quality · Value · Gap", "Score"].map((h) => (
          <span key={h} className="kicker hidden text-[10px] first:block sm:block">
            {h}
          </span>
        ))}
      </div>

      {neighbors.map((e) => (
        <Row key={e.symbol} e={e} active={e.symbol === stock.symbol} />
      ))}

      {/* the same row, open */}
      <div className="bg-page px-5 py-5">
        <div className="mb-3 flex flex-wrap items-baseline gap-x-4">
          <span className="kicker">the row, opened</span>
          <span className="text-[12px] text-ink-3">
            clicking a row unfolds the same view — nothing new to learn
          </span>
        </div>
        <div className="grid grid-cols-1 gap-6 md:grid-cols-[minmax(16rem,1.1fr)_1fr]">
          <div>
            <BandStrip score={stock.score} trail={trail} width={300} height={44} showLabels />
            <div className="mb-4 text-[11.5px] text-ink-3">
              today&apos;s reading with the last 30 behind it
            </div>
            {stock.assessment?.rationale && (
              <p className="max-w-[42ch] text-[13px] leading-relaxed text-ink-2">
                {stock.assessment.rationale.slice(0, 220)}
                {stock.assessment.rationale.length > 220 ? "…" : ""}
              </p>
            )}
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {(
              [
                ["quality", "Quality", "durable business"],
                ["value", "Value", "price vs true peers"],
                ["gap", "Narrative gap",
                  stock.priced_in != null
                    ? `${pct(1 - stock.priced_in)} of the story unpriced`
                    : "story the price ignores"],
              ] as const
            ).map(([key, label, sub]) => (
              <div key={key}>
                <div className="kicker">{label}</div>
                <div className="num text-[20px] font-bold">{fmt(stock.components[key])}</div>
                <Sparkline points={componentSeries(stock.history, key)} width={110} height={28} />
                <div className="text-[11px] text-ink-3">{sub}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
