// MOCK — the proposed company workbench, for user review.
// Hierarchy: the call → assessor only when it moves the call → the story.
// Judgment first, evidence beneath, history reachable. Live data only.

import Link from "next/link";
import { notFound } from "next/navigation";
import { getBoard, getStock, heroGap, isMentionSet, Stock } from "@/lib/api";
import { BandStrip, fmt, pct, scored, Sparkline, TierChip } from "@/components/signature/shared";
import Chrome from "@/components/mock/Chrome";
import CallsStack from "@/components/mock/CallsStack";
import { PricePath, ScorePath } from "@/components/mock/Charts";

export async function generateMetadata({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  return { title: `${symbol.toUpperCase()} · company mock` };
}

const TIER_ORDER: Record<string, number> = { "Strong Buy": 0, Buy: 1, Watch: 2 };
const TIER_DOMAIN: [number, number] = [2.9, 5.8];

function assessorMove(s: Stock): { word: "raised" | "restrained"; from: string } | null {
  const a = s.assessment;
  if (!a?.raw_tier || !a.adjusted_tier) return null;
  if (a.raw_tier === a.adjusted_tier) return null; // hold is silence
  const raised = (TIER_ORDER[a.adjusted_tier] ?? 3) < (TIER_ORDER[a.raw_tier] ?? 3);
  return { word: raised ? "raised" : "restrained", from: a.raw_tier };
}

function Chip({ label, value }: { label: string; value: string }) {
  return (
    <span className="rounded border border-hairline px-2 py-0.5 text-[12px]">
      <span className="text-ink-3">{label} </span>
      <b className="num">{value}</b>
    </span>
  );
}

function BarsRow({
  rows, get, label, fmtV,
}: {
  rows: { period_end: string }[];
  get: (r: { period_end: string }) => number | null;
  label: string;
  fmtV: (v: number) => string;
}) {
  const vals = rows.map(get);
  const max = Math.max(...vals.filter((v): v is number => v != null), 0);
  if (max <= 0) return null;
  return (
    <div className="mb-2">
      <div className="flex items-end gap-2">
        {rows.map((r, i) => {
          const v = vals[i];
          return (
            <div key={r.period_end} className="flex w-12 flex-col items-center gap-0.5">
              {v != null ? (
                <>
                  <span className="num text-[9.5px] text-ink-3">{fmtV(v)}</span>
                  <div
                    className="w-7 rounded-t-[3px] bg-ink-2 opacity-75"
                    style={{ height: `${Math.max((v / max) * 56, 2)}px` }}
                    title={`FY${r.period_end.slice(0, 4)}: ${fmtV(v)}`}
                  />
                </>
              ) : (
                <div className="h-[56px]" />
              )}
              <span className="text-[9.5px] text-ink-3">FY{r.period_end.slice(2, 4)}</span>
            </div>
          );
        })}
        <span className="mb-3 ml-1 text-[10px] text-ink-3">{label}</span>
      </div>
    </div>
  );
}

function Dumbbell({
  aLabel, a, bLabel, b,
}: {
  aLabel: string; a: number; bLabel: string; b: number;
}) {
  const Wd = 260;
  const max = Math.max(a, b) * 1.25;
  const x = (v: number) => 6 + (v / max) * (Wd - 58);
  return (
    <svg width={Wd} height={62}>
      {([[aLabel, a, 19, "var(--ink)"], [bLabel, b, 47, "var(--ink-3)"]] as const).map(
        ([label, v, cy, color]) => (
          <g key={label}>
            <line x1={6} x2={x(v)} y1={cy} y2={cy} stroke={color} strokeWidth="2" opacity="0.5" />
            <circle cx={x(v)} cy={cy} r="4.5" fill={color} />
            <text x={x(v) + 8} y={cy + 3.5} fontSize="10.5" fill="var(--ink-2)" className="num">
              {v.toFixed(1)}×
            </text>
            <text x={6} y={cy - 8} fontSize="9.5" fill="var(--ink-3)">{label}</text>
          </g>
        )
      )}
    </svg>
  );
}

export default async function CompanyMock({
  params,
}: {
  params: Promise<{ symbol: string }>;
}) {
  const { symbol: raw } = await params;
  const symbol = raw.toUpperCase();
  const [board, stock] = await Promise.all([
    getBoard(),
    getStock(symbol).catch(() => null),
  ]);
  if (!stock) notFound();

  const names = [...board.board, ...board.off_board].map((e) => ({
    symbol: e.symbol, company: e.company, tier: e.tier,
  }));
  const idx = board.board.findIndex((e) => e.symbol === symbol);
  const prev = idx > 0 ? board.board[idx - 1] : null;
  const next = idx >= 0 && idx < board.board.length - 1 ? board.board[idx + 1] : null;

  const move = assessorMove(stock);
  const f = stock.fundamentals ?? {};
  const lastClose = [...stock.prices].reverse().find((p) => p.close != null)?.close;
  const pts = scored(stock.history);
  const gap = heroGap(stock.valuation_gaps);
  const annuals = [...stock.annual_history].reverse().filter((r) => r.revenue != null);
  const roics = annuals.filter((r) => r.roic != null);
  const alsoAttached = stock.theme_alignments.filter(
    (t) => !stock.valuation_gaps.some((g) => g.theme === t.theme)
  );
  const claimsDesc = [...stock.claims].sort((a, b) =>
    b.call_date.localeCompare(a.call_date)
  );

  const num = (v: unknown): v is number => typeof v === "number";

  return (
    <>
      <Chrome names={names} context={`${symbol} · as of ${stock.as_of}`} />
      <main className="mx-auto max-w-[1280px] px-6 py-6">
        {/* 1 — hero */}
        <div className="mb-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <h1 className="text-[26px] font-bold tracking-tight">{stock.company ?? symbol}</h1>
          <span className="text-[14px] font-bold text-ink-2">{symbol}</span>
          <span className="text-[12.5px] text-ink-3">
            {[stock.sector, stock.industry].filter(Boolean).join(" · ")}
          </span>
          <span className="ml-auto flex items-center gap-2">
            {prev && (
              <Link href={`/companies/${prev.symbol}`} className="rounded-md border border-hairline px-2 py-0.5 text-[12.5px] text-ink-2 hover:border-baseline">
                ← {prev.symbol}
              </Link>
            )}
            {next && (
              <Link href={`/companies/${next.symbol}`} className="rounded-md border border-hairline px-2 py-0.5 text-[12.5px] text-ink-2 hover:border-baseline">
                {next.symbol} →
              </Link>
            )}
          </span>
        </div>
        <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2">
          <TierChip tier={stock.tier} />
          <span className="num text-[24px] font-bold">{fmt(stock.score)}</span>
          <span className="text-[12px] text-ink-3">out of 10</span>
          {stock.final_rank != null && (
            <span className="num text-[12.5px] text-ink-2">rank {stock.final_rank}</span>
          )}
          {move && (
            <span
              className="rounded px-1.5 py-px text-[11px] font-bold"
              style={{
                color: move.word === "raised" ? "var(--up)" : "var(--down)",
                background: `color-mix(in srgb, ${move.word === "raised" ? "var(--up)" : "var(--down)"} 12%, transparent)`,
              }}
            >
              {move.word} from {move.from}
            </span>
          )}
        </div>
        {(num(f.analysts_count) || typeof f.analyst_rating === "string") && (
          <div className="mb-3 text-[12.5px] text-ink-2">
            <span className="kicker mr-2 text-[10px]">Street</span>
            {num(f.analysts_count) && `${f.analysts_count} analysts`}
            {typeof f.analyst_rating === "string" &&
              f.analyst_rating.toLowerCase() !== "none" &&
              ` · ${f.analyst_rating.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}`}
            {num(f.analyst_target_price) &&
              ` · target $${f.analyst_target_price.toFixed(2)}`}
            {lastClose != null && ` vs last $${lastClose.toFixed(2)}`}
          </div>
        )}
        <div className="mb-1">
          <BandStrip
            score={stock.score}
            trail={pts.slice(0, -1).map((p) => p.score)}
            width={720}
            height={44}
            showLabels
            fixedDomain={TIER_DOMAIN}
          />
        </div>
        <p className="mb-8 text-[11.5px] text-ink-3">
          the dot is today; the trail is every reading since {pts[0]?.date ?? "coverage began"}
        </p>

        <div className="grid grid-cols-1 gap-10 xl:grid-cols-[minmax(0,1fr)_300px]">
          <div>
            {/* 2 — evidence triptych */}
            <section className="mb-10 grid grid-cols-1 gap-8 border-t border-hairline pt-5 lg:grid-cols-3">
              <div>
                <div className="kicker">Quality — {fmt(stock.components.quality)}</div>
                <div className="mb-2 text-[11.5px] text-ink-3">is this a durable business?</div>
                <BarsRow rows={annuals} get={(r) => (r as typeof annuals[number]).revenue}
                  label="revenue" fmtV={(v) => `$${(v / 1e9).toFixed(1)}b`} />
                <BarsRow rows={annuals} get={(r) => (r as typeof annuals[number]).op_margin}
                  label="op. margin" fmtV={(v) => `${(v * 100).toFixed(1)}%`} />
                {roics.length > 0 && (
                  <div className="mb-2 flex flex-wrap items-center gap-1 text-[11.5px]">
                    <span className="mr-1 text-ink-3">ROIC</span>
                    {roics.map((r, i) => (
                      <span key={r.period_end} className="num">
                        {((r.roic as number) * 100).toFixed(1)}%
                        {i < roics.length - 1 && <span className="text-ink-3"> → </span>}
                      </span>
                    ))}
                  </div>
                )}
                <div className="flex flex-wrap gap-1.5">
                  {num(f.pe_forward) && <Chip label="PE fwd" value={`${f.pe_forward.toFixed(1)}×`} />}
                  {num(f.peg_ratio) && <Chip label="PEG" value={f.peg_ratio.toFixed(2)} />}
                  {num(f.debt_to_equity) && <Chip label="D/E" value={f.debt_to_equity.toFixed(2)} />}
                  {num(f.price_vs_52w_high) && (
                    <Chip label="vs 52w high" value={pct(f.price_vs_52w_high)} />
                  )}
                </div>
              </div>

              <div>
                <div className="kicker">Value — {fmt(stock.components.value)}</div>
                <div className="mb-2 text-[11.5px] text-ink-3">
                  {gap && isMentionSet(gap)
                    ? "is it cheap against this set?"
                    : "is it cheap against the same story?"}
                </div>
                {gap ? (
                  <>
                    <Dumbbell aLabel={symbol} a={gap.pe_forward!}
                      bLabel={`${gap.peer_count} peers (median)`} b={gap.peer_median_pe!} />
                    {gap.ev_ebitda != null && gap.peer_median_ev != null && (
                      <Dumbbell aLabel={`${symbol} EV/EBITDA`} a={gap.ev_ebitda}
                        bLabel="peer median EV" b={gap.peer_median_ev} />
                    )}
                    <p className="mt-1 text-[11.5px] text-ink-2">
                      {gap.pe_discount != null && gap.pe_discount > 0 ? (
                        <>priced <b>{pct(gap.pe_discount)}</b> below {gap.peer_count} companies in {gap.theme}</>
                      ) : (
                        <>priced above its set in {gap.theme}</>
                      )}
                      {isMentionSet(gap) && (
                        <span className="text-ink-3"> · mention set — companies citing this story, not proven beneficiaries</span>
                      )}
                    </p>
                  </>
                ) : (
                  <p className="text-[12px] italic text-ink-3">no priced peer set yet</p>
                )}
              </div>

              <div>
                <div className="kicker">Narrative gap — {fmt(stock.components.gap)}</div>
                <div className="mb-2 text-[11.5px] text-ink-3">
                  how much of the story is the price ignoring?
                </div>
                {stock.components.exposure != null && stock.priced_in != null ? (
                  <>
                    <svg width={260} height={46}>
                      <text x={5} y={10} fontSize="9.5" fill="var(--ink-3)">
                        story exposure {fmt(stock.components.exposure)}/10
                      </text>
                      <rect x={5} y={16} width={(stock.components.exposure / 10) * 250}
                        height={16} rx="4" fill="var(--ink-3)" opacity="0.35" />
                      <rect
                        x={5 + (stock.components.exposure / 10) * 250 * stock.priced_in}
                        y={16}
                        width={(stock.components.exposure / 10) * 250 * (1 - stock.priced_in)}
                        height={16} rx="4" fill="var(--gap-accent)" />
                    </svg>
                    <p className="text-[11.5px] text-ink-2">
                      the market prices <b>{pct(stock.priced_in)}</b> of its story —
                      the violet rest is what the price ignores
                      {stock.ng_score != null && (
                        <span className="num text-ink-3"> · NG {stock.ng_score.toFixed(2)}</span>
                      )}
                    </p>
                  </>
                ) : (
                  <p className="text-[12px] italic text-ink-3">gap not measured yet</p>
                )}
              </div>
            </section>

            {/* 3 — score components */}
            <section className="mb-10 border-t border-hairline pt-5">
              <div className="kicker mb-3">Score components</div>
              <div className="grid grid-cols-2 gap-6 lg:grid-cols-4">
                {(
                  [
                    ["exposure", "Exposure", "alignment with the stories on the right"],
                    ["value", "Value", "cheapness vs the same story"],
                    ["quality", "Quality", "ROIC, margins, the road above"],
                    ["gap", "Gap", "story not yet in the price"],
                  ] as const
                ).map(([key, label, meaning]) => {
                  const v = stock.components[key];
                  return (
                    <div key={key}>
                      <div className="mb-0.5 flex items-baseline justify-between">
                        <span className="kicker text-[10px]">{label}</span>
                        <span className="num text-[16px] font-bold">{fmt(v)}</span>
                      </div>
                      <div className="mb-1 h-[6px] rounded-full bg-hairline">
                        {v != null && (
                          <div className="h-full rounded-full bg-ink-2"
                            style={{ width: `${Math.min(v * 10, 100)}%` }} />
                        )}
                      </div>
                      <div className="mb-1 text-[10.5px] leading-snug text-ink-3">{meaning}</div>
                      <Sparkline
                        points={stock.history
                          .filter((h) => h.components[key] != null)
                          .map((h) => ({ value: h.components[key] as number }))}
                        width={120} height={26}
                      />
                    </div>
                  );
                })}
              </div>
            </section>

            {/* 4 — the path */}
            <section className="mb-10 border-t border-hairline pt-5">
              <div className="kicker mb-2">The path</div>
              <ScorePath points={pts.map((p) => ({ date: p.date, score: p.score, tier: p.tier }))} />
              <div className="kicker mb-2 mt-5 text-[10px]">Price</div>
              <PricePath
                prices={stock.prices}
                events={stock.filing_events}
                week52High={num(f.week52_high) ? f.week52_high : null}
                week52Low={num(f.week52_low) ? f.week52_low : null}
              />
            </section>

            {/* 5 — thesis (after the instrument, not before) */}
            {stock.assessment?.rationale && (
              <section className="mb-10 border-t border-hairline pt-5">
                <div className="kicker mb-3">Thesis</div>
                <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                  <div>
                    <div className="kicker mb-1 text-[10px]" style={{ color: "var(--up)" }}>Bull</div>
                    <p className="text-[13px] leading-relaxed text-ink-2">{stock.assessment.key_bull}</p>
                  </div>
                  <div>
                    <div className="kicker mb-1 text-[10px]" style={{ color: "var(--down)" }}>Bear</div>
                    <p className="text-[13px] leading-relaxed text-ink-2">{stock.assessment.key_bear}</p>
                  </div>
                  <div>
                    <div className="kicker mb-1 text-[10px]">Rationale</div>
                    <p className="text-[13px] leading-relaxed text-ink-2">{stock.assessment.rationale}</p>
                  </div>
                </div>
              </section>
            )}

            {/* 6 — calls */}
            <section className="mb-10 border-t border-hairline pt-5">
              <div className="kicker mb-3">Calls</div>
              <CallsStack
                events={stock.filing_events}
                calls={stock.earnings_calls}
                filings={stock.filings}
                claims={stock.claims}
              />
            </section>
          </div>

          {/* 7 — right rail */}
          <aside className="text-[13px]">
            <div className="kicker mb-1.5">Stories</div>
            <div className="mb-7">
              {stock.valuation_gaps.length === 0 && (
                <p className="text-[12px] italic text-ink-3">no stories priced yet</p>
              )}
              {[...stock.valuation_gaps]
                .sort((a, b) => (b.alignment ?? 0) - (a.alignment ?? 0))
                .map((g) => (
                  <div key={g.theme} className="border-b border-hairline py-2 last:border-b-0">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="min-w-0 text-[12.5px] font-semibold leading-snug">{g.theme}</span>
                      <span className="num shrink-0 text-[11px] text-ink-3">
                        {g.alignment?.toFixed(2)} · n={g.peer_count}
                      </span>
                    </div>
                    {isMentionSet(g) && (
                      <div className="text-[10.5px] text-ink-3">mention set</div>
                    )}
                    {g.pe_forward != null && g.peer_median_pe != null && (
                      <div className="num text-[11.5px] text-ink-2">
                        pe {g.pe_forward.toFixed(2)} — peer {g.peer_median_pe.toFixed(2)}
                        {g.pe_discount != null && (
                          <span className="float-right">{pct(g.pe_discount)}</span>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              {alsoAttached.length > 0 && (
                <>
                  <div className="kicker mb-1 mt-3 text-[10px]">Also attached</div>
                  {alsoAttached.map((t) => (
                    <div key={t.theme} className="border-b border-hairline py-1.5 text-[12px] text-ink-2 last:border-b-0">
                      {t.theme}
                      <span className="num float-right text-[11px] text-ink-3">
                        {t.alignment?.toFixed(2)}{t.trajectory ? ` · ${t.trajectory}` : ""}
                      </span>
                    </div>
                  ))}
                </>
              )}
            </div>

            <div className="kicker mb-1.5">Said</div>
            <div className="mb-7">
              {claimsDesc.slice(0, 12).map((c, i) => (
                <div key={i} className="border-b border-hairline py-2 last:border-b-0">
                  <div className="flex items-baseline gap-2 text-[11px] text-ink-3">
                    <span className="num">{c.call_date.slice(0, 10)}</span>
                    <span>{c.type.replace(/_/g, " ")}</span>
                    {c.direction && (
                      <span
                        className="ml-auto font-bold uppercase"
                        style={{
                          color:
                            c.direction.toLowerCase() === "up"
                              ? "var(--up)"
                              : c.direction.toLowerCase() === "down"
                                ? "var(--down)"
                                : "var(--ink-3)",
                        }}
                      >
                        {c.direction}
                      </span>
                    )}
                  </div>
                  <div className="line-clamp-2 text-[12px] leading-snug text-ink-2">{c.text}</div>
                </div>
              ))}
            </div>

            <div className="kicker mb-1.5">Inside</div>
            <div>
              {stock.insider_trades.length === 0 && (
                <p className="text-[12px] italic text-ink-3">no insider decisions on record</p>
              )}
              {stock.insider_trades.slice(0, 10).map((t, i) => (
                <div key={i} className="flex items-baseline gap-2 border-b border-hairline py-1.5 text-[12px] last:border-b-0">
                  <span className="num shrink-0 text-[11px] text-ink-3">{t.date.slice(0, 10)}</span>
                  <span className="min-w-0 flex-1 truncate text-ink-2">{t.person}</span>
                  <span
                    className="shrink-0 font-bold"
                    style={{ color: t.type === "BUY" ? "var(--up)" : "var(--down)" }}
                  >
                    {t.type}
                  </span>
                  {t.total_value != null && (
                    <span className="num shrink-0 text-ink-2">
                      ${(t.total_value / 1e6).toFixed(1)}m
                    </span>
                  )}
                </div>
              ))}
            </div>
          </aside>
        </div>
      </main>
    </>
  );
}
