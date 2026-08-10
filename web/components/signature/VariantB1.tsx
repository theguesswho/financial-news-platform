// B1 — triptych with the band RULER: judgment as state (where it sits
// today, last 30 readings as a fading trail), plus the real company
// switcher the dossier header will carry.

import { Stock } from "@/lib/api";
import { BandStrip, fmt, scored, TierChip } from "./shared";
import { EvidenceRow } from "./evidence";
import CompanySwitcher, { SwitcherOption } from "./CompanySwitcher";

export default function VariantB1({
  stock,
  options,
}: {
  stock: Stock;
  options: SwitcherOption[];
}) {
  const pts = scored(stock.history);
  const trail = pts.slice(-30, -1).map((p) => p.score);
  return (
    <div className="rounded-xl border border-hairline bg-surface p-6">
      <header className="mb-1 flex flex-wrap items-baseline gap-x-4 gap-y-2">
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
        <BandStrip score={stock.score} trail={trail} width={620} height={44} showLabels />
        <div className="text-[11.5px] text-ink-3">
          the dot is today; the fading trail is the last 30 readings
        </div>
      </div>

      <EvidenceRow stock={stock} />
    </div>
  );
}
