"use client";

// CALLS — the evidence trail, not a wall of text. A compact strip of
// filing events; the selected date opens one card: themes / catalysts /
// risks (clipped counts) + that day's claims + SEC link. 8-K days with no
// call show titles only.

import { useMemo, useState } from "react";
import { Claim, EarningsCall, Filing, FilingEvent } from "@/lib/api";

const day = (d: string) => d.slice(0, 10);
const nice = (d: string) =>
  new Date(day(d) + "T00:00:00").toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
  });

function Direction({ dir }: { dir: string | null }) {
  if (!dir) return null;
  const up = dir.toLowerCase() === "up" || dir.toLowerCase() === "positive";
  const down = dir.toLowerCase() === "down" || dir.toLowerCase() === "negative";
  return (
    <span
      className="w-11 shrink-0 text-[10.5px] font-bold uppercase"
      style={{ color: up ? "var(--up)" : down ? "var(--down)" : "var(--ink-3)" }}
    >
      {dir}
    </span>
  );
}

export default function CallsStack({
  events,
  calls,
  filings,
  claims,
}: {
  events: FilingEvent[];
  calls: EarningsCall[];
  filings: Filing[];
  claims: Claim[];
}) {
  // group events by day, keep chronological
  const days = useMemo(() => {
    const m = new Map<string, FilingEvent[]>();
    for (const e of events) m.set(day(e.date), [...(m.get(day(e.date)) ?? []), e]);
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [events]);
  const callByDay = useMemo(
    () => new Map(calls.map((c) => [day(c.date), c])),
    [calls]
  );
  const latestCallDay =
    days.filter(([d, es]) => callByDay.has(d) || es.some((e) => e.type === "EARN_CALL"))
      .map(([d]) => d)
      .pop() ?? days[days.length - 1]?.[0];
  const [sel, setSel] = useState<string | undefined>(latestCallDay);

  const selEvents = days.find(([d]) => d === sel)?.[1] ?? [];
  const call = sel ? callByDay.get(sel) : undefined;
  const dayClaims = sel ? claims.filter((c) => day(c.call_date) === sel) : [];
  const secUrl = sel
    ? filings.find((f) => day(f.date) === sel && f.url)?.url
    : undefined;

  if (days.length === 0)
    return <p className="text-[12px] italic text-ink-3">no filings on record yet</p>;

  // Earnings and periodic filings carry the strip; days that are ONLY
  // 8-Ks compress to slim ticks — still there, still clickable, never
  // hidden (material news arrives by 8-K), just not costing width.
  const MAJOR = new Set(["EARN_CALL", "10-K", "10-Q"]);
  const isMajor = (es: FilingEvent[]) => es.some((e) => MAJOR.has(e.type));

  // Tone / trajectory / strength print only when the value DIFFERS across
  // this company's calls (addendum #8): if every call is "confident /
  // accelerating", the words carry no information and would read as a
  // per-call signal that isn't there.
  const varies = (get: (c: EarningsCall) => string | number | null) =>
    new Set(calls.map(get).filter((v) => v != null)).size > 1;
  const toneVaries = varies((c) => c.management_tone);
  const trajectoryVaries = varies((c) => c.trajectory);
  const strengthVaries = varies((c) => c.narrative_strength);

  return (
    <div>
      <div className="mb-4 flex items-end gap-1 overflow-x-auto border-b border-hairline">
        {days.map(([d, es]) =>
          isMajor(es) ? (
            <button
              key={d}
              type="button"
              onClick={() => setSel(d)}
              className={`shrink-0 border-b-2 px-3 pb-2 pt-1 text-left ${
                sel === d ? "border-ink" : "border-transparent hover:border-baseline"
              }`}
            >
              <span className={`block text-[12px] ${sel === d ? "font-bold" : "text-ink-2"}`}>
                {nice(d)}
              </span>
              {[...new Set(es.map((e) => e.type))].map((t) => (
                <span key={t} className="block text-[9.5px] uppercase tracking-[0.06em] text-ink-3">
                  {t.replace("_", " ")}
                </span>
              ))}
            </button>
          ) : (
            <button
              key={d}
              type="button"
              onClick={() => setSel(d)}
              title={`${nice(d)} — ${es.length} 8-K`}
              className={`shrink-0 border-b-2 px-1.5 pb-2 pt-1 ${
                sel === d ? "border-ink" : "border-transparent hover:border-baseline"
              }`}
            >
              <span className={`block text-[9.5px] ${sel === d ? "font-bold text-ink" : "text-ink-3"}`}>
                {nice(d).split(" ")[0]}
              </span>
              <span className="mx-auto block h-1.5 w-1.5 rounded-full bg-baseline" />
            </button>
          )
        )}
      </div>

      {call ? (
        <div>
          <div className="mb-3 flex flex-wrap items-baseline gap-x-3 text-[13px]">
            <span className="font-bold">{nice(call.date)}</span>
            {toneVaries && call.management_tone && (
              <span className="text-ink-2">{call.management_tone}</span>
            )}
            {trajectoryVaries && call.trajectory && (
              <span className="text-ink-2">· {call.trajectory}</span>
            )}
            {strengthVaries && call.narrative_strength != null && (
              <span className="num text-ink-3">· strength {call.narrative_strength.toFixed(2)}</span>
            )}
          </div>
          {call.themes.length > 0 && (
            <>
              <div className="kicker mb-1 text-[10px]">Themes</div>
              <ul className="mb-3">
                {call.themes.slice(0, 4).map((t, i) => (
                  <li key={i} className="border-b border-hairline py-1.5 text-[13px] text-ink-2 last:border-b-0">
                    {t}
                  </li>
                ))}
              </ul>
            </>
          )}
          {call.catalysts.length > 0 && (
            <>
              <div className="kicker mb-1 text-[10px]">Catalysts</div>
              <ul className="mb-3">
                {call.catalysts.slice(0, 3).map((t, i) => (
                  <li key={i} className="border-b border-hairline py-1.5 text-[13px] text-ink-2 last:border-b-0">
                    {t}
                  </li>
                ))}
              </ul>
            </>
          )}
          {call.risks.length > 0 && (
            <>
              <div className="kicker mb-1 text-[10px]">Risks</div>
              <ul className="mb-3">
                {call.risks.slice(0, 3).map((t, i) => (
                  <li key={i} className="border-b border-hairline py-1.5 text-[13px] text-ink-2 last:border-b-0">
                    {t}
                  </li>
                ))}
              </ul>
            </>
          )}
          {dayClaims.length > 0 && (
            <>
              <div className="kicker mb-1 text-[10px]">Claims</div>
              <div className="mb-3">
                {dayClaims.map((c, i) => (
                  <div key={i} className="flex items-baseline gap-3 border-b border-hairline py-1.5 last:border-b-0">
                    <span className="w-28 shrink-0 text-[11px] text-ink-3">
                      {c.type.replace(/_/g, " ")}
                    </span>
                    <Direction dir={c.direction} />
                    <span className="min-w-0 text-[13px] text-ink-2">{c.text}</span>
                  </div>
                ))}
              </div>
            </>
          )}
          {secUrl && (
            <a href={secUrl} target="_blank" rel="noreferrer"
              className="text-[12.5px] font-semibold underline decoration-hairline underline-offset-4 hover:decoration-ink">
              SEC filing →
            </a>
          )}
        </div>
      ) : (
        <div>
          {selEvents.map((e, i) => (
            <div key={i} className="border-b border-hairline py-1.5 text-[13px] text-ink-2 last:border-b-0">
              <span className="mr-2 text-[10.5px] uppercase tracking-[0.06em] text-ink-3">
                {e.type.replace("_", " ")}
              </span>
              {e.title ?? "filed"}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
