"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { TrendGraph } from "@/components/trend-graph"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { CandidateQuery, HypeProbeResult, TrendSeries } from "@/lib/types"

interface TrendRailProps {
  candidates: CandidateQuery[]
  hypeResults: Record<string, HypeProbeResult>
}

function pickSeries(probe: HypeProbeResult): TrendSeries | null {
  const c = [probe.series_30d, probe.series_90d, probe.series_7d]
  for (const s of c) if (s && s.points && s.points.length > 0) return s
  return null
}

export function TrendRail({ candidates, hypeResults }: TrendRailProps) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-xs uppercase tracking-wider text-primary font-medium">
          Trends
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {candidates.map((c) => {
          const probe = hypeResults[c.query]
          if (!probe) return null
          const series = pickSeries(probe)
          const probedTerm = probe.hype_term || c.query
          return (
            <div key={c.query} className="space-y-1">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium truncate" title={`probed: ${probedTerm}`}>
                  {probedTerm}
                </span>
                <Badge
                  variant="outline"
                  className={cn(
                    "text-[10px] shrink-0",
                    probe.momentum_pct > 0
                      ? "bg-primary/10 text-primary border-primary/20"
                      : probe.momentum_pct < 0
                      ? "bg-destructive/10 text-destructive border-destructive/20"
                      : "bg-muted text-muted-foreground"
                  )}
                >
                  {probe.momentum_pct > 0 ? "+" : ""}
                  {probe.momentum_pct}%
                </Badge>
              </div>
              <TrendGraph series={series} momentum={probe.momentum_pct} height={64} showHeader={false} />
            </div>
          )
        })}
        {candidates.length === 0 && (
          <p className="text-xs text-muted-foreground italic">No candidate trends</p>
        )}
      </CardContent>
    </Card>
  )
}
