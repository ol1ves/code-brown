export type AgentEventType =
  | "intent_parsed"
  | "candidates_generated"
  | "hype_started"
  | "hype_done"
  | "plan_thinking"
  | "plan"
  | "query_started"
  | "query_done"
  | "summary_thinking"
  | "summary"
  | "done"
  | "error"

export interface Recommendation {
  item_id: string
  edge_usd: number
  p_sell: number
  q50?: number
  cost?: number
  confidence?: "high" | "medium" | "low" | "insufficient" | "no_data"
  valuation?: {
    dist?: { q10: number; q50: number; q90: number }
    [key: string]: unknown
  }
  live_listing: {
    id: string
    name?: string
    designer?: string
    url?: string
    image_urls?: string[]
  }
  [key: string]: unknown
}

export interface CandidateQuery {
  query: string
  why: string
  hype_term?: string
}

export interface TrendPoint {
  day_unix: number
  intensity: number
}

export interface TrendSeries {
  range: "7d" | "30d" | "90d"
  points: TrendPoint[]
}

export interface HypeProbeResult {
  query: string
  hype_term?: string
  score: number | null
  confidence: "high" | "medium" | "low" | "insufficient"
  momentum_pct: number
  related: Array<{ query: string; value: number; kind: "rising" | "top"; is_breakout: boolean }>
  series_30d?: TrendSeries | null
  series_7d?: TrendSeries | null
  series_90d?: TrendSeries | null
}

export type AgentEvent = {
  type: AgentEventType
  [key: string]: unknown
}
