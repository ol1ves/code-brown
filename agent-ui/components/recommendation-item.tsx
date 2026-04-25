"use client"

import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import type { RankedItem } from "@/lib/agent-state"

interface RecommendationItemProps {
  item: RankedItem
  rank: number
  isHighlighted?: boolean
  highlightReason?: string
}

export function RecommendationItem({ item, rank, isHighlighted, highlightReason }: RecommendationItemProps) {
  const { item: rec, score, foundAcrossQueries } = item

  return (
    <div
      className={cn(
        "group flex items-start gap-3 p-3 rounded-lg transition-colors",
        isHighlighted ? "bg-primary/5 border border-primary/20" : "hover:bg-secondary/50"
      )}
    >
      <div className={cn(
        "flex items-center justify-center w-6 h-6 rounded text-xs font-bold shrink-0",
        rank <= 3 ? "bg-primary text-primary-foreground" : "bg-secondary text-muted-foreground"
      )}>
        {rank}
      </div>
      
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="font-medium text-sm truncate">
              {rec.live_listing.designer && (
                <span className="text-muted-foreground">{rec.live_listing.designer}</span>
              )}
              {rec.live_listing.designer && rec.live_listing.name && " - "}
              {rec.live_listing.name || rec.live_listing.id}
            </p>
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
            Score: <span className={cn(
              "font-medium",
              score > 0 ? "text-primary" : score < 0 ? "text-destructive" : "text-foreground"
            )}>
              {score.toFixed(2)}
            </span>
          </span>
          <span>
            Edge: <span className="text-foreground">${Number(rec.edge_usd || 0).toFixed(0)}</span>
          </span>
          <span>
            P(Sell): <span className="text-foreground">{(Number(rec.p_sell || 0) * 100).toFixed(0)}%</span>
          </span>
        </div>
      </div>

      {rec.live_listing.url && (
        <a
          href={rec.live_listing.url}
          target="_blank"
          rel="noopener noreferrer"
          className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-foreground"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
          </svg>
        </a>
      )}
    </div>
  )
}
