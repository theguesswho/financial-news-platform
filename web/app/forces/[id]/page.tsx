// MOCK — one force, opened: thesis, the weekly pulse, the on-board roster,
// and the attached-but-off-board tail (what this force may surface next).
// Everything here is keyed by narrative_id from GET /narratives/{id};
// nothing is paired to a company by matching names.

import Link from "next/link";
import { notFound } from "next/navigation";
import { getBoard, getNarrative } from "@/lib/api";
import Chrome from "@/components/mock/Chrome";
import Pulse from "@/components/mock/Pulse";
import { fmt, TierChip } from "@/components/signature/shared";

// Which way the force cuts for this company. "Beneficiary" is the default
// reading of a roster and stays silent; a headwind never does.
function Facing({ direction }: { direction: string | null }) {
  if (direction === "threatened")
    return (
      <span className="ml-1.5 not-italic" style={{ color: "var(--down)" }}>
        headwind
      </span>
    );
  if (direction === "adapting")
    return <span className="ml-1.5 text-ink-3">adapting</span>;
  return null;
}

export default async function ForceMock({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [board, force] = await Promise.all([
    getBoard(),
    getNarrative(id).catch(() => null),
  ]);
  if (!force) notFound();
  const roster = force.roster;
  // A force whose links mostly point the other way is a RISK, and its
  // attached names are exposed to it, not surfaced by it.
  const links = [...roster.on_board, ...roster.off_board];
  const isRisk =
    links.length > 0 &&
    links.filter((r) => r.direction === "threatened").length > links.length / 2;
  const names = [...board.board, ...board.off_board].map((e) => ({
    symbol: e.symbol, company: e.company, tier: e.tier,
  }));

  return (
    <>
      <Chrome names={names} active="Forces" context={`as of ${board.date}`} />
      <main className="mx-auto max-w-[900px] px-6 py-8">
        <div className="kicker">
          <Link href="/forces" className="hover:underline">Forces</Link> · {force.level}
          {force.parent && (
            <>
              {" · under "}
              <Link href={`/forces/${force.parent.id}`} className="hover:underline">
                {force.parent.name}
              </Link>
            </>
          )}
        </div>
        <h1 className="mb-1 text-[28px] font-bold tracking-tight">{force.name}</h1>
        <div className="num mb-3 text-[13px] text-ink-2">
          {roster.on_board.length} on the board · {roster.covered} covered
          {force.status !== "active" && (
            <span className="ml-2 text-ink-3">· {force.status}</span>
          )}
        </div>
        {force.thesis && (
          <p className="mb-4 max-w-[76ch] text-[14px] leading-relaxed text-ink-2">
            {force.thesis}
          </p>
        )}
        {force.falsification && (
          <p className="mb-8 max-w-[76ch] border-l-2 border-hairline pl-3 text-[12.5px] leading-relaxed text-ink-3">
            <span className="kicker mr-1 text-[9.5px]">What would break it</span>
            {force.falsification}
          </p>
        )}

        <section className="mb-9">
          <div className="kicker mb-2 border-b border-ink pb-1">The pulse</div>
          <Pulse weeks={force.health.weeks} />
          {force.health.observed_weeks > 0 && force.health.observed_weeks < 4 && (
            <p className="mt-1 text-[11.5px] text-ink-3">
              {`Only ${force.health.observed_weeks} week${
                force.health.observed_weeks === 1 ? "" : "s"
              } of live observation so far — too short to read as a trend.`}
            </p>
          )}
        </section>

        {force.children.length > 0 && (
          <section className="mb-9">
            <div className="kicker mb-2 border-b border-ink pb-1">Inside this force</div>
            {force.children.map((c) => (
              <Link
                key={c.id}
                href={`/forces/${c.id}`}
                className="flex items-baseline justify-between gap-4 border-b border-hairline py-2 last:border-b-0 hover:bg-surface"
              >
                <span className="min-w-0 truncate text-[13px] font-semibold">{c.name}</span>
                <span className="num shrink-0 text-[12px] text-ink-3">
                  {c.on_board} on the board · {c.covered} covered
                </span>
              </Link>
            ))}
          </section>
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
                <Facing direction={r.direction} />
              </span>
              <TierChip tier={r.tier} />
              <span className="num justify-self-end text-[15px] font-bold">{fmt(r.score)}</span>
            </Link>
          ))}
        </section>

        <section>
          <div className="kicker mb-1 border-b border-ink pb-1">Attached, not on the board</div>
          <p className="mb-2 text-[12.5px] text-ink-3">
            {isRisk ? (
              <>
                The {roster.off_board_total} covered names this force cuts
                against without a call today — ranked by how exposed they are.
                Exposure to a headwind is not a candidate list.
              </>
            ) : (
              <>
                The {roster.off_board_total} covered names carrying this story
                without a call today — ranked by how much of their story it is.
                This is where the force surfaces its next candidates.
              </>
            )}
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
                <Facing direction={r.direction} />
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
