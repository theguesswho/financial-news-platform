// `/` IS The Board (addendum #3, 2026-08-15 — the front-door reversal
// landing for real). The page itself lives in ./home/page.tsx; this
// re-export keeps one implementation serving both URLs until /home is
// retired in the promote step.

export { default, metadata } from "./home/page";
