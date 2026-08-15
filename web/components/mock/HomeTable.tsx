"use client";

// The home table: name-first rows, filter tabs, and two silent-by-default
// columns — Assessor (prints only when the judgment moved the call or
// changed its verdict) and Moved (prints only day-over-day change).
// Row body expands to bull / bear / rationale; the name opens the page.

import Link from "next/link";
import { useState } from "react";
import { BoardEntry } from "@/lib/api";
import { fmt, TierChip } from "@/components/signature/shared";

const GRID =
  "grid-cols-[1.8rem_minmax(9rem,1fr)_auto_auto] md:grid-cols-[1.8rem_minmax(11rem,0.9fr)_auto_auto_minmax(8rem,auto)_auto_minmax(0,1.2fr)]";

function Assessor({ e }: { e: BoardEntry }) {
  if (e.qual_promoted)
    return (
      <span className="text-[12px] font-semibold" style={{ color: "var(--gap-accent)" }}>
        narrative promoted
      </span>
    );
  if (e.disagreement) {
    const raised = e.disagreement.kind === "raised";
    return (
      <span
        className="text-[12px] font-semibold"
        style={{ color: raised ? "var(--up)" : "var(--down)" }}
      >
        {raised ? "raised" : "restrained"} from {e.disagreement.quant_tier}
      </span>
    );
  }
  if (e.direction === "upgrade" || e.direction === "downgrade")
    return (
      <span
        className="text-[12px] font-semibold"
        style={{ color: e.direction === "upgrade" ? "var(--up)" : "var(--down)" }}
      >
        {e.direction}
      </span>
    );
  return null; // hold is silence
}

function Moved({ e }: { e: BoardEntry }) {
  if (e.is_new)
    return (
      <span className="rounded border border-ink px-1 py-px text-[10px] font-bold tracking-[0.06em]">
        NEW
      </span>
    );
  if (e.tier_move)
    return (
      <span
        className="whitespace-nowrap text-[11.5px] font-semibold"
        style={{ color: e.tier_move.direction === "up" ? "var(--up)" : "var(--down)" }}
      >
        {e.tier_move.direction === "up" ? "▲" : "▼"} from {e.tier_move.from}
      </span>
    );
  if (e.exit_grace)
    return <span className="text-[11px] italic text-ink-2">grace seat</span>;
  if (e.rank_change)
    return (
      <span
        className="num text-[11.5px] font-semibold"
        style={{ color: e.rank_change > 0 ? "var(--up)" : "var(--down)" }}
      >
        {e.rank_change > 0 ? "▲" : "▼"}{Math.abs(e.rank_change)}
      </span>
    );
  return null;
}

const moved = (e: BoardEntry) =>
  e.is_new || !!e.tier_move || !!e.rank_change || e.exit_grace;

