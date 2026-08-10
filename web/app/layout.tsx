import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  // Product name/masthead still an open decision (DESIGN_BRIEF.md);
  // plain page titles until it lands.
  title: "The Board",
  description: "A discovery instrument with a judgment layer.",
};

const NAV = [
  { label: "The Board", href: "/" },
  { label: "Companies", href: null },
  { label: "Narratives", href: null },
  { label: "What Changed", href: null },
  { label: "Portfolio", href: null },
] as const;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <header className="border-b border-hairline bg-surface">
          <nav className="mx-auto flex max-w-[1100px] flex-wrap items-baseline gap-x-6 gap-y-1 px-6 py-3">
            {NAV.map(({ label, href }) =>
              href ? (
                <a key={label} href={href} className="text-[13.5px] font-semibold">
                  {label}
                </a>
              ) : (
                <span
                  key={label}
                  className="text-[13.5px] text-ink-3"
                  title="not built yet"
                >
                  {label}
                </span>
              )
            )}
          </nav>
        </header>
        {children}
      </body>
    </html>
  );
}
