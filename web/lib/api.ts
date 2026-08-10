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
};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json();
}

export const getBoard = () => get<Board>("/board");
export const getStock = (symbol: string) =>
  get<Stock>(`/stocks/${encodeURIComponent(symbol)}`);

// Tier thresholds on the 10-point display scale (pipeline/tiers.py is the
// source of truth in 0–1; these are those cutoffs ×10 for drawing bands).
export const BANDS = { STRONG_BUY: 4.6, BUY: 3.6, WATCH: 3.4, EXIT: 3.2 };