function Row({ e }: { e: BoardEntry }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <div
        role="button"
        tabIndex={0}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(ev) => ev.key === "Enter" && setOpen((v) => !v)}
        className={`grid ${GRID} cursor-pointer items-baseline gap-x-4 border-b border-hairline px-4 py-2.5 last:border-b-0 hover:bg-page ${open ? "bg-page" : ""}`}
      >
        <span className="num text-[12.5px] text-ink-3">{e.rank ?? "—"}</span>
        <span className="min-w-0">
          <Link
            href={`/companies/${e.symbol}`}
            onClick={(ev) => ev.stopPropagation()}
            className="block truncate text-[13.5px] font-bold leading-snug hover:underline"
          >
            {e.company ?? e.symbol}
          </Link>
          <span className="num text-[11px] tracking-[0.05em] text-ink-3">{e.symbol}</span>
        </span>
        <TierChip tier={e.tier} />
        <span className="num justify-self-end text-[15px] font-bold md:justify-self-auto">
          {fmt(e.score)}
        </span>
        <span className="hidden md:block"><Assessor e={e} /></span>
        <span className="hidden md:block"><Moved e={e} /></span>
        <span className="hidden truncate text-[12.5px] text-ink-2 md:block">
          {e.key_bull ?? ""}
        </span>
      </div>
      {open && (
        <div className="border-b border-hairline bg-page px-5 py-4 last:border-b-0">
          {e.rationale ? (
            <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
              <div>
                <div className="kicker mb-1" style={{ color: "var(--up)" }}>Bull</div>
                <p className="text-[13px] leading-relaxed text-ink-2">{e.key_bull ?? "—"}</p>
              </div>
              <div>
                <div className="kicker mb-1" style={{ color: "var(--down)" }}>Bear</div>
                <p className="text-[13px] leading-relaxed text-ink-2">{e.key_bear ?? "—"}</p>
              </div>
              <div>
                <div className="kicker mb-1">Rationale</div>
                <p className="text-[13px] leading-relaxed text-ink-2">{e.rationale}</p>
              </div>
            </div>
          ) : (
            <p className="text-[13px] italic text-ink-2">
              Not yet through the judgment layer — the score is the data alone.
            </p>
          )}
          <div className="mt-2">
            <Link
              href={`/companies/${e.symbol}`}
              className="text-[12.5px] font-semibold underline decoration-hairline underline-offset-4 hover:decoration-ink"
            >
              full page →
            </Link>
          </div>
        </div>
      )}
    </>
  );
}

const TIER_DOT: Record<string, string> = {
  "Strong Buy": "var(--tier-sb)",
  Buy: "var(--tier-buy)",
  Watch: "var(--tier-watch)",
};

export default function HomeTable({ rows }: { rows: BoardEntry[] }) {
  const [filter, setFilter] = useState<"all" | "strong" | "moved">("all");
  const visible =
    filter === "strong"
      ? rows.filter((e) => e.tier === "Strong Buy")
      : filter === "moved"
        ? rows.filter(moved)
        : rows;
  const groups = (["Strong Buy", "Buy", "Watch"] as const)
    .map((tier) => ({ tier, rows: visible.filter((e) => e.tier === tier) }))
    .filter((g) => g.rows.length > 0);

  const tab = (key: typeof filter, label: string) => (
    <button
      key={key}
      type="button"
      onClick={() => setFilter(key)}
      className={`text-[12.5px] ${filter === key ? "font-bold underline underline-offset-4" : "text-ink-2 hover:text-ink"}`}
    >
      {label}
    </button>
  );

  return (
    <div>
      <div className="mb-2 flex items-baseline gap-4 border-b border-ink pb-1.5">
        <span className="kicker">The Board</span>
        <span className="ml-auto flex gap-4">
          {tab("all", "All")}
          {tab("strong", "Strong Buy")}
          {tab("moved", "Moved")}
          <span className="num text-[12.5px] text-ink-3">{rows.length} with a call</span>
        </span>
      </div>
      <div className={`grid ${GRID} gap-x-4 px-4 py-1.5`}>
        {(
          [
            ["#", ""], ["Name", ""], ["Call", ""], ["Score", ""],
            ["Assessor", "hidden md:block"], ["Moved", "hidden md:block"],
            ["Story", "hidden md:block"],
          ] as const
        ).map(([h, cls]) => (
          <span key={h} className={`kicker text-[9.5px] ${cls}`}>{h}</span>
        ))}
      </div>
      {groups.map(({ tier, rows }) => (
        <section key={tier} className="mb-5">
          <div className="mb-1 flex items-center gap-2 px-1">
            <span className="inline-block h-2.5 w-2.5" style={{ background: TIER_DOT[tier] }} />
            <span className="kicker text-[10.5px]">{tier}</span>
            <span className="num text-[11px] text-ink-3">{rows.length}</span>
          </div>
          <div className="overflow-hidden rounded-lg border border-hairline bg-surface">
            {rows.map((e) => (
              <Row key={e.symbol} e={e} />
            ))}
          </div>
        </section>
      ))}
      {groups.length === 0 && (
        <p className="px-1 py-4 text-[13px] italic text-ink-3">nothing matches this filter today</p>
      )}
    </div>
  );
}
