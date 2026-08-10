// Compact score-path chart: the last ~60 readings travelling through the
// tier bands. B2's judgment strip — trajectory where B1's ruler shows state.

import { BANDS } from "@/lib/api";
import { fmt, scoreDomain } from "./shared";

export default function MiniPath({
  points,
  width = 620,
  height = 120,
}: {
  points: { date: string; score: number }[];
  width?: number;
  height?: number;
}) {
  const pts = points.slice(-60);
  if (pts.length < 2)
    return <div className="text-[12px] text-ink-3 italic">not enough history yet</div>;
  const PAD = { l: 4, r: 40, t: 6, b: 16 };
  const [lo, hi] = scoreDomain(pts.map((p) => p.score));
  const x = (i: number) => PAD.l + (i / (pts.length - 1)) * (width - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (1 - (v - lo) / (hi - lo)) * (height - PAD.t - PAD.b);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.score).toFixed(1)}`).join("");
  const last = pts[pts.length - 1];
  const zones: [number, number, string][] = [
    [BANDS.STRONG_BUY, hi, "var(--tier-sb)"],
    [BANDS.BUY, BANDS.STRONG_BUY, "var(--tier-buy)"],
    [BANDS.WATCH, BANDS.BUY, "var(--tier-watch)"],
  ];
  return (
    <svg width={width} height={height} aria-label="score path through the bands">
      {zones.map(([a, b, c]) => (
        <rect key={c} x={PAD.l} y={y(b)} width={width - PAD.l - PAD.r}
          height={Math.max(y(a) - y(b), 0)} fill={c} opacity="0.15" />
      ))}
      <line x1={PAD.l} x2={width - PAD.r} y1={y(BANDS.EXIT)} y2={y(BANDS.EXIT)}
        stroke="var(--down)" strokeWidth="1" strokeDasharray="3,3" opacity="0.6" />
      {/* threshold labels, right edge */}
      {([[BANDS.STRONG_BUY, "4.6"], [BANDS.BUY, "3.6"]] as const).map(([v, t]) => (
        <text key={t} x={width - PAD.r + 4} y={y(v) + 3} fontSize="9" fill="var(--ink-3)" className="num">
          {t}
        </text>
      ))}
      <path d={d} fill="none" stroke="var(--ink)" strokeWidth="1.8" strokeLinejoin="round" />
      <circle cx={x(pts.length - 1)} cy={y(last.score)} r="3.5" fill="var(--ink)" />
      <text x={x(pts.length - 1) + 7} y={y(last.score) + 3.5} fontSize="11" fontWeight="700"
        fill="var(--ink)" className="num">
        {fmt(last.score)}
      </text>
      <text x={PAD.l} y={height - 4} fontSize="9.5" fill="var(--ink-3)">{pts[0].date}</text>
      <text x={width - PAD.r} y={height - 4} fontSize="9.5" fill="var(--ink-3)" textAnchor="end">
        {last.date}
      </text>
    </svg>
  );
}
