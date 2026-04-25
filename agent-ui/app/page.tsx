"use client"

import { useMemo, useState } from "react"
import { initialState, rankedList, reduceAgentEvent } from "../lib/agent-state"
import { streamAgentRun } from "../lib/agent-stream"

export default function Page() {
  const [intentText, setIntentText] = useState("")
  const [state, setState] = useState(initialState)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  const items = useMemo(() => rankedList(state), [state])

  async function onRun() {
    if (!intentText.trim()) return
    setBusy(true)
    setError("")
    setState(initialState)
    try {
      await streamAgentRun(intentText, (event) => {
        setState((prev) => reduceAgentEvent(prev, event))
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : "stream failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <main style={{ padding: 20, maxWidth: 1300, margin: "0 auto" }}>
      <h1 style={{ marginBottom: 8 }}>Agent Run Dashboard</h1>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <input
          style={{ flex: 1, padding: 8 }}
          value={intentText}
          onChange={(e) => setIntentText(e.target.value)}
          placeholder="find me underpriced archive 2000s pieces"
        />
        <button disabled={busy} onClick={onRun}>
          {busy ? "Running..." : "Run"}
        </button>
      </div>

      {error ? <p style={{ color: "#ff6b6b" }}>{error}</p> : null}
      <p style={{ opacity: 0.8 }}>Phase: {state.phase}</p>

      <section style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div style={{ background: "#121a2b", padding: 12, borderRadius: 10 }}>
          <h3>1) Intent</h3>
          <p>{state.intentReasoning}</p>
          <h4>2) Candidates + Hype Probes</h4>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {state.candidates.map((c) => {
              const probe = state.hypeResults[c.query]
              const status = state.hypeStatus[c.query] ?? "pending"
              return (
                <div key={c.query} style={{ border: "1px solid #28344f", borderRadius: 8, padding: 8 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                    <strong>{c.query}</strong>
                    <span>{status}</span>
                  </div>
                  <small>{c.why}</small>
                  {probe ? (
                    <div style={{ marginTop: 4, fontSize: 12 }}>
                      score {probe.score ?? 0} | {probe.confidence} | mom {probe.momentum_pct}
                    </div>
                  ) : null}
                </div>
              )
            })}
          </div>
        </div>
        <div style={{ background: "#121a2b", padding: 12, borderRadius: 10 }}>
          <h3>3) Plan + Search Status</h3>
          <pre style={{ whiteSpace: "pre-wrap", maxHeight: 220, overflow: "auto" }}>{JSON.stringify(state.plan, null, 2)}</pre>
          <ul>
            {Object.entries(state.queryStatus).map(([query, status]) => (
              <li key={query} style={{ marginBottom: 4 }}>
                {query}: {status}
              </li>
            ))}
          </ul>
          <h4>Planner Thinking</h4>
          <p style={{ whiteSpace: "pre-wrap" }}>{state.planThinking}</p>
        </div>
      </section>

      <section style={{ marginTop: 16, display: "grid", gridTemplateColumns: "1.2fr .8fr", gap: 16 }}>
        <div style={{ background: "#121a2b", padding: 12, borderRadius: 10 }}>
          <h3>4) Recommendations</h3>
          <ul>
            {items.map(({ item, score, foundAcrossQueries }) => (
              <li key={item.live_listing.id} style={{ marginBottom: 8 }}>
                {item.live_listing.designer} {item.live_listing.name} - score {score.toFixed(2)} - found across{" "}
                {foundAcrossQueries} queries
              </li>
            ))}
          </ul>
        </div>
        <div style={{ background: "#121a2b", padding: 12, borderRadius: 10 }}>
          <h3>5) Summary</h3>
          <h4>Summary Thinking</h4>
          <p style={{ whiteSpace: "pre-wrap" }}>{state.summaryThinking}</p>
          <p>{state.summaryText}</p>
          <ul>
            {state.highlights.map((h) => (
              <li key={h.item_id}>
                {h.item_id}: {h.why}
              </li>
            ))}
          </ul>
        </div>
      </section>
    </main>
  )
}
