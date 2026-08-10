// B2 — triptych with the PATH: judgment as trajectory (the last ~60
// readings travelling through the bands), same evidence panes beneath.

import { Stock } from "@/lib/api";
import { fmt, scored, TierChip } from "./shared";
import { EvidenceRow } from "./evidence";
import MiniPath from "./MiniPath";
import CompanySwitcher, { SwitcherOption } from "./CompanySwitcher";

export default function VariantB2({
  stock,
  options,
}: {
  stock: Stock;
  options: SwitcherOption[];
}) {
  const pts = scored(stock.history);
  return (
    <div className="rounded-xl border border-hairline bg-surface p-6">
      <header className="mb-3 flex flex-wrap items-baseline gap-x-4 gap-y-2">
        <span className="text-[26px] font-bold tracking-tight">{stock.symbol}</span>
        <span className="text-ink-2">{stock.company}</span>
        <TierChip tier={stock.tier} />
        <span className="ml-auto">
          <CompanySwitcher options={options} current={stock.symbol} />
        </span>
        <span className="num text-[26px] font-bold">{fmt(stock.score)}</span>
        <span className="text-[12px] text-ink-3">out of 10</span>
      </header>

      <div className="mb-5">
        <MiniPath points={pts} />
        <div className="text-[11.5px] text-ink-3">
          the composite&apos;s path through the tier bands, last {Math.min(pts.length, 60)} readings
        </div>
      </div>

      <EvidenceRow stock={stock} />
    </div>
  );
}
