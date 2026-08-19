"use client";

// Mock chrome for the proposed product shape: wordmark, universe search,
// nav nouns. "THE BOARD" stays the working masthead until named.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useRef, useState } from "react";

export type SearchName = {
  symbol: string;
  company: string | null;
  tier: string | null;
};

function Search({ names }: { names: SearchName[] }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);

  const hits = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return [];
    return names
      .filter(
        (n) =>
          n.symbol.toLowerCase().startsWith(s) ||
          (n.company ?? "").toLowerCase().includes(s)
      )
      .slice(0, 8);
  }, [q, names]);

  const go = (sym: string) => {
    setQ("");
    setOpen(false);
    router.push(`/companies/${sym}`);
  };

  return (
    <div ref={boxRef} className="relative min-w-0 flex-1">
      <input
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
          setHi(0);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") setHi((h) => Math.min(h + 1, hits.length - 1));
          else if (e.key === "ArrowUp") setHi((h) => Math.max(h - 1, 0));
          else if (e.key === "Enter" && hits[hi]) go(hits[hi].symbol);
          else if (e.key === "Escape") setOpen(false);
        }}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={`Any of ${names.length} names`}
        aria-label="search companies"
        className="w-full rounded-md border border-hairline bg-surface px-3 py-1.5 text-[13px] placeholder:text-ink-3 focus:border-baseline focus:outline-none"
      />
      {open && hits.length > 0 && (
        <div className="absolute top-full z-20 mt-1 w-full overflow-hidden rounded-md border border-hairline bg-surface shadow-sm">
          {hits.map((n, i) => (
            <button
              key={n.symbol}
              type="button"
              onMouseDown={() => go(n.symbol)}
              className={`flex w-full items-baseline gap-3 px-3 py-1.5 text-left text-[13px] ${
                i === hi ? "bg-page" : ""
              }`}
            >
              <span className="w-14 font-bold">{n.symbol}</span>
              <span className="min-w-0 flex-1 truncate text-ink-2">{n.company}</span>
              <span className="text-[11px] text-ink-3">{n.tier ?? "off board"}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// Five nouns — order decided by Edmund 2026-08-19 (FIXPACK B3): News
// Wire joins between What changed and Track record.
const NAV = [
  ["The Board", "/"],
  ["Forces", "/forces"],
  ["What changed", "/changed"],
  ["News Wire", "/wire"],
  ["Track record", "/record"],
] as const;

export default function Chrome({
  names,
  context,
  active,
}: {
  names: SearchName[];
  context?: string; // e.g. "ACM · Fri 14 Aug 2026"
  active?: (typeof NAV)[number][0];
}) {
  return (
    <header className="sticky top-0 z-10 border-b border-hairline bg-surface">
      <div className="mx-auto flex max-w-[1280px] items-center gap-5 px-6 py-2.5">
        <Link href="/" className="flex shrink-0 items-center gap-2">
          <span className="inline-block h-3 w-3 bg-[var(--tier-sb)]" />
          <span className="text-[13.5px] font-bold tracking-[0.12em]">THE BOARD</span>
        </Link>
        <Search names={names} />
        <nav className="hidden shrink-0 items-baseline gap-4 text-[13px] md:flex">
          {NAV.map(([label, href]) => (
            <Link
              key={label}
              href={href}
              className={
                label === active
                  ? "font-semibold underline decoration-2 underline-offset-8"
                  : "text-ink-2 hover:text-ink"
              }
            >
              {label}
            </Link>
          ))}
        </nav>
        {context && (
          <span className="num hidden shrink-0 text-[12.5px] text-ink-2 lg:block">
            {context}
          </span>
        )}
      </div>
    </header>
  );
}
