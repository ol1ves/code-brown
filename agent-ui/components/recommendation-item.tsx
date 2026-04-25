"use client"

import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import { displayName } from "@/lib/distribution"
import type { RankedItem } from "@/lib/agent-state"

interface RecommendationItemProps {
  item: RankedItem
  rank: number
  isHighlighted?: boolean
  isSelected?: boolean
  highlightReason?: string
  onSelect?: () => void
}

export function RecommendationItem({
  item,
  rank,
  isHighlighted,
  isSelected,
  highlightReason,
  onSelect,
}: RecommendationItemProps) {
  const { item: rec, score, foundAcrossQueries } = item
  const imageUrl = rec.live_listing.image_urls?.[0]
  const title = displayName(rec.live_listing)

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "group w-full text-left flex items-start gap-3 p-3 rounded-lg transition-colors",
        isSelected
          ? "bg-primary/10 border border-primary/30"
          : isHighlighted
          ? "bg-primary/5 border border-primary/20"
          : "hover:bg-secondary/50"
      )}
    >
      <div
        className={cn(
          "flex items-center justify-center w-6 h-6 rounded text-xs font-bold shrink-0",
          rank <= 3 ? "bg-primary text-primary-foreground" : "bg-secondary text-muted-foreground"
        )}
      >
        {rank}
      </div>

      {imageUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={imageUrl}
          alt={title}
          className="w-14 h-14 rounded object-cover shrink-0 bg-secondary"
          loading="lazy"
          onError={(e) => {
            ;(e.currentTarget as HTMLImageElement).style.visibility = "hidden"
          }}
        />
      ) : (
        <div className="w-14 h-14 rounded bg-secondary shrink-0" />
      )}

      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="font-medium text-sm truncate">{title}</p>
            {highlightReason && (
              <p className="text-xs text-primary mt-0.5">{highlightReason}</p>
            )}
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <Badge variant="secondary" className="text-xs">
              {foundAcrossQueries} {foundAcrossQueries === 1 ? "query" : "queries"}
            </Badge>
          </div>
        </div>

        <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
          <span>
            Score:{" "}
            <span
              className={cn(
                "font-medium",
                score > 0 ? "text-primary" : score < 0 ? "text-destructive" : "text-foreground"
              )}
            >
              {score.toFixed(2)}
            </span>
          </span>
          <span>
            Edge: <span className="text-foreground">${Number(rec.edge_usd || 0).toFixed(0)}</span>
          </span>
          <span>
            P(Sell):{" "}
            <span className="text-foreground">{(Number(rec.p_sell || 0) * 100).toFixed(0)}%</span>
          </span>
        </div>
      </div>
    </button>
  )
}
