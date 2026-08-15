// MOCK — one force, opened: thesis, the on-board roster, and the
// attached-but-off-board tail (what this force may surface next).

import Link from "next/link";
import { notFound } from "next/navigation";
import { getBoard, getForceRoster } from "@/lib/api";
import Chrome from "@/components/mock/Chrome";
import { fmt, TierChip } from "@/components/signature/shared";

export default async function ForceMock({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [board, roster] = await Promise.all([
    getBoard(),
    getForceRoster(id).catch(() => null),
  ]);
  if (!roster) notFound();
  const names = [...board.board, ...board.off_board].map((e) => ({
    symbol: e.symbol, company: e.company, tier: e.tier,
  }));

  return (
    <>
      <Chrome names={names} active="Forces" context={`as of ${board.date}`} />
      <main className="mx-auto max-w-[900px] px-6 py-8">
        <div className="kicker">
          <Link href="/forces" className="hover:underline">Forces</Link> · {roster.level}
        </div>
        <h1 className="mb-1 text-[28px] font-bold tracking-tight">{roster.name}</h1>
        <div className="num mb-3 text-[13px] text-ink-2">
          {roster.on_board.length} on the board · {roster.covered} covered
        </div>
        {roster.thesis && (
          <p className="mb-8 max-w-[76ch] text-[14px] leading-relaxed text-ink-2">
            {roster.thesis}
          </p>
        )}

        <section className="mb-9">
          <div className="kicker mb-2 border-b border-ink pb-1">On the board</div>
          {roster.on_board.length === 0 && (
            <p className="py-2 text-[13px] italic text-ink-3">
              no board name carries this force yet
            </p>
          )}
          {roster.on_board.map((r) => (
            <Link
              key={r.symbol}
              href={`/companies/${r.symbol}`}
              className="grid grid-cols-[minmax(0,1fr)_auto_auto_auto] items-center gap-x-6 border-b border-hairline py-2.5 hover:bg-surface"
            >
              <span className="min-w-0 truncate">
                <span className="font-bold">{r.symbol}</span>{" "}
                <span className="text-[12.5px] text-ink-2">{r.company}</span>
              </span>
              <span className="num text-[12px] text-ink-3">
                exposure {r.exposure?.toFixed(2) ?? "—"}
              </span>
              <TierChip tier={r.tier} />
              <span className="num justify-self-end text-[15px] font-bold">{fmt(r.score)}</span>
            </Link>
          ))}
        </section>

        <section>
          <div className="kicker mb-1 border-b border-ink pb-1">Attached, not on the board</div>
          <p className="mb-2 text-[12.5px] text-ink-3">
            The {roster.off_board_total} covered names carrying this story
            without a call today — ranked by how much of their story it is.
            This is where the force surfaces its next candidates.
          </p>
          {roster.off_board.map((r) => (
            <Link
              key={r.symbol}
              href={`/companies/${r.symbol}`}
              className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-baseline gap-x-6 border-b border-hairline py-2 hover:bg-surface"
            >
              <span className="min-w-0 truncate">
                <span className="font-bold">{r.symbol}</span>{" "}
                <span className="text-[12.5px] text-ink-2">{r.company}</span>
              </span>
              <span className="num text-[12px] text-ink-3">
                exposure {r.exposure?.toFixed(2) ?? "—"}
              </span>
              <span className="num justify-self-end text-[13px] text-ink-2">{fmt(r.score)}</span>
            </Link>
          ))}
          {roster.off_board_total > roster.off_board.length && (
            <p className="mt-2 text-[11.5px] text-ink-3">
              …and {roster.off_board_total - roster.off_board.length} more with
              thinner exposure, all scored through the same lens
            </p>
          )}
        </section>
      </main>
    </>
  );
}
