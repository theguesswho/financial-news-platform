"use client";

// The dossier's company toggle: a dropdown over the covered board plus
// prev/next stepping in board-rank order. This is the real product
// mechanism for moving between dossiers (besides clicking a Board row).

import { useRouter } from "next/navigation";

export type SwitcherOption = {
  symbol: string;
  company: string | null;
  tier: string | null;
};

export default function CompanySwitcher({
  options,
  current,
}: {
  options: SwitcherOption[];
  current: string;
}) {
  const router = useRouter();
  const idx = Math.max(0, options.findIndex((o) => o.symbol === current));
  const go = (s: string) => router.push(`/signature?symbol=${s}`);
  const prev = options[(idx - 1 + options.length) % options.length];
  const next = options[(idx + 1) % options.length];
  const btn =
    "rounded-md border border-hairline bg-surface px-2 py-1 text-[13px] text-ink-2 hover:border-baseline";
  return (
    <div className="flex items-center gap-1.5">
      <button className={btn} aria-label={`previous: ${prev.symbol}`} onClick={() => go(prev.symbol)}>
        ←
      </button>
      <select
        className="max-w-[16rem] rounded-md border border-hairline bg-surface px-2 py-1 text-[13px]"
        value={current}
        onChange={(e) => go(e.target.value)}
        aria-label="company"
      >
        {options.map((o) => (
          <option key={o.symbol} value={o.symbol}>
            {o.symbol} — {o.company ?? "?"} · {o.tier ?? "off board"}
          </option>
        ))}
      </select>
      <button className={btn} aria-label={`next: ${next.symbol}`} onClick={() => go(next.symbol)}>
        →
      </button>
    </div>
  );
}
