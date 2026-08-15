// The current (pre-mock-review) site chrome: five-nouns nav. Mock routes
// (/home, /companies) live outside this group and carry their own chrome.

const NAV = [
  { label: "Narratives", href: "/" },
  { label: "The Board", href: "/board" },
  { label: "Companies", href: null },
  { label: "What Changed", href: null },
  { label: "Portfolio", href: null },
] as const;

export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className="border-b border-hairline bg-surface">
        <nav className="mx-auto flex max-w-[1100px] flex-wrap items-baseline gap-x-6 gap-y-1 px-6 py-3">
          {NAV.map(({ label, href }) =>
            href ? (
              <a key={label} href={href} className="text-[13.5px] font-semibold">
                {label}
              </a>
            ) : (
              <span key={label} className="text-[13.5px] text-ink-3" title="not built yet">
                {label}
              </span>
            )
          )}
        </nav>
      </header>
      {children}
    </>
  );
}
