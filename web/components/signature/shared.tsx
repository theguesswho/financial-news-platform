import { BANDS, Components, HistoryPoint } from "@/lib/api";

export const TIER_COLOR: Record<string, string> = {
  "Strong Buy": "var(--tier-sb)",
  Buy: "var(--tier-buy)",
  Watch: "var(--tier-watch)",
};

export function TierChip({ tier, grace }: { tier: string | null; grace?: boolean }) {
  if (!tier)
    return <span className="text-ink-3 text-[12px] italic">off the board</span>;
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className="rounded-md px-2 py-0.5 text-[11.5px] font-bold tracking-[0.05em] uppercase"
        style={{
          color: "var(--surface)",
          background: TIER_COLOR[tier] ?? "var(--ink-3)",
        }}
      >
        {tier}
      </span>
      {grace && (
        <span className="text-[11.5px] text-ink-2 italic">
          holding its seat — leaves if it stays below 3.4
        </span>
      )}
    </span>
  );
}

export function fmt(v: number | null | undefined, dp = 1): string {
  return v == null ? "—" : v.toFixed(dp);
}

export function pct(v: number | null | undefined, dp = 0): string {
  return v == null ? "—" : `${(v * 100).toFixed(dp)}%`;
}

/** Chronological history rows that actually carry a score. */
export function scored(history: HistoryPoint[]) {
  return history.filter((h) => h.score != null) as (HistoryPoint & {
    score: number;
  })[];
}

export function componentSeries(
  history: HistoryPoint[],
  key: keyof Components
) {
  return history
    .filter((h) => h.components[key] != null)
    .map((h) => ({ date: h.date, value: h.components[key] as number }));
}

/** Shared y-domain for score charts: always show the full band structure. */
export function scoreDomain(values: number[]): [number, number] {
  const lo = Math.min(BANDS.EXIT - 0.4, ...values) - 0.15;
  const hi = Math.max(BANDS.STRONG_BUY + 0.8, ...values) + 0.25;
  return [lo, hi];
}

export function Sparkline({
  points,
  width = 120,
  height = 34,
  stroke = "var(--ink-2)",
}: {
  points: { value: number }[];
  width?: number;
  height?: number;
  stroke?: string;
}) {
  if (points.length < 2)
    return <div className="text-[11px] text-ink-3 italic">not enough history</div>;
  const vs = points.map((p) => p.value);
  let lo = Math.min(...vs);
  let hi = Math.max(...vs);
  // Floor the span so a 0.3-point wiggle on the 10-point scale doesn't
  // render as a cliff (honest surfaces: amplitude should mean something).
  const MIN_SPAN = 1.5;
  if (hi - lo < MIN_SPAN) {
    const mid = (hi + lo) / 2;
    lo = mid - MIN_SPAN / 2;
    hi = mid + MIN_SPAN / 2;
  }
  const pad = (hi - lo) * 0.15;
  const y = (v: number) =>
    height - 3 - ((v - lo + pad) / (hi - lo + 2 * pad)) * (height - 6);
  const x = (i: number) => 2 + (i / (points.length - 1)) * (width - 4);
  const d = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join("");
  const last = points[points.length - 1];
  return (
    <svg width={width} height={height} aria-hidden>
      <path d={d} fill="none" stroke={stroke} strokeWidth="1.5" />
      <circle cx={x(points.length - 1)} cy={y(last.value)} r="2.5" fill={stroke} />
    </svg>
  );
}

/** Horizontal band ruler: zone washes + threshold ticks + marker + trail. */
export function BandStrip({
  score,
  trail = [],
  width = 260,
  height = 30,
  showLabels = false,
}: {
  score: number;
  trail?: number[];
  width?: number;
  height?: number;
  showLabels?: boolean;
}) {
  const [lo, hi] = scoreDomain([score, ...trail]);
  const x = (v: number) => ((v - lo) / (hi - lo)) * width;
  const zoneY = showLabels ? 12 : 4;
  const zoneH = height - zoneY - 4;
  const cy = zoneY + zoneH / 2;
  const zones: [number, number, string, string][] = [
    [BANDS.STRONG_BUY, hi, "var(--tier-sb)", "Strong Buy"],
    [BANDS.BUY, BANDS.STRONG_BUY, "var(--tier-buy)", "Buy"],
    [BANDS.WATCH, BANDS.BUY, "var(--tier-watch)", "Watch"],
  ];
  return (
    <svg width={width} height={height} aria-label={`score ${fmt(score)} on the band scale`}>
      {zones.map(([a, b, c, label]) => (
        <g key={label}>
          <rect x={x(a)} y={zoneY} width={x(b) - x(a)} height={zoneH} fill={c} opacity="0.18" />
          {/* label a zone only when it's wide enough to hold the text */}
          {showLabels && x(b) - x(a) >= 52 && (
            <text x={x(a) + 3} y={9} fontSize="8.5" fill="var(--ink-3)" letterSpacing="0.08em">
              {label.toUpperCase()} &gt;{a}
            </text>
          )}
        </g>
      ))}
      <line x1={x(BANDS.EXIT)} x2={x(BANDS.EXIT)} y1={zoneY} y2={zoneY + zoneH}
        stroke="var(--down)" strokeWidth="1" strokeDasharray="2,2" opacity="0.7" />
      {trail.map((v, i) => (
        <circle key={i} cx={x(v)} cy={cy} r="2"
          fill="var(--ink-2)" opacity={0.12 + 0.5 * (i / Math.max(trail.length - 1, 1))} />
      ))}
      <circle cx={x(score)} cy={cy} r="4.5" fill="var(--ink)" />
    </svg>
  );
}
