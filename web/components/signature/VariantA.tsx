"use client";

// Variant A — "The instrument chart". FASTgraphs-esque: one time chart of
// the composite score travelling through the tier bands, components as a
// quiet evidence row beneath.

import { useMemo, useRef, useState } from "react";
import { BANDS, Stock } from "@/lib/api";
import { componentSeries, fmt, pct, scored, scoreDomain, Sparkline, TierChip } from "./shared";

const W = 940;
const H = 300;
const PAD = { l: 30, r: 118, t: 10, b: 22 };

export default function VariantA({ stock }: { stock: Stock }) {
  const pts = useMemo(() => scored(stock.history), [stock]);
  const [hover, setHover] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const [lo, hi] = scoreDomain(pts.map((p) => p.score));
  const x = (i: number) =>
    PAD.l + (i / Math.max(pts.length - 1, 1)) * (W - PAD.l - PAD.r);
  const y = (v: number) =>
    PAD.t + (1 - (v - lo) / (hi - lo)) * (H - PAD.t - PAD.b);

  const line = pts
    .map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.score).toFixed(1)}`)
    .join("");
  const last = pts[pts.length - 1];

  const zones: [number, number, string, string][] = [
    [BANDS.STRONG_BUY, hi, "var(--tier-sb)", `Strong Buy above ${BANDS.STRONG_BUY}`],
    [BANDS.BUY, BANDS.STRONG_BUY, "var(--tier-buy)", `Buy above ${BANDS.BUY}`],
    [BANDS.WATCH, BANDS.BUY, "var(--tier-watch)", `Watch above ${BANDS.WATCH}`],
  ];

  const onMove = (e: React.MouseEvent) => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect || pts.length < 2) return;
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const i = Math.round(
      ((px - PAD.l) / (W - PAD.l - PAD.r)) * (pts.length - 1)
    );
    setHover(Math.max(0, Math.min(pts.length - 1, i)));
  };

  const hp = hover != null ? pts[hover] : null;
  const gapUnpriced =
    stock.components.gap != null && stock.priced_in != null
      ? `the market prices ${pct(stock.priced_in)} of its story`
      : null;

  return (
    <div className="rounded-xl border border-hairline bg-surface p-6">
      <header className="mb-4 flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span className="text-[26px] font-bold tracking-tight">{stock.symbol}</span>
        <span className="text-ink-2">{stock.company}</span>
        <TierChip tier={stock.tier} />
        <span className="num ml-auto text-[26px] font-bold">{fmt(stock.score)}</span>
        <span className="text-[12px] text-ink-3">out of 10</span>
      </header>

      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        {zones.map(([a, b, c, label]) => (
          <g key={label}>
            <rect x={PAD.l} y={y(b)} width={W - PAD.l - PAD.r} height={y(a) - y(b)} fill={c} opacity="0.13" />
            <text x={W - PAD.r + 8} y={(y(a) + y(b)) / 2 + 3} fontSize="10.5" fill="var(--ink-3)">
              {label}
            </text>
          </g>
        ))}
        <line x1={PAD.l} x2={W - PAD.r} y1={y(BANDS.EXIT)} y2={y(BANDS.EXIT)}
          stroke="var(--down)" strokeWidth="1" strokeDasharray="3,3" opacity="0.65" />
        <text x={W - PAD.r + 8} y={y(BANDS.EXIT) + 3} fontSize="10.5" fill="var(--down)" opacity="0.85">
          exits below {BANDS.EXIT}
        </text>

        {[...new Set([Math.ceil(lo), Math.floor(hi)])].map((t) => (
          <text key={t} x={PAD.l - 8} y={y(t) + 3} fontSize="10" fill="var(--ink-3)" textAnchor="end" className="num">
            {t}
          </text>
        ))}
        {pts.length > 1 &&
          [0, Math.floor((pts.length - 1) / 2), pts.length - 1].map((i) => (
            <text key={i} x={x(i)} y={H - 6} fontSize="10" fill="var(--ink-3)"
              textAnchor={i === 0 ? "start" : i === pts.length - 1 ? "end" : "middle"}>
              {pts[i].date}
            </text>
          ))}

        <path d={line} fill="none" stroke="var(--ink)" strokeWidth="2" strokeLinejoin="round" />
        {last && (
          <>
            <circle cx={x(pts.length - 1)} cy={y(last.score)} r="4" fill="var(--ink)" />
            <text x={x(pts.length - 1)} y={y(last.score) - 9} fontSize="12" fontWeight="700"
              fill="var(--ink)" textAnchor="middle" className="num">
              {fmt(last.score)}
            </text>
          </>
        )}

        {hp && hover != null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={PAD.t} y2={H - PAD.b}
              stroke="var(--baseline)" strokeWidth="1" />
            <circle cx={x(hover)} cy={y(hp.score)} r="4" fill="var(--surface)"
              stroke="var(--ink)" strokeWidth="2" />
            <g transform={`translate(${Math.min(x(hover) + 10, W - PAD.r - 150)}, ${PAD.t + 6})`}>
              <rect width="150" height="40" rx="6" fill="var(--surface)" stroke="var(--hairline)" />
              <text x="10" y="17" fontSize="11" fill="var(--ink-2)">{hp.date}</text>
              <text x="10" y="32" fontSize="12" fontWeight="700" fill="var(--ink)" className="num">
                {fmt(hp.score)}
                <tspan fontWeight="400" fill="var(--ink-2)"> · {hp.tier ?? "off board"}</tspan>
              </text>
            </g>
          </g>
        )}
      </svg>

      <div className="mt-5 grid grid-cols-1 gap-4 border-t border-hairline pt-4 sm:grid-cols-3">
        {(
          [
            ["quality", "Quality", "a durable business — the 10-year road"],
            ["value", "Value", "price against its true peers"],
            ["gap", "Narrative gap", gapUnpriced ?? "story the price ignores"],
          ] as const
        ).map(([key, label, sub]) => (
          <div key={key} className="flex items-center gap-4">
            <div className="min-w-0 flex-1">
              <div className="kicker">{label}</div>
              <div className="num text-[22px] font-bold">{fmt(stock.components[key])}</div>
              <div className="truncate text-[11.5px] text-ink-3">{sub}</div>
            </div>
            <Sparkline points={componentSeries(stock.history, key)} width={100} height={30} />
          </div>
        ))}
      </div>
    </div>
  );
}
