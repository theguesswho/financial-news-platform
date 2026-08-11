// The front door — the narrative lens (DESIGN_BRIEF.md, revised
// 2026-08-10). What the system IS: forces / emerging / weakness from the
// ledger / the bridge to the Board.

import Link from "next/link";
import { getBoard, getNarrativesLanding } from "@/lib/api";
import { fmt, TierChip } from "@/components/signature/shared";

export const metadata = { title: "Narratives" };

function MomentumWord({ momentum }: { momentum: string }) {
  // Momentum role (orange) enters use here — never tiers, never deltas.
  if (momentum === "accelerating")
    return (
      <span className="text-[11.5px] font-bold" style={{ color: "var(--momentum)" }}>
        accelerating
      </span>
    );
  return <span className="text-[11.5px] text-ink-3">{momentum}</span>;
}

export default async function NarrativesLandingPage() {
  const [landing, board] = await Promise.all([getNarrativesLanding(), getBoard()]);
  const bridge = board.board.slice(0, 6);

  return (
    <main className="mx-auto max-w-[1100px] px-6 py-10">
      <div className="kicker">the narrative lens · as of {board.date}</div>
      <h1 className="mb-1 text-[28px] font-bold tracking-tight">
        The forces the instrument believes in
      </h1>
      <p className="mb-8 max-w-[72ch] text-[14px] text-ink-2">
        This instrument reads SEC filings, earnings calls, and market data,
        and synthesises them into narratives — the stories actually moving
        businesses. Below: the forces it currently believes in, the ones it
        is starting to see, and the ones losing support. Each force leads to
        the stocks it surfaces.
      </p>

      {/* 1 — the forces */}
      <section className="mb-10">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {landing.forces.map((f) => (
            <div key={f.id} className="rounded-xl border border-hairline bg-surface p-5">
              <div className="mb-1 flex items-baseline justify-between gap-3">
                <span className="text-[16px] font-bold leading-snug">{f.name}</span>
                <MomentumWord momentum={f.momentum} />
              </div>
              {f.thesis && (
                <p className="mb-2 line-clamp-3 text-[13px] leading-relaxed text-ink-2">
                  {f.thesis}
                </p>
              )}
              <div className="num mb-2 text-[12px] text-ink-3">
                {f.companies} companies carry it · {f.board_companies} on the
                board · board conviction {f.board_weight.toFixed(1)}
              </div>
              {f.top_stocks.length > 0 && (
                <div className="flex flex-wrap items-center gap-2">
                  {f.top_stocks.map((s) => (
                    <Link
                      key={s.symbol}
                      href={`/signature?symbol=${s.symbol}`}
                      className="num rounded-md border border-hairline px-1.5 py-0.5 text-[12px] font-semibold hover:border-baseline"
                    >
                      {s.symbol} {fmt(s.score)}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* 2 — emerging */}
      <section className="mb-10">
        <div className="kicker mb-1">Starting to see</div>
        <p className="mb-3 max-w-[72ch] text-[13px] text-ink-3">
          Narratives the instrument is forming right now — named, young, and
          accumulating companies. Discovery happening live.
        </p>
        <div className="overflow-hidden rounded-xl border border-hairline bg-surface">
          {landing.emerging.map((e) => (
            <div
              key={e.id}
              className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b border-hairline px-4 py-2.5 last:border-b-0"
            >
              <span className="min-w-0 flex-1 text-[13.5px] font-semibold">
                {e.name}
                {e.parent && (
                  <span className="ml-2 text-[11.5px] font-normal text-ink-3">
                    under {e.parent}
                  </span>
                )}
              </span>
              <span className="num text-[12px] text-ink-2">
                {e.age_days != null ? `${e.age_days} days old` : "age unknown"} ·{" "}
                {e.companies} companies · {e.adds_30d} additions in 30 days
              </span>
              <span className="rounded border border-hairline px-1.5 py-px text-[10.5px] font-semibold uppercase tracking-[0.06em] text-ink-3">
                {e.maturity}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* 3 — shifts and weakness (equal weight, from the ledger) */}
      <section className="mb-10">
        <div className="kicker mb-1">Losing support</div>
        <p className="mb-3 max-w-[72ch] text-[13px] text-ink-3">
          Where the evidence ledger has turned against a story — removals and
          weakenings outrunning support, or calls the narrative got wrong.
          Shown with the same prominence as the winners; that is the point.
        </p>
        <div className="overflow-hidden rounded-xl border border-hairline bg-surface">
          {landing.weakening.length === 0 && (
            <p className="px-4 py-3 text-[13px] italic text-ink-3">
              No narrative is currently losing support on net.
            </p>
          )}
          {landing.weakening.map((w) => (
            <div
              key={w.id}
              className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b border-hairline px-4 py-2.5 last:border-b-0"
            >
              <span className="min-w-0 flex-1 text-[13.5px] font-semibold">
                {w.name}
                {w.status === "declining" && (
                  <span className="ml-2 text-[11.5px] font-normal italic text-ink-3">
                    declining
                  </span>
                )}
              </span>
              <span className="num text-[12px] text-ink-2">
                removed from {w.removed_30d}, weakened in {w.weakened_30d},
                supported in {w.strengthened_30d} —{" "}
                <b style={{ color: w.net_30d < 0 ? "var(--down)" : undefined }}>
                  net {w.net_30d >= 0 ? `+${w.net_30d}` : w.net_30d}
                </b>{" "}
                in 30 days
                {w.misses > 0 && (
                  <>
                    {" "}· <b style={{ color: "var(--down)" }}>{w.misses} missed{" "}
                    {w.misses === 1 ? "call" : "calls"}</b>
                  </>
                )}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* 4 — the bridge to the Board */}
      <section className="mb-8">
        <div className="kicker mb-1">What these forces surface</div>
        <p className="mb-3 max-w-[72ch] text-[13px] text-ink-3">
          The top of the Board — every stock scored through the same lens,
          ranked by conviction.
        </p>
        <div className="overflow-hidden rounded-xl border border-hairline bg-surface">
          {bridge.map((e) => (
            <Link
              key={e.symbol}
              href="/board"
              className="grid grid-cols-[1.6rem_minmax(0,1fr)_auto_auto] items-center gap-x-4 border-b border-hairline px-4 py-2.5 last:border-b-0 hover:bg-page"
            >
              <span className="num text-[13px] text-ink-3">{e.rank}</span>
              <span className="min-w-0 truncate">
                <span className="font-bold">{e.symbol}</span>{" "}
                <span className="text-[12px] text-ink-2">{e.company}</span>
              </span>
              <TierChip tier={e.tier} />
              <span className="num justify-self-end text-[15px] font-bold">
                {fmt(e.score)}
              </span>
            </Link>
          ))}
        </div>
        <div className="mt-3">
          <Link
            href="/board"
            className="text-[13px] font-semibold underline decoration-hairline underline-offset-4 hover:decoration-ink"
          >
            the full Board — all {board.counts.strong_buy + board.counts.buy + board.counts.watch} rated stocks →
          </Link>
        </div>
      </section>
    </main>
  );
}
