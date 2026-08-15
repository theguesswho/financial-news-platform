// Read layer client — server-side fetches against the api/ service.
// Scores arrive on the 10-point display scale (API boundary rule);
// priced_in and ng_score are 0–1 fractions.

const BASE = process.env.API_URL ?? "https://api-production-e885.up.railway.app";

export type Components = {
  exposure: number | null;
  value: number | null;
  quality: number | null;
  gap: number | null;
};

export type BoardEntry = {
  symbol: string;
  company: string | null;
  score: number;
  score_raw: number;
  tier: "Strong Buy" | "Buy" | "Watch" | null;
  components: Components;
  assessed: boolean;
  direction: string;
  rationale: string | null;
  key_bull: string | null;
  key_bear: string | null;
  qual_promoted: boolean;
  disagreement: { kind: "raised" | "restrained"; quant_tier: string } | null;
  exit_grace: boolean;
  rank: number | null;
  is_new: boolean;
  tier_move: { direction: "up" | "down"; from: string; to: string } | null;
  rank_change: number | null;
};

export type Board = {
  date: string;
  counts: {
    strong_buy: number;
    buy: number;
    watch: number;
    assessed: number;
    new: number;
    universe: number;
  };
  board: BoardEntry[];
  off_board: BoardEntry[];
};

export type HistoryPoint = {
  date: string;
  score: number | null;
  components: Components;
  tier: string | null;
  final_rank: number | null;
};

export type AnnualRow = {
  period_end: string;
  revenue: number | null;
  gross_margin: number | null;
  op_margin: number | null;
  net_margin: number | null;
  fcf: number | null;
  roic: number | null;
};

export type ValuationGap = {
  /** The force whose exposed companies form this peer set. (The DB column
   * is still called meta_theme_id — a legacy name holding a narrative_id;
   * the API renames it at the boundary.) */
  narrative_id: number | null;
  theme: string;
  alignment: number | null;
  peer_count: number | null;
  pe_forward: number | null;
  peer_median_pe: number | null;
  pe_discount: number | null;
  ev_ebitda: number | null;
  peer_median_ev: number | null;
  ev_discount: number | null;
};

export type EarningsCall = {
  date: string;
  narrative_strength: number | null;
  trajectory: string | null;
  management_tone: string | null;
  themes: string[];
  catalysts: string[];
  risks: string[];
};

export type Filing = EarningsCall & { type: string; url: string | null };

export type FilingEvent = { date: string; type: string; title: string | null };

export type Claim = {
  type: string;
  text: string;
  confidence: number | null;
  call_date: string;
  direction: string | null;
};

export type InsiderTrade = {
  person: string;
  title: string | null;
  date: string;
  type: string;
  shares: number | null;
  avg_price: number | null;
  total_value: number | null;
};

export type Stock = {
  symbol: string;
  company: string | null;
  sector: string | null;
  industry: string | null;
  as_of: string;
  score: number;
  tier: string | null;
  quant_tier: string | null;
  final_rank: number | null;
  components: Components;
  priced_in: number | null;
  ng_score: number | null;
  assessment: {
    score_at_assessment: number | null;
    raw_tier: string | null;
    adjusted_tier: string | null;
    direction: string | null;
    rationale: string | null;
    key_bull: string | null;
    key_bear: string | null;
    assessed_at: string | null;
  } | null;
  fundamentals: Record<string, number | string | null> | null;
  annual_history: AnnualRow[];
  history: HistoryPoint[];
  valuation_gaps: ValuationGap[];
  prices: { date: string; close: number | null }[];
  earnings_calls: EarningsCall[];
  filings: Filing[];
  filing_events: FilingEvent[];
  claims: Claim[];
  insider_trades: InsiderTrade[];
  /** The narrative brain's own links, keyed by narrative_id — this is how
   * a company is paired to a force. `theme_alignments` below is the LEGACY
   * meta-themes system (frozen 2026-07-12, retiring); never pair the two
   * systems by matching their names. */
  exposures: Exposure[];
  theme_alignments: { theme: string; alignment: number | null; trajectory: string | null }[];
};

export type Exposure = {
  narrative_id: number;
  name: string;
  level: string;
  scope: string;
  parent: { id: number; name: string } | null;
  exposure: number | null;
  /** beneficiary / adapting / threatened — a threatened link must never be
   * drawn as if it were a tailwind. */
  direction: string | null;
  linkage: string | null;
  status: string | null;
  misses: number | null;
  decays: number | null;
  first_seen: string | null;
  last_confirmed: string | null;
};

export type EditionStory = {
  section?: string;
  kind: string;
  symbol: string | null;
  headline: string;
  body?: string;
};

export type Report = {
  date: string;
  dates?: string[];
  masthead: {
    board: number;
    changes: number;
    us_pct: number | null;
    spy_pct: number | null;
    positions: number;
    closed: number;
    since: string | null;
    changes_breakdown: string | null;
    leaders: { symbol: string; score: number; tier: string }[];
  };
  top_story: EditionStory | null;
  sections: EditionStory[];
};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json();
}

export type Force = {
  id: number;
  name: string;
  thesis: string | null;
  momentum: string;
  board_weight: number;
  companies: number;
  board_companies: number;
  top_stocks: { symbol: string; tier: string | null; score: number | null }[];
};

export type EmergingNarrative = {
  id: number;
  name: string;
  maturity: "emerging" | "candidate";
  parent: string | null;
  age_days: number | null;
  companies: number;
  adds_30d: number;
};

export type WeakeningNarrative = {
  id: number;
  name: string;
  level: string;
  status: string;
  strengthened_30d: number;
  weakened_30d: number;
  removed_30d: number;
  misses: number;
  net_30d: number;
  companies: number;
};

