"use client";

// THE PATH — composite score through the band washes (with hover), then
// the price series with 52w marks and faint filing-date ticks. This chart
// is where the full history (including off-board prints) is told; the
// hero band strip stays on the tier scale.

import { useMemo, useRef, useState } from "react";
import { BANDS, FilingEvent } from "@/lib/api";
import { fmt, scoreDomain } from "@/components/signature/shared";

const W = 860;

export function ScorePath({
  points,
}: {
  points: { date: string; score: number; tier: string | null }[];
}) {
  const H = 240;
  const PAD = { l: 30, r: 110, t: 12, b: 20 };
  const [hover, setHover] = useState<number | null>(null);
  const ref = useRef<SVGSVGElement>(null);
  const [lo, hi] = scoreDomain(points.map((p) => p.score));
  const x = (i: number) => PAD.l + (i / Math.max(points.length - 1, 1)) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (1 - (v - lo) / (hi - lo)) * (H - PAD.t - PAD.b);
  const d = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.score).toFixed(1)}`).join("");
  const last = points[points.length - 1];
  const zones: [number, number, string, string][] = [
    [BANDS.STRONG_BUY, hi, "var(--tier-sb)", `Strong Buy above ${BANDS.STRONG_BUY}`],
    [BANDS.BUY, BANDS.STRONG_BUY, "var(--tier-buy)", `Buy above ${BANDS.BUY}`],
    [BANDS.WATCH, BANDS.BUY, "var(--tier-watch)", `Watch above ${BANDS.WATCH}`],
  ];
  const onMove = (e: React.MouseEvent) => {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect || points.length < 2) return;
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const i = Math.round(((px - PAD.l) / (W - PAD.l - PAD.r)) * (points.length - 1));
    setHover(Math.max(0, Math.min(points.length - 1, i)));
  };
  const hp = hover != null ? points[hover] : null;
  if (points.length < 2)
    return <p className="text-[12px] italic text-ink-3">not enough score history yet</p>;
  return (
    <svg ref={ref} viewBox={`0 0 ${W} ${H}`} className="w-full"
      onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
      {zones.map(([a, b, c, label]) => (
        <g key={label}>
          <rect x={PAD.l} y={y(b)} width={W - PAD.l - PAD.r} height={Math.max(y(a) - y(b), 0)} fill={c} opacity="0.13" />
          <text x={W - PAD.r + 8} y={(y(a) + y(b)) / 2 + 3} fontSize="10" fill="var(--ink-3)">{label}</text>
        </g>
      ))}
      <line x1={PAD.l} x2={W - PAD.r} y1={y(BANDS.EXIT)} y2={y(BANDS.EXIT)}
        stroke="var(--down)" strokeWidth="1" strokeDasharray="3,3" opacity="0.6" />
      <text x={W - PAD.r + 8} y={y(BANDS.EXIT) + 3} fontSize="10" fill="var(--down)" opacity="0.85">
        exits below {BANDS.EXIT}
      </text>
      {[Math.ceil(lo), Math.floor(hi)].map((t) => (
        <text key={t} x={PAD.l - 7} y={y(t) + 3} fontSize="9.5" fill="var(--ink-3)" textAnchor="end" className="num">{t}</text>
      ))}
      {[0, Math.floor((points.length - 1) / 2), points.length - 1].map((i) => (
        <text key={i} x={x(i)} y={H - 5} fontSize="9.5" fill="var(--ink-3)"
          textAnchor={i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"}>
          {points[i].date}
        </text>
      ))}
      <path d={d} fill="none" stroke="var(--ink)" strokeWidth="1.8" strokeLinejoin="round" />
      {last && (
        <>
          <circle cx={x(points.length - 1)} cy={y(last.score)} r="3.5" fill="var(--ink)" />
          <text x={x(points.length - 1)} y={y(last.score) - 8} fontSize="11.5" fontWeight="700"
            fill="var(--ink)" textAnchor="middle" className="num">{fmt(last.score)}</text>
        </>
      )}
      {hp && hover != null && (
        <g>
          <line x1={x(hover)} x2={x(hover)} y1={PAD.t} y2={H - PAD.b} stroke="var(--baseline)" strokeWidth="1" />
          <circle cx={x(hover)} cy={y(hp.score)} r="3.5" fill="var(--surface)" stroke="var(--ink)" strokeWidth="2" />
          <g transform={`translate(${Math.min(x(hover) + 10, W - PAD.r - 160)}, ${PAD.t + 4})`}>
            <rect width="160" height="38" rx="5" fill="var(--surface)" stroke="var(--hairline)" />
            <text x="9" y="15" fontSize="10.5" fill="var(--ink-2)">{hp.date}</text>
            <text x="9" y="30" fontSize="11.5" fontWeight="700" fill="var(--ink)" className="num">
              {fmt(hp.score)}
              <tspan fontWeight="400" fill="var(--ink-2)"> · {hp.tier ?? "off board"}</tspan>
            </text>
          </g>
        </g>
      )}
    </svg>
  );
}

export function PricePath({
  prices,
  events,
  week52High,
  week52Low,
}: {
  prices: { date: string; close: number | null }[];
  events: FilingEvent[];
  week52High: number | null;
  week52Low: number | null;
}) {
  const H = 190;
  const PAD = { l: 30, r: 110, t: 12, b: 20 };
  const pts = useMemo(
    () => prices.filter((p) => p.close != null) as { date: string; close: number }[],
    [prices]
  );
  if (pts.length < 2)
    return <p className="text-[12px] italic text-ink-3">no price series yet</p>;
  const vals = pts.map((p) => p.close);
  const lo = Math.min(...vals, week52Low ?? Infinity) * 0.98;
  const hi = Math.max(...vals, week52High ?? -Infinity) * 1.02;
  const x = (i: number) => PAD.l + (i / (pts.length - 1)) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (1 - (v - lo) / (hi - lo)) * (H - PAD.t - PAD.b);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.close).toFixed(1)}`).join("");
  const dateIdx = new Map(pts.map((p, i) => [p.date, i]));
  const ticks = [...new Set(
    events
      .map((e) => dateIdx.get(e.date.slice(0, 10)))
      .filter((i): i is number => i != null)
  )];
  const last = pts[pts.length - 1];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      {ticks.map((i) => (
        <line key={i} x1={x(i)} x2={x(i)} y1={PAD.t} y2={H - PAD.b}
          stroke="var(--baseline)" strokeWidth="1" opacity="0.45" />
      ))}
      {week52High != null && (
        <>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(week52High)} y2={y(week52High)}
            stroke="var(--ink-3)" strokeWidth="0.8" strokeDasharray="2,3" />
          <text x={W - PAD.r + 8} y={y(week52High) + 3} fontSize="9.5" fill="var(--ink-3)" className="num">
            52w high {week52High.toFixed(2)}
          </text>
        </>
      )}
      {week52Low != null && (
        <>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(week52Low)} y2={y(week52Low)}
            stroke="var(--ink-3)" strokeWidth="0.8" strokeDasharray="2,3" />
          <text x={W - PAD.r + 8} y={y(week52Low) + 3} fontSize="9.5" fill="var(--ink-3)" className="num">
            52w low {week52Low.toFixed(2)}
          </text>
        </>
      )}
      <path d={d} fill="none" stroke="var(--ink)" strokeWidth="1.5" strokeLinejoin="round" />
      <circle cx={x(pts.length - 1)} cy={y(last.close)} r="3" fill="var(--ink)" />
      <text x={x(pts.length - 1) - 6} y={y(last.close) + 12} fontSize="10.5" fontWeight="700"
        fill="var(--ink)" textAnchor="end" className="num">{last.close.toFixed(2)}</text>
      {[0, Math.floor((pts.length - 1) / 2), pts.length - 1].map((i) => (
        <text key={i} x={x(i)} y={H - 5} fontSize="9.5" fill="var(--ink-3)"
          textAnchor={i === 0 ? "start" : i === pts.length - 1 ? "end" : "middle"}>
          {pts[i].date}
        </text>
      ))}
    </svg>
  );
}
