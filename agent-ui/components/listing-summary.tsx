"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { DistributionCurve } from "@/components/distribution-curve"
import { ThinkingDisplay } from "@/components/thinking-display"
import { derivePercentiles, displayName } from "@/lib/distribution"
import type { RankedItem } from "@/lib/agent-state"

interface ListingSummaryProps {
  selected: RankedItem | null
  summaryText: string
  summaryThinking: string
  highlights: Array<{ item_id: string; why: string }>
  rankedItems: RankedItem[]
}

function highlightTitle(highlight: { item_id: string; why: string }, rankedItems: RankedItem[]): string {
  const match = rankedItems.find((r) => r.item.live_listing.id === highlight.item_id)
  return match ? displayName(match.item.live_listing) : "Unknown listing"
}

export function ListingSummary({
  selected,
  summaryText,
  summaryThinking,
  highlights,
  rankedItems,
}: ListingSummaryProps) {
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm uppercase tracking-wider text-primary font-medium">
            Distribution
          </CardTitle>
        </CardHeader>
        <CardContent>
          {selected ? (
            <>
              <p className="text-sm font-medium mb-1">{displayName(selected.item.live_listing)}</p>
              <DistributionCurve
                price={Number(selected.item.cost ?? 0)}
                percentiles={derivePercentiles(selected.item)}
              />
            </>
          ) : (
            <p className="text-sm text-muted-foreground italic">Select a recommendation to see its price distribution</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm uppercase tracking-wider text-primary font-medium">
            Summary
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <ThinkingDisplay
            label="Summary Thinking"
            content={summaryThinking}
            defaultExpanded={false}
          />
          {summaryText ? (
            <p className="text-sm leading-relaxed">{summaryText}</p>
          ) : (
            <p className="text-sm text-muted-foreground italic">
              Summary will appear after analysis completes
            </p>
          )}
          {highlights.length > 0 && (
            <div>
              <h4 className="text-sm font-medium mb-2">Key Highlights</h4>
              <ul className="space-y-2">
                {highlights.map((h, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <svg className="h-4 w-4 text-primary shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                      <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                    </svg>
                    <span>
                      <span className="font-medium">{highlightTitle(h, rankedItems)}</span>
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
  )
}
