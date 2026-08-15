"use client";

// Track record — aggregation first, lots on demand. One row per name
// (its lots vs their SPY twins combined), expandable to the daily lots.
// Losses and wins identical treatment; sorted by capital at work.

import { useState } from "react";
import { ScorecardLot } from "@/lib/api";

const pctColor = (v: number) =>
  v > 0 ? "var(--up)" : v < 0 ? "var(--down)" : "var(--ink-2)";
const fmtPct = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
const nice = (d: string) =>
  new Date(d + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short" });

type Agg = {
  symbol: string;
  lots: ScorecardLot[];
  invested: number;
  stock_value: number;
  spy_value: number;
  vs_spy_pct: number;
  open: number;
  closed: number;
  beating: number;
};

function aggregate(lots: ScorecardLot[]): Agg[] {
  const by = new Map<string, ScorecardLot[]>();
  for (const l of lots) by.set(l.symbol, [...(by.get(l.symbol) ?? []), l]);
  return [...by.entries()]
    .map(([symbol, ls]) => {
      const invested = ls.reduce((s, l) => s + l.invested, 0);
      const stock = ls.reduce((s, l) => s + l.stock_value, 0);
      const spy = ls.reduce((s, l) => s + l.spy_value, 0);
      return {
        symbol,
        lots: [...ls].sort((a, b) => a.lot_date.localeCompare(b.lot_date)),
        invested,
        stock_value: stock,
        spy_value: spy,
        vs_spy_pct: spy > 0 ? ((stock - spy) / spy) * 100 : 0,
        open: ls.filter((l) => !l.closed).length,
        closed: ls.filter((l) => l.closed).length,
        beating: ls.filter((l) => l.beat).length,
      };
    })
    .sort((a, b) => b.invested - a.invested);
}

function NameRow({ a, company }: { a: Agg; company: string | null }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className={`grid w-full grid-cols-[minmax(9rem,1fr)_auto_auto_auto_auto] items-baseline gap-x-5 border-b border-hairline px-4 py-2.5 text-left last:border-b-0 hover:bg-page ${open ? "bg-page" : ""}`}
      >
        <span className="min-w-0 truncate">
          <span className="font-bold">{a.symbol}</span>{" "}
          <span className="text-[12px] text-ink-2">{company}</span>{" "}
          <span className={`inline-block text-[9px] text-ink-3 transition-transform ${open ? "rotate-90" : ""}`}>▶</span>
        </span>
        <span className="num text-[12px] text-ink-3">
          {a.lots.length} {a.lots.length === 1 ? "lot" : "lots"} · ${a.invested.toFixed(0)}
        </span>
        <span className="num text-[12px] text-ink-2">
          {a.closed > 0 && a.open === 0 ? "closed" : a.closed > 0 ? `${a.open} open · ${a.closed} closed` : "open"}
        </span>
        <span className="num text-[12px] text-ink-2">{a.beating}/{a.lots.length} beating</span>
        <span className="num justify-self-end text-[14px] font-bold" style={{ color: pctColor(a.vs_spy_pct) }}>
          {fmtPct(a.vs_spy_pct)}
        </span>
      </button>
      {open && (
        <div className="border-b border-hairline bg-page px-4 py-3 last:border-b-0">
          <div className="grid grid-cols-[auto_auto_auto_auto_auto_auto] gap-x-6 gap-y-1 text-[12px]">
            {["Lot", "Stock", "SPY twin", "vs SPY", "Beat", "Exit"].map((h) => (
              <span key={h} className="kicker text-[9.5px]">{h}</span>
            ))}
            {a.lots.map((l) => (
              <FragmentRow key={l.lot_date + l.symbol} l={l} />
            ))}
          </div>
          <p className="mt-2 text-[11px] text-ink-3">
            each lot is $100 at that day&apos;s close, paired against $100 of SPY the same day
          </p>
        </div>
      )}
    </>
  );
}

function FragmentRow({ l }: { l: ScorecardLot }) {
  return (
    <>
      <span className="num">{nice(l.lot_date)}</span>
      <span className="num">{l.stock_value.toFixed(2)}</span>
      <span className="num">{l.spy_value.toFixed(2)}</span>
      <span className="num font-semibold" style={{ color: pctColor(l.vs_spy_pct) }}>
        {fmtPct(l.vs_spy_pct)}
      </span>
      <span className="num text-ink-2">{l.beat ? "yes" : "no"}</span>
      <span className="num text-ink-2">{l.exit_date ? nice(l.exit_date) : "—"}</span>
    </>
  );
}

export default function RecordTable({
  lots,
  companies,
}: {
  lots: ScorecardLot[];
  companies: Record<string, string | null>;
}) {
  const aggs = aggregate(lots);
  return (
    <div className="overflow-hidden rounded-lg border border-hairline bg-surface">
      {aggs.map((a) => (
        <NameRow key={a.symbol} a={a} company={companies[a.symbol] ?? null} />
      ))}
    </div>
  );
}
