import { describe, expect, it } from "vitest"
import { initialState, rankedList, reduceAgentEvent } from "./agent-state"

describe("reduceAgentEvent", () => {
  it("dedups by live_listing.id and keeps higher score", () => {
    let state = initialState
    state = reduceAgentEvent(state, {
      type: "query_done",
      query: "q1",
      items: [
        {
          item_id: "a",
          edge_usd: 100,
          p_sell: 0.5,
          live_listing: { id: "id-1", name: "A" },
        },
      ],
    })
    state = reduceAgentEvent(state, {
      type: "query_done",
      query: "q2",
      items: [
        {
          item_id: "b",
          edge_usd: 80,
          p_sell: 0.4,
          live_listing: { id: "id-1", name: "A2" },
        },
      ],
    })
    const ranked = rankedList(state)
    expect(ranked).toHaveLength(1)
    expect(ranked[0].item.item_id).toBe("a")
    expect(ranked[0].foundAcrossQueries).toBe(2)
  })

  it("sets done phase on done event", () => {
    const state = reduceAgentEvent(initialState, { type: "done" })
    expect(state.phase).toBe("done")
  })

  it("tracks candidates and hype probe lifecycle", () => {
    let state = reduceAgentEvent(initialState, {
      type: "intent_parsed",
      reasoning: "x",
      candidates: [{ query: "q1", why: "y" }],
    })
    expect(state.candidates).toHaveLength(1)
    expect(state.hypeStatus["q1"]).toBe("pending")
    state = reduceAgentEvent(state, { type: "hype_started", query: "q1" })
    expect(state.hypeStatus["q1"]).toBe("probing")
    state = reduceAgentEvent(state, {
      type: "hype_done",
      query: "q1",
      score: 12,
      confidence: "high",
      momentum_pct: 9,
      related: [],
    })
    expect(state.hypeStatus["q1"]).toBe("done")
  })
})
