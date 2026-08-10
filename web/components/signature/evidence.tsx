// The three evidence panes shared by the B variants: the 10-year road,
// the peer-price comparison, and the narrative gap taught inline.

import { Stock } from "@/lib/api";
import { fmt, pct } from "./shared";

export function RevenueRoad({ stock }: { stock: Stock }) {
  const rows = [...stock.annual_history].reverse().filter((r) => r.revenue != null);
  if (rows.length < 2)
    return <div className="text-[12px] text-ink-3 italic">annual history still being gathered</div>;
  const W = 250;
  const H = 84;
  const max = Math.max(...rows.map((r) => r.revenue as number));
  const bw = Math.min(28, (W - 8) / rows.length - 4);
  return (
    <svg width={W} height={H + 16} aria-label="annual revenue">
      {rows.map((r, i) => {
        const h = ((r.revenue as number) / max) * (H - 12);
        const bx = 4 + i * ((W - 8) / rows.length);
        return (
          <g key={r.period_end}>
            <rect x={bx} y={H - h} width={bw} height={h} rx="3" fill="var(--ink-2)" opacity="0.75">
              <title>{`FY ${r.period_end.slice(0, 4)}: revenue $${((r.revenue as number) / 1e9).toFixed(1)}b, net margin ${pct(r.net_margin)}`}</title>
            </rect>
            <text x={bx + bw / 2} y={H + 12} fontSize="9.5" fill="var(--ink-3)" textAnchor="middle">
              {r.period_end.slice(2, 4)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function PeerPrice({ stock }: { stock: Stock }) {
  const g = stock.valuation_gaps.find((v) => v.pe_forward != null && v.peer_median_pe != null);
  if (!g)
    return <div className="text-[12px] text-ink-3 italic">no peer group priced yet</div>;
  const W = 250;
  const max = Math.max(g.pe_forward!, g.peer_median_pe!) * 1.25;
  const x = (v: number) => 6 + (v / max) * (W - 60);
  const cheaper = g.pe_discount != null && g.pe_discount > 0;
  return (
    <div>
      <svg width={W} height={64} aria-label="forward P/E vs peers">
        {(
          [
            [stock.symbol, g.pe_forward!, 20, "var(--ink)"],
            [`${g.peer_count ?? "—"} peers (median)`, g.peer_median_pe!, 46, "var(--ink-3)"],
          ] as const
        ).map(([label, v, cy, color]) => (
          <g key={label}>
            <line x1={6} x2={x(v)} y1={cy} y2={cy} stroke={color} strokeWidth="2" opacity="0.5" />
            <circle cx={x(v)} cy={cy} r="5" fill={color} />
            <text x={x(v) + 9} y={cy + 3.5} fontSize="10.5" fill="var(--ink-2)" className="num">
              {v.toFixed(1)}×
            </text>
            <text x={6} y={cy - 9} fontSize="9.5" fill="var(--ink-3)">{label}</text>
          </g>
        ))}
      </svg>
      <div className="text-[11.5px] text-ink-2">
        {cheaper
          ? <>priced <b>{pct(g.pe_discount)}</b> below its peers on next year&apos;s earnings</>
          : <>priced above its peers on next year&apos;s earnings</>}
      </div>
    </div>
  );
}

export function GapBar({ stock }: { stock: Stock }) {
  const exp = stock.components.exposure;
  const p = stock.priced_in;
  if (exp == null || p == null)
    return <div className="text-[12px] text-ink-3 italic">gap not measured yet</div>;
  const W = 250;
  const bar = (exp / 10) * (W - 10);
  const pricedW = bar * p;
  return (
    <div>
      <svg width={W} height={54}>
        <rect x={5} y={16} width={bar} height={18} rx="4" fill="var(--ink-3)" opacity="0.35">
          <title>{`exposure ${fmt(exp)} / 10`}</title>
        </rect>
        <rect x={5 + pricedW} y={16} width={bar - pricedW} height={18} rx="4" fill="var(--gap-accent)">
          <title>{`unpriced story: ${pct(1 - p)} of the exposure`}</title>
        </rect>
        <text x={5} y={10} fontSize="9.5" fill="var(--ink-3)">
          story exposure {fmt(exp)}/10
        </text>
        <text x={5 + pricedW + (bar - pricedW) / 2} y={47} fontSize="9.5"
          fill="var(--gap-accent)" textAnchor="middle" fontWeight="600">
          the gap
        </text>
      </svg>
      <div className="text-[11.5px] text-ink-2">
        the market prices <b>{pct(p)}</b> of its story — the shaded rest is what
        the price ignores
      </div>
    </div>
  );
}

export function EvidenceRow({ stock }: { stock: Stock }) {
  return (
    <div className="grid grid-cols-1 gap-6 border-t border-hairline pt-4 lg:grid-cols-3">
      <div>
        <div className="kicker">Quality — {fmt(stock.components.quality)}</div>
        <div className="mb-1 text-[11.5px] text-ink-3">
          is this a durable business? revenue, last {Math.min(stock.annual_history.length, 10)} fiscal years
        </div>
        <RevenueRoad stock={stock} />
      </div>
      <div>
        <div className="kicker">Value — {fmt(stock.components.value)}</div>
        <div className="mb-1 text-[11.5px] text-ink-3">
          is it fairly priced against companies with the same story?
        </div>
        <PeerPrice stock={stock} />
      </div>
      <div>
        <div className="kicker">Narrative gap — {fmt(stock.components.gap)}</div>
        <div className="mb-1 text-[11.5px] text-ink-3">
          how much of the story is the price ignoring?
        </div>
        <GapBar stock={stock} />
      </div>
    </div>
  );
}
