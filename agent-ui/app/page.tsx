"use client"

import { useMemo, useState } from "react"
import { initialState, rankedList, reduceAgentEvent } from "@/lib/agent-state"
import { streamAgentRun } from "@/lib/agent-stream"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { PhaseIndicator } from "@/components/phase-indicator"
import { CandidateCard } from "@/components/candidate-card"
import { RecommendationItem } from "@/components/recommendation-item"
import { QueryStatusList } from "@/components/query-status-list"
import { ThinkingDisplay } from "@/components/thinking-display"

export default function Page() {
  const [intentText, setIntentText] = useState("")
  const [state, setState] = useState(initialState)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  const items = useMemo(() => rankedList(state), [state])
  const highlightMap = useMemo(() => {
    const map: Record<string, string> = {}
    for (const h of state.highlights) {
      map[h.item_id] = h.why
    }
    return map
  }, [state.highlights])

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
      setError(e instanceof Error ? e.message : "Stream failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-2xl font-serif italic text-primary tracking-wide">Groogle</h1>
              <p className="text-sm text-muted-foreground">AI-powered item discovery and analysis</p>
            </div>
            <PhaseIndicator currentPhase={state.phase} />
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Search Input */}
        <Card className="mb-6">
          <CardContent className="p-4">
            <form
              onSubmit={(e) => {
                e.preventDefault()
                onRun()
              }}
              className="flex gap-3"
            >
              <Input
                value={intentText}
                onChange={(e) => setIntentText(e.target.value)}
                placeholder="Find me underpriced archive 2000s pieces..."
                className="flex-1"
                disabled={busy}
              />
              <Button type="submit" disabled={busy || !intentText.trim()} className="uppercase tracking-wider font-medium">
                {busy ? (
                  <>
                    <Spinner className="mr-2 h-4 w-4" />
                    Searching...
                  </>
                ) : (
                  "Search"
                )}
              </Button>
            </form>
            {error && (
              <p className="mt-3 text-sm text-destructive">{error}</p>
            )}
          </CardContent>
        </Card>

        {/* Main Grid */}
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Left Column */}
          <div className="space-y-6">
            {/* Intent & Candidates */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm uppercase tracking-wider text-primary font-medium">
                  Intent Analysis
                </CardTitle>
              </CardHeader>
              <CardContent>
                {state.intentReasoning ? (
                  <p className="text-sm text-muted-foreground mb-4">{state.intentReasoning}</p>
                ) : (
                  <p className="text-sm text-muted-foreground italic mb-4">Waiting for intent analysis...</p>
                )}

                <h4 className="text-xs uppercase tracking-wider text-primary font-medium mb-3">
                  Candidate Queries
                </h4>
                
                {state.candidates.length > 0 ? (
                  <div className="grid gap-3 sm:grid-cols-2">
                    {state.candidates.map((c) => (
                      <CandidateCard
                        key={c.query}
                        candidate={c}
                        status={state.hypeStatus[c.query] ?? "pending"}
                        probe={state.hypeResults[c.query]}
                      />
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground italic">No candidates generated yet</p>
                )}
              </CardContent>
            </Card>

            {/* Plan & Search Status */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm uppercase tracking-wider text-primary font-medium">
                  Plan & Search
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <ThinkingDisplay
                  label="Planner Thinking"
                  content={state.planThinking}
                  defaultExpanded={false}
                />

                {state.plan && (
                  <div>
                    <h4 className="text-sm font-medium mb-2">Execution Plan</h4>
                    <pre className="text-xs bg-muted/50 p-3 rounded-lg overflow-auto max-h-40 text-muted-foreground">
                      {JSON.stringify(state.plan, null, 2)}
                    </pre>
                  </div>
                )}

                <div>
                  <h4 className="text-sm font-medium mb-2">Search Progress</h4>
                  <QueryStatusList queryStatus={state.queryStatus} />
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Right Column */}
          <div className="space-y-6">
            {/* Recommendations */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm uppercase tracking-wider text-primary font-medium flex items-center justify-between">
                  Recommendations
                  {items.length > 0 && (
                    <span className="text-xs font-normal text-muted-foreground normal-case">
                      {items.length} items found
                    </span>
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent>
                {items.length > 0 ? (
                  <div className="space-y-1 max-h-[400px] overflow-y-auto -mx-2 px-2">
                    {items.map((item, index) => (
                      <RecommendationItem
                        key={item.item.live_listing.id}
                        item={item}
                        rank={index + 1}
                        isHighlighted={!!highlightMap[item.item.live_listing.id]}
                        highlightReason={highlightMap[item.item.live_listing.id]}
                      />
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground italic">
                    {state.phase === "idle" ? "Run the agent to see recommendations" : "Searching for items..."}
                  </p>
                )}
              </CardContent>
            </Card>

            {/* Summary */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm uppercase tracking-wider text-primary font-medium">
                  Summary
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <ThinkingDisplay
                  label="Summary Thinking"
                  content={state.summaryThinking}
                  defaultExpanded={false}
                />

                {state.summaryText ? (
                  <p className="text-sm leading-relaxed">{state.summaryText}</p>
                ) : (
                  <p className="text-sm text-muted-foreground italic">
                    Summary will appear after analysis completes
                  </p>
                )}

                {state.highlights.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium mb-2">Key Highlights</h4>
                    <ul className="space-y-2">
                      {state.highlights.map((h) => (
                        <li key={h.item_id} className="flex items-start gap-2 text-sm">
                          <svg className="h-4 w-4 text-primary shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                            <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                          </svg>
                          <span>
                            <span className="font-medium">{h.item_id}</span>
                            <span className="text-muted-foreground"> - {h.why}</span>
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </main>
  )
}
