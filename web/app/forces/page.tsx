// MOCK — Forces: a directory, not a lecture. Every force opens its
// roster; emerging and ledger-derived weakening on the rail.

import Link from "next/link";
import { getBoard, getNarrativesLanding } from "@/lib/api";
import Chrome from "@/components/mock/Chrome";

export const metadata = { title: "Forces" };

export default async function ForcesMock() {
  const [board, landing] = await Promise.all([getBoard(), getNarrativesLanding()]);
  const names = [...board.board, ...board.off_board].map((e) => ({
    symbol: e.symbol, company: e.company, tier: e.tier,
  }));

  return (
    <>
      <Chrome names={names} active="Forces" context={`as of ${board.date}`} />
      <main className="mx-auto max-w-[1280px] px-6 py-8">
        <div className="grid grid-cols-1 gap-10 xl:grid-cols-[minmax(0,1fr)_400px]">
          <div>
            <div className="kicker">Directory</div>
            <h1 className="mb-4 border-b-2 border-ink pb-3 text-[28px] font-bold tracking-tight">
              Forces
            </h1>
            <div className="grid grid-cols-[minmax(0,1fr)_auto_auto_auto] items-baseline gap-x-6 border-b border-hairline pb-1.5">
              {["Force", "wt", "board", "covered"].map((h) => (
                <span key={h} className="kicker text-[10px]">{h}</span>
              ))}
            </div>
            {landing.forces.map((f) => (
              <Link
                key={f.id}
                href={`/forces/${f.id}`}
                className="grid grid-cols-[minmax(0,1fr)_auto_auto_auto] items-baseline gap-x-6 border-b border-hairline py-3 hover:bg-surface"
              >
                <span className="min-w-0">
                  <span className="block text-[15px] font-bold leading-snug hover:underline">
                    {f.name}
                  </span>
                  {f.thesis && (
                    <span className="line-clamp-2 text-[12.5px] leading-snug text-ink-2">
                      {f.thesis}
                    </span>
                  )}
                </span>
                <span className="num text-[14px] font-bold">{f.board_weight.toFixed(0)}</span>
                <span className="num text-[13px] text-ink-2">{f.board_companies}</span>
                <span className="num text-[13px] text-ink-3">{f.companies}</span>
              </Link>
            ))}
            <p className="mt-3 text-[11.5px] text-ink-3">
              wt = exposed board weight · board = names on the board carrying
              it · covered = every company with signed exposure
            </p>
          </div>

          <aside>
            <div className="kicker mb-2 border-b border-ink pb-1">Emerging</div>
            <div className="mb-8">
              {landing.emerging.map((e) => (
                <div key={e.id} className="border-b border-hairline py-2.5 last:border-b-0">
                  <div className="text-[13.5px] font-bold leading-snug">{e.name}</div>
                  <div className="num text-[11.5px] text-ink-3">
                    {e.parent && <>{e.parent} · </>}
                    {e.age_days != null && <>{e.age_days}d · </>}
                    {e.companies} companies
                  </div>
                </div>
              ))}
            </div>

            <div className="kicker mb-2 border-b border-ink pb-1">Losing support</div>
            <div>
              {landing.weakening.filter((w) => w.net_30d < 0).length === 0 && (
                <p className="py-2 text-[12px] italic text-ink-3">nothing on net right now</p>
              )}
              {landing.weakening
                .filter((w) => w.net_30d < 0)
                .map((w) => (
                  <div key={w.id} className="flex items-baseline justify-between gap-3 border-b border-hairline py-2.5 last:border-b-0">
                    <span className="min-w-0 text-[13.5px] font-bold leading-snug">{w.name}</span>
                    <span className="num shrink-0 text-[12px] text-ink-3">
                      {w.companies} companies ·{" "}
                      <b style={{ color: "var(--down)" }}>{w.net_30d}</b>
                      {w.misses > 0 && (
                        <> · <b style={{ color: "var(--down)" }}>{w.misses} missed</b></>
                      )}
                    </span>
                  </div>
                ))}
            </div>
          </aside>
        </div>
      </main>
    </>
  );
}
