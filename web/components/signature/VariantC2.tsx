// C2 — the movement row. Same anatomy as C1 but the band strip gives way
// to a "what changed" column driven entirely by fields /board already
// carries (NEW, tier moves, rank deltas, grace seats) — the news-hierarchy
// rule at row level, at zero extra query cost.

import { BoardEntry } from "@/lib/api";
import { fmt, TierChip } from "./shared";

function WhatChanged({ e }: { e: BoardEntry }) {
  if (e.is_new)
    return (
      <span className="text-[12px]">
        <span className="mr-1.5 rounded border border-ink px-1 py-px text-[10px] font-bold tracking-[0.06em]">
          NEW
        </span>
        first day on the board
      </span>
    );
  if (e.tier_move)
    return (
      <span
        className="text-[12px] font-semibold"
        style={{ color: e.tier_move.direction === "up" ? "var(--up)" : "var(--down)" }}
      >
        {e.tier_move.direction === "up" ? "▲ raised" : "▼ lowered"} from {e.tier_move.from}
      </span>
    );
  if (e.exit_grace)
    return (
      <span className="text-[12px] text-ink-2 italic">
        holding its seat — score below 3.4
      </span>
    );
  if (e.rank_change)
    return (
      <span
        className="num text-[12px]"
        style={{ color: e.rank_change > 0 ? "var(--up)" : "var(--down)" }}
      >
        {e.rank_change > 0 ? "▲" : "▼"} {Math.abs(e.rank_change)}{" "}
        {Math.abs(e.rank_change) === 1 ? "place" : "places"}
      </span>
    );
  return <span className="text-[12px] text-ink-3">steady</span>;
}

export default function VariantC2({
  rows,
  active,
}: {
  rows: BoardEntry[];
  active: string;
}) {
  const cols = "grid-cols-[2.2rem_minmax(10rem,1.3fr)_auto_minmax(11rem,1fr)_auto_auto]";
  return (
    <div className="overflow-hidden rounded-xl border border-hairline bg-surface">
      <div className={`grid ${cols} gap-x-5 border-b border-hairline px-4 py-2`}>
        {["#", "Company", "Tier", "What changed", "Quality · Value · Gap", "Score"].map((h) => (
          <span key={h} className="kicker hidden text-[10px] first:block sm:block">
            {h}
          </span>
        ))}
      </div>
      {rows.map((e) => (
        <div
          key={e.symbol}
          className={`grid ${cols} items-center gap-x-5 border-b border-hairline px-4 py-3 last:border-b-0 ${
            e.symbol === active ? "bg-page" : ""
          }`}
        >
          <span className="num text-[13px] text-ink-3">{e.rank ?? "—"}</span>
          <span className="min-w-0">
            <span className="font-bold">{e.symbol}</span>{" "}
            <span className="block truncate text-[12px] text-ink-2 sm:inline">{e.company}</span>
          </span>
          <TierChip tier={e.tier} />
          <WhatChanged e={e} />
          <span className="num hidden gap-3 text-[12.5px] lg:flex">
            {(["quality", "value", "gap"] as const).map((k) => (
              <span key={k} className="w-8 text-right font-semibold">{fmt(e.components[k])}</span>
            ))}
          </span>
          <span className="num justify-self-end text-[17px] font-bold">{fmt(e.score)}</span>
        </div>
      ))}
    </div>
  );
}
