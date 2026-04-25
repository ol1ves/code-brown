import type { AgentEvent, CandidateQuery, HypeProbeResult, Recommendation } from "./types"

export type Phase =
  | "idle"
  | "intent"
  | "probing"
  | "planning"
  | "querying"
  | "summarizing"
  | "done"
  | "error"

export interface RankedItem {
  item: Recommendation
  score: number
  foundAcrossQueries: number
}

export interface AgentUiState {
  phase: Phase
  intentReasoning: string
  planThinking: string
  summaryThinking: string
  plan: Record<string, unknown> | null
  candidates: CandidateQuery[]
  hypeStatus: Record<string, "pending" | "probing" | "done" | "error">
  hypeResults: Record<string, HypeProbeResult>
  summaryText: string
  highlights: Array<{ item_id: string; why: string }>
  queryStatus: Record<string, "searching" | "done" | "error">
  ranked: Record<string, RankedItem>
}

export const initialState: AgentUiState = {
  phase: "idle",
  intentReasoning: "",
  planThinking: "",
  summaryThinking: "",
  plan: null,
  candidates: [],
  hypeStatus: {},
  hypeResults: {},
  summaryText: "",
  highlights: [],
  queryStatus: {},
  ranked: {},
}

function scoreOf(item: Recommendation): number {
  return Number(item.edge_usd || 0) * Number(item.p_sell || 0)
}

export function reduceAgentEvent(state: AgentUiState, event: AgentEvent): AgentUiState {
  if (event.type === "intent_parsed") {
    const candidates = Array.isArray(event.candidates) ? (event.candidates as CandidateQuery[]) : []
    const hypeStatus: AgentUiState["hypeStatus"] = {}
    for (const c of candidates) hypeStatus[c.query] = "pending"
    return { ...state, phase: "intent", intentReasoning: String(event.reasoning ?? ""), candidates, hypeStatus }
  }
  if (event.type === "candidates_generated") {
    const candidates = Array.isArray(event.candidates) ? (event.candidates as CandidateQuery[]) : state.candidates
    const hypeStatus: AgentUiState["hypeStatus"] = { ...state.hypeStatus }
    for (const c of candidates) if (!hypeStatus[c.query]) hypeStatus[c.query] = "pending"
    return { ...state, phase: "probing", candidates, hypeStatus }
  }
  if (event.type === "hype_started") {
    const query = String(event.query ?? "")
    return { ...state, phase: "probing", hypeStatus: { ...state.hypeStatus, [query]: "probing" } }
  }
  if (event.type === "hype_done") {
    const probe = event as unknown as HypeProbeResult
    const query = String(probe.query ?? "")
    return {
      ...state,
      phase: "probing",
      hypeStatus: { ...state.hypeStatus, [query]: "done" },
      hypeResults: { ...state.hypeResults, [query]: probe },
    }
  }
  if (event.type === "plan_thinking") {
    return { ...state, phase: "planning", planThinking: `${state.planThinking}${String(event.delta ?? "")}` }
  }
  if (event.type === "plan") {
    return { ...state, phase: "querying", plan: event as Record<string, unknown> }
  }
  if (event.type === "query_started") {
    const query = String(event.query ?? "")
    return { ...state, phase: "querying", queryStatus: { ...state.queryStatus, [query]: "searching" } }
  }
  if (event.type === "query_done") {
    const query = String(event.query ?? "")
    const nextRanked = { ...state.ranked }
    const items = Array.isArray(event.items) ? (event.items as Recommendation[]) : []
    for (const item of items) {
      const listingId = item?.live_listing?.id
      if (!listingId) continue
      const newScore = scoreOf(item)
      const prev = nextRanked[listingId]
      if (!prev) {
        nextRanked[listingId] = { item, score: newScore, foundAcrossQueries: 1 }
      } else {
        nextRanked[listingId] = {
          item: newScore > prev.score ? item : prev.item,
          score: Math.max(newScore, prev.score),
          foundAcrossQueries: prev.foundAcrossQueries + 1,
        }
      }
    }
    return { ...state, phase: "querying", ranked: nextRanked, queryStatus: { ...state.queryStatus, [query]: "done" } }
  }
  if (event.type === "summary_thinking") {
    return {
      ...state,
      phase: "summarizing",
      summaryThinking: `${state.summaryThinking}${String(event.delta ?? "")}`,
    }
  }
  if (event.type === "summary") {
    return {
      ...state,
      phase: "summarizing",
      summaryText: String(event.text ?? ""),
      highlights: Array.isArray(event.highlights)
        ? (event.highlights as Array<{ item_id: string; why: string }>)
        : [],
    }
  }
  if (event.type === "error") {
    const stage = String(event.stage ?? "")
    if (stage === "search") {
      const query = String(event.query ?? "")
      return { ...state, queryStatus: { ...state.queryStatus, [query]: "error" } }
    }
    if (stage === "hype") {
      const query = String(event.query ?? "")
      if (query) return { ...state, hypeStatus: { ...state.hypeStatus, [query]: "error" } }
      return { ...state }
    }
    return { ...state, phase: "error" }
  }
  if (event.type === "done") {
    return { ...state, phase: "done" }
  }
  return state
}

export function rankedList(state: AgentUiState): RankedItem[] {
  return Object.values(state.ranked).sort((a, b) => b.score - a.score)
}
