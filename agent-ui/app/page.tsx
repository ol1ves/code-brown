"use client"

import { useEffect, useMemo, useState } from "react"
import { initialState, rankedList, reduceAgentEvent } from "@/lib/agent-state"
import { streamAgentRun } from "@/lib/agent-stream"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { PhaseIndicator } from "@/components/phase-indicator"
import { RecommendationItem } from "@/components/recommendation-item"
import { TrendStage } from "@/components/trend-stage"
import { TrendRail } from "@/components/trend-rail"
import { ListingSummary } from "@/components/listing-summary"

export default function Page() {
  const [intentText, setIntentText] = useState("")
  const [state, setState] = useState(initialState)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [selectedListingId, setSelectedListingId] = useState<string | null>(null)

  const items = useMemo(() => rankedList(state), [state])

  const highlightMap = useMemo(() => {
    const map: Record<string, string> = {}
    for (const h of state.highlights) map[h.item_id] = h.why
    return map
  }, [state.highlights])

  const showRecsLayout = items.length > 0

  useEffect(() => {
    if (!showRecsLayout) {
      setSelectedListingId(null)
      return
    }
    if (!selectedListingId || !items.find((i) => i.item.live_listing.id === selectedListingId)) {
      setSelectedListingId(items[0].item.live_listing.id)
    }
  }, [items, showRecsLayout, selectedListingId])

  const selected = useMemo(
    () => items.find((i) => i.item.live_listing.id === selectedListingId) ?? null,
    [items, selectedListingId]
  )

  async function onRun() {
    if (!intentText.trim()) return
    setBusy(true)
    setError("")
    setState(initialState)
    setSelectedListingId(null)
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
      <header className="border-b border-border bg-card/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-[1600px] mx-auto px-4 py-4">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-2xl font-serif italic text-primary tracking-wide">Groogle</h1>
              <p className="text-sm text-muted-foreground">AI-powered item discovery and analysis</p>
            </div>
            <PhaseIndicator currentPhase={state.phase} />
          </div>
        </div>
      </header>

      <div className="max-w-[1600px] mx-auto px-4 py-6">
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
              <Button
                type="submit"
                disabled={busy || !intentText.trim()}
                className="uppercase tracking-wider font-medium"
              >
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
            {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
          </CardContent>
        </Card>

        {showRecsLayout ? (
          <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)_400px]">
            <aside className="space-y-6">
              <TrendRail candidates={state.candidates} hypeResults={state.hypeResults} />
            </aside>

            <section>
              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h2 className="text-sm uppercase tracking-wider text-primary font-medium">
                      Recommendations
                    </h2>
                    <span className="text-xs text-muted-foreground">{items.length} items</span>
                  </div>
                  <div className="space-y-1 max-h-[70vh] overflow-y-auto -mx-2 px-2">
                    {items.map((item, index) => {
                      const id = item.item.live_listing.id
                      return (
                        <RecommendationItem
                          key={id}
                          item={item}
                          rank={index + 1}
                          isHighlighted={!!highlightMap[id]}
                          isSelected={selectedListingId === id}
                          highlightReason={highlightMap[id]}
                          onSelect={() => setSelectedListingId(id)}
                        />
                      )
                    })}
                  </div>
                </CardContent>
              </Card>
            </section>

            <aside>
              <ListingSummary
                selected={selected}
                summaryText={state.summaryText}
                summaryThinking={state.summaryThinking}
                highlights={state.highlights}
                rankedItems={items}
              />
            </aside>
          </div>
        ) : (
          <TrendStage
            candidates={state.candidates}
            hypeStatus={state.hypeStatus}
            hypeResults={state.hypeResults}
            intentReasoning={state.intentReasoning}
          />
        )}
      </div>
    </main>
  )
}
