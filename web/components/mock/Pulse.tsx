// The pulse of one force: the weekly vital signs from the ledger.
// Support (links added or strengthened) above the line, erosion (weakened,
// removed, or gone quiet at earnings) below it — the up/down role, because
// this is direction of change, not conviction.
//
// Honesty rules, drawn not just documented:
//  - ONLY observed (non-seeding) weeks are charted. The backfill weeks are
//    the ledger's opening sweep — the instrument opening its eyes, not the
//    world changing — and their 300-op bars would dwarf every real week
//    and set the scale (addendum #9). They are acknowledged in the
//    footnote, never drawn as the lead.
//  - no momentum word appears anywhere — that column is still in shadow
//    (NARRATIVE_SPEC Phase 2), and every macro would read "accelerating".

import { HealthWeek } from "@/lib/api";

const W = 560;
const H = 116;
const MID = 50;     // the zero line: support above it, erosion below
const BAR = 38;     // tallest bar
const PAD = 8;

const shortWeek = (d: string) => {
  const [, m, day] = d.split("-");
  return `${+day} ${["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][+m]}`;
};

export default function Pulse({ weeks }: { weeks: HealthWeek[] }) {
  const observed = weeks.filter((w) => !w.seeding);
  const backfill = weeks.length - observed.length;

  if (observed.length === 0) {
    return (
      <p className="text-[12.5px] italic text-ink-3">
        no observed weeks yet — only the ledger&apos;s opening sweep
        {backfill > 0 && ` (${backfill} backfill week${backfill === 1 ? "" : "s"})`},
        which is the instrument opening its eyes, not the world changing
      </p>
    );
  }

  const max = Math.max(1, ...observed.map((w) => Math.max(w.support, w.erosion)));
  const slot = (W - PAD * 2) / observed.length;
  const barW = Math.min(22, slot * 0.42);
  const h = (v: number) => (v / max) * BAR;
  const attached = observed.filter((w) => w.active_exposures != null);
  const last = attached[attached.length - 1];

  return (
    <div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        role="img"
        aria-label="weekly support and erosion, observed weeks only"
      >
        <line x1={PAD} x2={W - PAD} y1={MID} y2={MID} stroke="var(--baseline)" strokeWidth="1" />
        {observed.map((w, i) => {
          const cx = PAD + slot * (i + 0.5);
          return (
            <g key={w.week_start}>
              {w.support > 0 && (
                <rect
                  x={cx - barW - 1} y={MID - h(w.support)} width={barW} height={h(w.support)}
                  fill="var(--up)" rx="1"
                >
                  <title>{`${w.week_start}: ${w.support} added or strengthened`}</title>
                </rect>
              )}
              {w.erosion > 0 && (
                <rect
                  x={cx + 1} y={MID} width={barW} height={h(w.erosion)}
                  fill="var(--down)" rx="1"
                >
                  <title>{`${w.week_start}: ${w.erosion} weakened, removed, or quiet`}</title>
                </rect>
              )}
              {w.active_exposures != null && (
                <text
                  x={cx} y={MID + BAR + 14} fontSize="10.5" textAnchor="middle"
                  fill="var(--ink-2)" className="num"
                >
                  {w.active_exposures}
                </text>
              )}
              <text
                x={cx} y={MID + BAR + 26} fontSize="9.5" textAnchor="middle"
                fill="var(--ink-3)" className="num"
              >
                {shortWeek(w.week_start)}
              </text>
            </g>
          );
        })}
      </svg>

      <p className="mt-1 text-[11.5px] leading-relaxed text-ink-3">
        Each observed week: links <span style={{ color: "var(--up)" }}>added or strengthened</span> above
        the line, <span style={{ color: "var(--down)" }}>weakened, removed, or gone quiet</span> below
        it; the number under each week is how many companies were attached
        {last?.active_exposures != null && <> (now {last.active_exposures})</>}.
        {backfill > 0 && (
          <>
            {" "}{backfill} earlier week{backfill === 1 ? "" : "s"} from the
            ledger&apos;s opening sweep {backfill === 1 ? "is" : "are"} not drawn —
            the instrument opening its eyes, not the world changing.
          </>
        )}
      </p>
    </div>
  );
}
