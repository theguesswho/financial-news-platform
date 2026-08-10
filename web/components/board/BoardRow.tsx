"use client";

// The Board row — the signature view collapsed (C1 position anatomy with
// C2's movement language integrated, per DESIGN_BRIEF.md). Clicking a row
// expands it in place: the qualitative call, bull case, and bear case —
// all fields /board already returns. Full dossier is a link inside.

import Link from "next/link";
import { useState } from "react";
import { BoardEntry } from "@/lib/api";
import { BandStrip, fmt, TierChip } from "@/components/signature/shared";

// Mobile: rank / company / tier / score (movement folds under the name);
// md adds the movement + band-strip columns; lg adds Q·V·G.
export const ROW_GRID =
  "grid-cols-[1.6rem_minmax(0,1fr)_auto_auto] md:grid-cols-[2rem_minmax(9rem,1.35fr)_auto_minmax(8rem,auto)_1fr_auto_auto]";

function Movement({ e }: { e: BoardEntry }) {
  if (e.is_new)
    return (
      <span className="rounded border border-ink px-1 py-px text-[10px] font-bold tracking-[0.06em]">
        NEW
      </span>
    );
  if (e.tier_move)
    return (
      <span
        className="text-[12px] font-semibold"
        style={{ color: e.tier_move.direction === "up" ? "var(--up)" : "var(--down)" }}
      >
        {e.tier_move.direction === "up" ? "▲" : "▼"} from {e.tier_move.from}
      </span>
    );
  if (e.exit_grace)
    return <span className="text-[11.5px] text-ink-2 italic">grace seat</span>;
  if (e.rank_change)
    return (
      <span
        className="num text-[12px] font-semibold"
        style={{ color: e.rank_change > 0 ? "var(--up)" : "var(--down)" }}
      >
        {e.rank_change > 0 ? "▲" : "▼"}{Math.abs(e.rank_change)}
      </span>
    );
  return null;
}

// The judgment layer's standing adjustment — a badge, not a footnote.
// Distinct from the movement arrows (day-over-day) by role: this is where
// the assessor stands vs the data, colored on the up/down axis with a
// tinted wash so it reads as a state, not an event.
function QualBadge({ e }: { e: BoardEntry }) {
  if (e.qual_promoted)
    return (
      <span
        className="rounded px-1.5 py-px text-[10.5px] font-bold"
        style={{
          color: "var(--gap-accent)",
          background: "color-mix(in srgb, var(--gap-accent) 12%, transparent)",
        }}
      >
        narrative promoted
      </span>
    );
  if (!e.disagreement) return null;
  const raised = e.disagreement.kind === "raised";
  const col = raised ? "var(--up)" : "var(--down)";
  return (
    <span
      className="rounded px-1.5 py-px text-[10.5px] font-bold"
      style={{
        color: col,
        background: `color-mix(in srgb, ${col} 12%, transparent)`,
      }}
    >
      {raised ? "▲ judgment raised it" : "▼ judgment restrained it"}
    </span>
  );
}

function MiniBar({ v }: { v: number | null }) {
  return (
    <div className="h-[5px] w-[48px] rounded-full bg-hairline">
      {v != null && (
        <div
          className="h-full rounded-full bg-ink-2"
          style={{ width: `${Math.min(v * 10, 100)}%` }}
        />
      )}
    </div>
  );
}

export function BoardHeader() {
  return (
    <div className={`grid ${ROW_GRID} gap-x-5 border-b border-hairline px-4 py-2`}>
      {(
        [
          ["#", ""],
          ["Company", ""],
          ["Tier", ""],
          ["What changed", "hidden md:block"],
          ["Where it sits", "hidden md:block"],
          ["Quality · Value · Gap", "hidden lg:block"],
          ["Score", "justify-self-end"],
        ] as const
      ).map(([h, cls]) => (
        <span key={h} className={`kicker text-[10px] ${cls}`}>
          {h}
        </span>
      ))}
    </div>
  );
}

function ExpandedCall({ e }: { e: BoardEntry }) {
  return (
    <div className="border-b border-hairline bg-page px-5 py-4 last:border-b-0">
      {e.assessed && e.rationale ? (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1.2fr_1fr_1fr]">
          <div>
            <div className="kicker mb-1">
              The call{e.direction && e.direction !== "hold" ? ` — ${e.direction}` : ""}
            </div>
            <p className="max-w-[52ch] text-[13px] leading-relaxed text-ink-2">
              {e.rationale}
            </p>
          </div>
          {/* bull and bear get identical visual weight — standing rule */}
          <div>
            <div className="kicker mb-1">Bull case</div>
            <p className="max-w-[44ch] text-[13px] leading-relaxed text-ink-2">
              {e.key_bull ?? "—"}
            </p>
          </div>
          <div>
            <div className="kicker mb-1">Bear case</div>
            <p className="max-w-[44ch] text-[13px] leading-relaxed text-ink-2">
              {e.key_bear ?? "—"}
            </p>
          </div>
        </div>
      ) : (
        <p className="text-[13px] text-ink-2 italic">
          Not yet through the judgment layer — the score above is the data
          alone.
        </p>
      )}
      <div className="mt-3">
        <Link
          href={`/signature?symbol=${e.symbol}`}
          className="text-[12.5px] font-semibold underline decoration-hairline underline-offset-4 hover:decoration-ink"
        >
          full dossier →
        </Link>
      </div>
    </div>
  );
}

export default function BoardRow({ e }: { e: BoardEntry }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className={`grid ${ROW_GRID} w-full items-center gap-x-5 border-b border-hairline px-4 py-3 text-left last:border-b-0 hover:bg-page ${
          open ? "bg-page" : ""
        }`}
      >
        <span className="num text-[13px] text-ink-3">{e.rank ?? "—"}</span>
        <span className="min-w-0">
          <span className="font-bold">{e.symbol}</span>{" "}
          <span className="truncate text-[12px] text-ink-2 sm:inline">{e.company}</span>{" "}
          <span
            className={`inline-block text-[9px] text-ink-3 transition-transform ${open ? "rotate-90" : ""}`}
            aria-hidden
          >
            ▶
          </span>
          {e.disagreement && (
            <span className="block text-[10.5px] text-ink-3">
              instrument {e.disagreement.kind === "raised" ? "raised" : "restrained"} it —
              data alone says {e.disagreement.quant_tier}
            </span>
          )}
          <span className="mt-0.5 block md:hidden">
            <Movement e={e} />
          </span>
        </span>
        <span className="flex flex-col items-start gap-1">
          <TierChip tier={e.tier} />
          <QualBadge e={e} />
        </span>
        <span className="hidden md:block"><Movement e={e} /></span>
        <span className="hidden justify-self-center md:block">
          <BandStrip score={e.score} width={180} height={22} />
        </span>
        <span className="hidden items-center gap-3 lg:flex">
          {(["quality", "value", "gap"] as const).map((k) => (
            <span key={k} className="flex flex-col items-start gap-0.5">
              <span className="num text-[12px] font-semibold">{fmt(e.components[k])}</span>
              <MiniBar v={e.components[k]} />
            </span>
          ))}
        </span>
        <span className="num justify-self-end text-[17px] font-bold">{fmt(e.score)}</span>
      </button>
      {open && <ExpandedCall e={e} />}
    </>
  );
}
