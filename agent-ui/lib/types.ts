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
  live_listing: { id: string; name?: string; designer?: string; url?: string; image_urls?: string[] }
  [key: string]: unknown
}

export interface CandidateQuery {
  query: string
  why: string
}

export interface HypeProbeResult {
  query: string
  score: number | null
  confidence: "high" | "medium" | "low" | "insufficient"
  momentum_pct: number
  related: Array<{ query: string; value: number; kind: "rising" | "top"; is_breakout: boolean }>
}

export type AgentEvent = {
  type: AgentEventType
  [key: string]: unknown
}
