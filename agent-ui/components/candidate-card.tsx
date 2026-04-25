"use client"

import { cn } from "@/lib/utils"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { TrendGraph } from "@/components/trend-graph"
import type { CandidateQuery, HypeProbeResult, TrendSeries } from "@/lib/types"

interface CandidateCardProps {
  candidate: CandidateQuery
  status: "pending" | "probing" | "done" | "error"
  probe?: HypeProbeResult
}

const confidenceColors: Record<string, string> = {
  high: "bg-primary/10 text-primary border-primary/20",
  medium: "bg-primary/5 text-primary/80 border-primary/15",
  low: "bg-muted text-muted-foreground border-border",
  insufficient: "bg-muted text-muted-foreground border-border",
}

function pickSeries(probe: HypeProbeResult): TrendSeries | null {
  const candidates = [probe.series_30d, probe.series_90d, probe.series_7d]
  for (const s of candidates) {
    if (s && s.points && s.points.length > 0) return s
  }
  return null
}

export function CandidateCard({ candidate, status, probe }: CandidateCardProps) {
  const series = probe ? pickSeries(probe) : null
  const scoreDisplay = probe?.score == null ? "—" : probe.score.toFixed(2)

  return (
    <Card className={cn(
      "transition-all",
      status === "probing" && "ring-1 ring-primary/50"
    )}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2 mb-2">
          <h4 className="font-medium text-sm leading-tight">{candidate.query}</h4>
          <StatusBadge status={status} />
        </div>
        {candidate.hype_term && candidate.hype_term !== candidate.query && (
          <p className="text-[10px] text-muted-foreground mb-2">
            Trend probe: <span className="text-foreground font-medium">{candidate.hype_term}</span>
          </p>
        )}
        <p className="text-xs text-muted-foreground mb-3">{candidate.why}</p>

        {probe && (
          <div className="space-y-2 pt-2 border-t border-border">
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant="outline" className={cn("text-xs", confidenceColors[probe.confidence])}>
                {probe.confidence}
              </Badge>
              <span className="text-xs text-muted-foreground">
                Score: <span className="text-foreground font-medium">{scoreDisplay}</span>
              </span>
              <span className="text-xs text-muted-foreground">
                Momentum: <span className={cn(
                  "font-medium",
                  probe.momentum_pct > 0 ? "text-primary" : probe.momentum_pct < 0 ? "text-destructive" : "text-foreground"
                )}>
                  {probe.momentum_pct > 0 ? "+" : ""}{probe.momentum_pct}%
                </span>
              </span>
            </div>

            <TrendGraph series={series} momentum={probe.momentum_pct} />

            {probe.related && probe.related.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {probe.related.slice(0, 3).map((r, i) => (
                  <Badge
                    key={i}
                    variant="secondary"
                    className={cn(
                      "text-[10px]",
                      r.is_breakout && "bg-primary/10 text-primary border-primary/20"
                    )}
                  >
                    {r.query}
                    {r.is_breakout && " *"}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function StatusBadge({ status }: { status: "pending" | "probing" | "done" | "error" }) {
  const styles = {
    pending: "bg-muted text-muted-foreground",
    probing: "bg-primary/10 text-primary animate-pulse",
    done: "bg-primary/10 text-primary",
    error: "bg-destructive/10 text-destructive",
  }

  return (
    <Badge variant="outline" className={cn("text-[10px] shrink-0", styles[status])}>
      {status}
    </Badge>
  )
}