export type NarrativesLanding = {
  forces: Force[];
  emerging: EmergingNarrative[];
  weakening: WeakeningNarrative[];
};

export const getBoard = () => get<Board>("/board");
export const getNarrativesLanding = () =>
  get<NarrativesLanding>("/narratives/landing");
export const getReportLatest = () => get<Report>("/reports/latest");
export const getReport = (date: string) => get<Report>(`/reports/${date}`);

export type ScorecardLot = {
  lot_date: string;
  symbol: string;
  is_entry: boolean;
  invested: number;
  stock_value: number;
  spy_value: number;
  vs_spy_pct: number;
  beat: boolean;
  closed: boolean;
  exit_date: string | null;
};

export type Scorecard = {
  lots: ScorecardLot[];
  total_invested: number;
  portfolio_value: number;
  spy_value: number;
  portfolio_return_pct: number;
  spy_return_pct: number;
  lots_beating_spy: number;
  n_lots: number;
  open_lots: number;
  closed_lots: number;
};

export const getScorecard = () => get<Scorecard>("/board/scorecard");

/** One clock (addendum #2): the product's since-date is the first lot in
 * the scorecard — never masthead.since. */
export const firstLotDate = (sc: Scorecard) =>
  sc.lots.reduce(
    (min, l) => (l.lot_date < min ? l.lot_date : min),
    sc.lots[0]?.lot_date ?? ""
  );

/** Open lots per symbol, from the scorecard — the book of record. */
export function openLotCounts(sc: Scorecard): Record<string, number> {
  const m: Record<string, number> = {};
  for (const l of sc.lots) if (!l.closed) m[l.symbol] = (m[l.symbol] ?? 0) + 1;
  return m;
}

/** Never contradict the book (addendum #4, user decision 2026-08-15):
 * if the book holds open lots in a name, an edition sentence claiming we
 * hold nothing is replaced with the open-lot fact. Applies to every
 * symbol, every edition — no special-casing. */
const NO_POSITION_CLAIM =
  /[^.!?]*\b(?:we\s+(?:do\s*not|don'?t)\s+(?:hold|own|have)|(?:holds?|holding|have|has)\s+no\s+position|no\s+position\s+(?:is\s+)?held|not\s+a\s+(?:current\s+)?(?:position|holding))\b[^.!?]*[.!?]\s*/i;

export function reconcileWithBook(text: string, openLots: number): string {
  if (openLots <= 0 || !NO_POSITION_CLAIM.test(text)) return text;
  const fact = `The book holds ${openLots} open $100 lot${openLots === 1 ? "" : "s"} in this name. `;
  return text.replace(NO_POSITION_CLAIM, fact).trim();
}

export type RosterRow = {
  symbol: string;
  company: string | null;
  exposure: number | null;
  /** direction of the company's strongest link to this force: beneficiary /
   * adapting / threatened. A force can be a headwind. */
  direction: string | null;
  tier: string | null;
  score: number | null;
};

export type ForceRoster = {
  id: number;
  name: string;
  level: string;
  thesis: string | null;
  status: string;
  covered: number;
  on_board: RosterRow[];
  off_board: RosterRow[];
  off_board_total: number;
};

export const getForceRoster = (id: number | string) =>
  get<ForceRoster>(`/narratives/${id}/roster`);

/** One week of a force's vital signs. `seeding` marks the ledger-backfill
 * weeks (before 3 Aug 2026) — the instrument opening its eyes, not the
 * world changing; any surface drawing them must say so. There is no
 * momentum word here on purpose: that column is still in shadow. */
export type HealthWeek = {
  week_start: string;
  support: number;
  erosion: number;
  breadth: number;
  active_exposures: number | null;
  board_weight: number | null;
  checkpoint_passes: number;
  checkpoint_fails: number;
  translation_share: number | null;
  seeding: boolean;
};

export type Narrative = {
  id: number;
  name: string;
  level: string;
  thesis: string | null;
  status: string;
  momentum: string;
  falsification: string | null;
  parent: { id: number; name: string } | null;
  children: { id: number; name: string; level: string; covered: number; on_board: number }[];
  board_weight: number;
  roster: {
    covered: number;
    on_board: RosterRow[];
    off_board: RosterRow[];
    off_board_total: number;
  };
  health: {
    weeks: HealthWeek[];
    observed_weeks: number;
    first_observed_week: string | null;
  };
};

export const getNarrative = (id: number | string) =>
  get<Narrative>(`/narratives/${id}`);

/** Mention-set rule (PRODUCT_UI_HANDOFF): a gap with peer_count >= 100 is
 * a mention set, not a same-story beneficiary set. */
export const isMentionSet = (g: ValuationGap) => (g.peer_count ?? 0) >= 100;

/** The company hero's value peer set: the gap with the SMALLEST peer
 * count that still has both forward P/E figures. */
export function heroGap(gaps: ValuationGap[]): ValuationGap | null {
  const usable = gaps.filter(
    (g) => g.pe_forward != null && g.peer_median_pe != null && g.peer_count
  );
  usable.sort((a, b) => (a.peer_count ?? 1e9) - (b.peer_count ?? 1e9));
  return usable[0] ?? null;
}
export const getStock = (symbol: string) =>
  get<Stock>(`/stocks/${encodeURIComponent(symbol)}`);

// Tier thresholds on the 10-point display scale (pipeline/tiers.py is the
// source of truth in 0–1; these are those cutoffs ×10 for drawing bands).
export const BANDS = { STRONG_BUY: 4.6, BUY: 3.6, WATCH: 3.4, EXIT: 3.2 };
