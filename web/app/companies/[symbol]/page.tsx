// MOCK — the proposed company workbench, for user review.
// Hierarchy: the call → assessor only when it moves the call → the story.
// Judgment first, evidence beneath, history reachable. Live data only.

import Link from "next/link";
import { notFound } from "next/navigation";
import { getBoard, getStock, heroGap, isMentionSet } from "@/lib/api";
import { BandStrip, fmt, pct, scored, Sparkline, TierChip } from "@/components/signature/shared";
import Chrome from "@/components/mock/Chrome";
import CallsStack from "@/components/mock/CallsStack";
import { PricePath, ScorePath } from "@/components/mock/Charts";

export async function generateMetadata({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  return { title: `${symbol.toUpperCase()} · company mock` };
}

const TIER_DOMAIN: [number, number] = [2.9, 5.8];

// NO assessor badge on the hero: raised / restrained / promoted stay dark
// until assessed_tier carries provenance (addendum #5, V3 #11) — the
// corridor also writes assessed_tier, and painting a corridor state as
// judge conviction is the exact mislabel the gate blocks.

function Chip({ label, value }: { label: string; value: string }) {
  return (
    <span className="rounded border border-hairline px-2 py-0.5 text-[12px]">
      <span className="text-ink-3">{label} </span>
      <b className="num">{value}</b>
    </span>
  );
}

// Quality is durability — ROIC, operating margin, FCF margin — never size
// (addendum #1: revenue can be flat while every durability metric halves,
// so a revenue histogram cannot explain a quality move; amended by user
// 2026-08-15: each metric gets a ROAD — up to five fiscal years of bars,
// with TTM as the sixth). One SVG so the three metric rows share one year
// axis; each row scales to its own range. FY labels come from period_end
// (a Sep year-end is one FY, never a second calendar year); the TTM bar
// is drawn in full ink so "now" reads apart from the fiscal history.
// Null values omit the bar — the slot stays, nothing is padded.
function DurabilityRoad({
  columns,
  metrics,
}: {
  columns: string[]; // e.g. ["FY21", ..., "FY25", "TTM"]
  metrics: { label: string; values: (number | null)[] }[];
}) {
  const shown = metrics.filter((m) => m.values.some((v) => v != null));
  if (shown.length === 0 || columns.length === 0) return null;
  const SLOT = 46;
  const BARW = 20;
  const LABEL = 13; // metric label line
  const VAL = 10;   // value text above the tallest bar
  const AREA = 32;  // tallest bar
  const ROWGAP = 9;
  const AXIS = 12;  // year labels, drawn once
  const W = columns.length * SLOT;
  const rowH = LABEL + VAL + AREA + ROWGAP;
  const H = shown.length * rowH + AXIS;
  const cx = (i: number) => i * SLOT + SLOT / 2;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="mb-2 w-full max-w-[330px]"
      role="img"
      aria-label="durability: fiscal-year history and trailing twelve months"
    >
      {shown.map((m, mi) => {
        const top = mi * rowH;
        const nums = m.values.filter((v): v is number => v != null);
        const pos = Math.max(0, ...nums.map((v) => (v > 0 ? v : 0)));
        const neg = Math.max(0, ...nums.map((v) => (v < 0 ? -v : 0)));
        const scale = AREA / (pos + neg || 1);
        const base = top + LABEL + VAL + pos * scale;
        return (
          <g key={m.label}>
            <text x={0} y={top + 9} fontSize="10" fill="var(--ink-3)">
              {m.label}
            </text>
            <line
              x1={0} x2={W} y1={base} y2={base}
              stroke="var(--hairline)" strokeWidth="1"
            />
            {m.values.map((v, i) => {
              if (v == null) return null;
              const h = Math.max(Math.abs(v) * scale, 1.5);
              const up = v >= 0;
              const isTtm = columns[i] === "TTM";
              return (
                <g key={i}>
                  <rect
                    x={cx(i) - BARW / 2}
                    y={up ? base - h : base}
                    width={BARW}
                    height={h}
                    rx="1.5"
                    fill={isTtm ? "var(--ink)" : "var(--ink-2)"}
                    opacity={isTtm ? 1 : 0.55}
                  />
                  <text
                    x={cx(i)}
                    y={up ? base - h - 3 : base + h + 9}
                    fontSize="8.5"
                    textAnchor="middle"
                    fill={up ? "var(--ink-2)" : "var(--down)"}
                    className="num"
                  >
                    {(v * 100).toFixed(1)}%
                  </text>
                </g>
              );
            })}
          </g>
        );
      })}
      {columns.map((c, i) => (
        <text
          key={c + i}
          x={cx(i)}
          y={H - 2}
          fontSize="9"
          textAnchor="middle"
          fill="var(--ink-3)"
          fontWeight={c === "TTM" ? 700 : 400}
          className="num"
        >
          {c}
        </text>
      ))}
    </svg>
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

  const f = stock.fundamentals ?? {};
  const lastClose = [...stock.prices].reverse().find((p) => p.close != null)?.close;
  const pts = scored(stock.history);
  const gap = heroGap(stock.valuation_gaps);
  // The durability road: the last five fiscal years with any quality
  // field (rows arrive newest first), oldest → newest, then TTM as the
  // sixth column. FY FCF margin is fcf / revenue from the same row.
  const fys = stock.annual_history
    .filter((r) => r.roic != null || r.op_margin != null || r.fcf != null)
    .slice(0, 5)
    .reverse();
  const roadCols = [...fys.map((r) => `FY${r.period_end.slice(2, 4)}`), "TTM"];
  // The rail's Forces block comes from narrative_exposures (keyed by
  // narrative_id). Company-scope narratives are this company's OWN story,
  // not a market-wide force, so they are listed apart. The legacy
  // meta-themes alignments are no longer shown here at all: they are a
  // second, frozen vocabulary for the same idea (retiring at the
  // NARRATIVE_SPEC Phase 2 gate), and two names for one thing on one rail
  // is how a reader is taught something untrue.
  const forces = stock.exposures.filter((e) => e.scope !== "company");
  const companyStories = stock.exposures.filter((e) => e.scope === "company");
  const num = (v: unknown): v is number => typeof v === "number";

  return (
    <>
      <Chrome names={names} context={`${symbol} · as of ${stock.as_of}`} />
      <main className="mx-auto max-w-[1280px] px-6 py-6">
        {/* 1 — hero. Prev/next stepping is its own labeled control ABOVE
            the name, never part of the phrase that carries this name's
            call and score (addendum #8: "GDDY → Strong Buy 5.2" read as
            one statement). */}
        {(prev || next) && (
          <div className="mb-1 flex items-center justify-end gap-2">
            <span className="kicker text-[9.5px]">board neighbours</span>
            {prev && (
              <Link href={`/companies/${prev.symbol}`} className="rounded-md border border-hairline px-2 py-0.5 text-[12px] text-ink-2 hover:border-baseline">
                ← {prev.symbol}
              </Link>
            )}
            {next && (
              <Link href={`/companies/${next.symbol}`} className="rounded-md border border-hairline px-2 py-0.5 text-[12px] text-ink-2 hover:border-baseline">
                {next.symbol} →
              </Link>
            )}
          </div>
        )}
        <div className="mb-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <h1 className="text-[26px] font-bold tracking-tight">{stock.company ?? symbol}</h1>
          <span className="text-[14px] font-bold text-ink-2">{symbol}</span>
          <span className="text-[12.5px] text-ink-3">
            {[stock.sector, stock.industry].filter(Boolean).join(" · ")}
          </span>
        </div>
        <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2">
          <TierChip tier={stock.tier} />
          <span className="num text-[24px] font-bold">{fmt(stock.score)}</span>
          <span className="text-[12px] text-ink-3">out of 10</span>
          {stock.final_rank != null && (
            <span className="num text-[12.5px] text-ink-2">rank {stock.final_rank}</span>
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
                <div className="mb-2 text-[11.5px] text-ink-3">
                  durability: five fiscal years, then the last twelve months
                </div>
                <DurabilityRoad
                  columns={roadCols}
                  metrics={[
                    {
                      label: "ROIC",
                      values: [
                        ...fys.map((r) => r.roic),
                        num(f.roic) ? f.roic : null,
                      ],
                    },
                    {
                      label: "op. margin",
                      values: [
                        ...fys.map((r) => r.op_margin),
                        num(f.operating_margin) ? f.operating_margin : null,
                      ],
                    },
                    {
                      label: "FCF margin",
                      values: [
                        ...fys.map((r) =>
                          r.fcf != null && r.revenue != null && r.revenue !== 0
                            ? r.fcf / r.revenue
                            : null
                        ),
                        num(f.fcf_margin) ? f.fcf_margin : null,
                      ],
                    },
                  ]}
                />
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
                  is it cheap against this set?
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
                    {/* one gap word per pane (addendum #8): priced_in here,
                        the 10-pt Gap on its component bar — never a third
                        figure for the same idea */}
                    <p className="text-[11.5px] text-ink-2">
                      the market prices <b>{pct(stock.priced_in)}</b> of its story —
                      the violet rest is what the price ignores
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
                    ["exposure", "Exposure", "alignment with the forces on the right"],
                    ["value", "Value", "cheapness vs its peer set"],
                    ["quality", "Quality", "ROIC, margins, the durability above"],
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
            {/* The forces this company carries, from the narrative brain's
                own link table (keyed by narrative_id — never name-matched).
                Direction is printed: a threatened link must not read like a
                tailwind. */}
            <div className="kicker mb-1.5">Forces</div>
            <div className="mb-7">
              {forces.length === 0 && (
                <p className="text-[12px] italic text-ink-3">
                  no force is attached to this company yet
                </p>
              )}
              {forces.map((e) => (
                <Link
                  key={e.narrative_id}
                  href={`/forces/${e.narrative_id}`}
                  className="block border-b border-hairline py-2 last:border-b-0 hover:bg-surface"
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="min-w-0 text-[12.5px] font-semibold leading-snug">
                      {e.name}
                    </span>
                    <span className="num shrink-0 text-[11px] text-ink-3">
                      {e.exposure?.toFixed(2)}
                    </span>
                  </div>
                  <div className="text-[10.5px] text-ink-3">
                    {e.direction === "threatened" ? (
                      <span style={{ color: "var(--down)" }}>exposed to the downside</span>
                    ) : e.direction === "adapting" ? (
                      "adapting to it"
                    ) : (
                      "stands to gain"
                    )}
                    {e.linkage === "secondary" && " · second-order"}
                    {e.parent && ` · under ${e.parent.name}`}
                  </div>
                </Link>
              ))}
              {companyStories.length > 0 && (
                <>
                  <div className="kicker mb-1 mt-3 text-[10px]">Its own story</div>
                  {companyStories.map((e) => (
                    <div
                      key={e.narrative_id}
                      className="border-b border-hairline py-1.5 text-[12px] text-ink-2 last:border-b-0"
                    >
                      {e.name}
                    </div>
                  ))}
                </>
              )}
            </div>

            <div className="kicker mb-1.5">Priced against</div>
            <p className="mb-1.5 text-[11px] leading-snug text-ink-3">
              the peer sets behind the value reading
            </p>
            <div className="mb-7">
              {stock.valuation_gaps.length === 0 && (
                <p className="text-[12px] italic text-ink-3">no priced peer set yet</p>
              )}
              {[...stock.valuation_gaps]
                .sort((a, b) => (b.alignment ?? 0) - (a.alignment ?? 0))
                .map((g) => (
                  <div key={g.theme} className="border-b border-hairline py-2 last:border-b-0">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="min-w-0 text-[12.5px] font-semibold leading-snug">
                        {g.narrative_id != null ? (
                          <Link href={`/forces/${g.narrative_id}`} className="hover:underline">
                            {g.theme}
                          </Link>
                        ) : (
                          g.theme
                        )}
                      </span>
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
            </div>

            {/* Claims appear ONCE, inside the calls stack against their
                call date (addendum #8) — the Said rail duplicated the
                same quotes and is gone. */}
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
