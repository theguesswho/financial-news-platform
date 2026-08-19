// News Wire — the earnings/filings feed as its own page (FIXPACK
// 2026-08-19 Session B). Content is the Streamlit reference feed only
// (load_filings_intelligence): noteworthy narrative filings plus
// high-impact 8-Ks. Board moves belong to What changed; insiders stay
// off. Dated masthead + date archive like the report page; every date
// shown is the observed filing date. Nulls are omitted — an item
// missing a synopsis shows its headline, an off-board name shows no
// tier chip at all. Assessor stays dark (V3 #11 — nothing here touches
// it). Items carry id anchors (#f{id}) so the home rail can land on
// its line.

import Link from "next/link";
import { getBoard, getWire, getWireAt, WireItem } from "@/lib/api";
import Chrome from "@/components/mock/Chrome";
import { TIER_COLOR, fmt } from "@/components/signature/shared";

/** The board TierChip at wire-line scale — same tier colors, sized to
 * sit inside a 12.5px text line rather than dominate it. */
function SmallTierChip({ tier }: { tier: string }) {
  return (
    <span
      className="rounded px-1.5 py-px text-[10px] font-bold uppercase tracking-[0.05em]"
      style={{ color: "var(--surface)", background: TIER_COLOR[tier] ?? "var(--ink-3)" }}
    >
      {tier}
    </span>
  );
}

export const metadata = { title: "News Wire" };

const nice = (d: string) =>
  new Date(d + "T00:00:00").toLocaleDateString("en-GB", {
    weekday: "short", day: "numeric", month: "short",
  });

function Signals({ it }: { it: WireItem }) {
  const bits: React.ReactNode[] = [];
  if (it.signal != null)
    bits.push(
      <span key="sig" className="num text-[12px] text-ink-2">
        story strength {fmt(it.signal)} / 10
      </span>
    );
  if (it.signal_delta != null)
    bits.push(
      <span
        key="delta"
        className="num text-[12px] font-semibold"
        style={{ color: it.signal_delta > 0 ? "var(--up)" : "var(--down)" }}
      >
        {it.signal_delta > 0 ? "▲" : "▼"} {it.signal_delta > 0 ? "+" : ""}
        {fmt(it.signal_delta)} vs its last filing
      </span>
    );
  if (it.trajectory)
    bits.push(
      <span key="traj" className="text-[12px] text-ink-2">
        story {it.trajectory}
      </span>
    );
  if (it.tone)
    bits.push(
      <span key="tone" className="text-[12px] text-ink-2">
        management {it.tone}
      </span>
    );
  if (it.impact)
    bits.push(
      <span
        key="impact"
        className="text-[12px] font-semibold"
        style={{
          color:
            it.impact === "Positive"
              ? "var(--up)"
              : it.impact === "Negative"
                ? "var(--down)"
                : "var(--ink-2)",
        }}
      >
        read as {it.impact.toLowerCase()}
      </span>
    );
  if (bits.length === 0) return null;
  return <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1">{bits}</div>;
}

export default async function WirePage({
  searchParams,
}: {
  searchParams: Promise<{ date?: string }>;
}) {
  const { date } = await searchParams;
  const [board, wire] = await Promise.all([
    getBoard(),
    date ? getWireAt(date) : getWire(),
  ]);
  const names = [...board.board, ...board.off_board].map((e) => ({
    symbol: e.symbol, company: e.company, tier: e.tier,
  }));

  const niceDate = new Date(wire.date + "T00:00:00").toLocaleDateString("en-GB", {
    weekday: "short", day: "numeric", month: "short", year: "numeric",
  });

  return (
    <>
      <Chrome names={names} active="News Wire" context={`wire ${wire.date}`} />
      <main className="mx-auto max-w-[900px] px-6 py-8">
        <div className="kicker">
          {niceDate} · {wire.items.length} items · earnings calls, 10-K/Q
          reports and significant 8-K events from the last 14 days
        </div>
        <h1 className="mb-2 border-b-2 border-ink pb-3 text-[28px] font-bold tracking-tight">
          News Wire
        </h1>
        <nav className="num mb-8 flex flex-wrap gap-x-3 gap-y-1 text-[12px] text-ink-3">
          {wire.dates.map((d) => (
            <Link
              key={d}
              href={d === wire.date ? "#" : `/wire?date=${d}`}
              className={d === wire.date ? "font-bold text-ink" : "hover:underline"}
            >
              {d}
            </Link>
          ))}
        </nav>

        {wire.items.length === 0 && (
          <p className="py-4 text-[13px] italic text-ink-3">
            no noteworthy filings in this window
          </p>
        )}
        {wire.items.map((it) => (
          <article
            key={it.id}
            id={`f${it.id}`}
            className="grid scroll-mt-16 grid-cols-[3.4rem_minmax(0,1fr)] gap-x-4 border-b border-hairline py-3.5 last:border-b-0"
          >
            <span className="num pt-0.5 text-[11.5px] font-semibold text-ink-3">
              <Link href={`/companies/${it.symbol}`} className="hover:underline">
                {it.symbol}
              </Link>
            </span>
            <div>
              <div className="num mb-0.5 flex flex-wrap items-baseline gap-x-3 text-[11px] text-ink-3">
                <span className="font-semibold uppercase tracking-[0.06em]">
                  {it.type_label}
                </span>
                {it.date && <span>{nice(it.date)}</span>}
              </div>
              <h3 className="mb-0.5 text-[15px] font-bold leading-snug">
                <Link href={`/companies/${it.symbol}`} className="hover:underline">
                  {it.headline}
                </Link>
              </h3>
              {/* the company under the headline, readable — with its call
                  and score when it is on the board (shared resolver; a
                  name without a call shows nothing, never an invented
                  rating) */}
              {(it.company || it.board) && (
                <div className="mb-1 flex flex-wrap items-center gap-x-2 gap-y-1">
                  {it.company && (
                    <Link
                      href={`/companies/${it.symbol}`}
                      className="text-[11px] font-semibold text-ink hover:underline"
                    >
                      {it.company}
                    </Link>
                  )}
                  {it.board && (
                    <span className="inline-flex items-center gap-1.5">
                      <SmallTierChip tier={it.board.tier} />
                      <span className="num text-[11px] font-bold">
                        {fmt(it.board.score)}
                      </span>
                    </span>
                  )}
                </div>
              )}
              {it.synopsis && it.synopsis !== it.headline && (
                <p className="text-[13px] leading-relaxed text-ink-2">{it.synopsis}</p>
              )}
              <Signals it={it} />
            </div>
          </article>
        ))}
      </main>
    </>
  );
}
