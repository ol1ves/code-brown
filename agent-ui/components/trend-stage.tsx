"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { CandidateCard } from "@/components/candidate-card"
import { TrendGraph } from "@/components/trend-graph"
import type { CandidateQuery, HypeProbeResult, TrendSeries } from "@/lib/types"

interface TrendStageProps {
  candidates: CandidateQuery[]
  hypeStatus: Record<string, "pending" | "probing" | "done" | "error">
  hypeResults: Record<string, HypeProbeResult>
  intentReasoning: string
}

function pickSeries(probe: HypeProbeResult): TrendSeries | null {
  const c = [probe.series_30d, probe.series_90d, probe.series_7d]
  for (const s of c) if (s && s.points && s.points.length > 0) return s
  return null
}

export function TrendStage({ candidates, hypeStatus, hypeResults, intentReasoning }: TrendStageProps) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm uppercase tracking-wider text-primary font-medium">
          Candidate Query Trends
        </CardTitle>
      </CardHeader>
      <CardContent>
        {intentReasoning && (
          <p className="text-sm text-muted-foreground mb-4">{intentReasoning}</p>
        )}
        {candidates.length === 0 ? (
          <p className="text-sm text-muted-foreground italic">Generating candidate queries...</p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {candidates.map((c) => {
              const probe = hypeResults[c.query]
              const series = probe ? pickSeries(probe) : null
              return (
                <div key={c.query} className="space-y-3">
                  <CandidateCard
                    candidate={c}
                    status={hypeStatus[c.query] ?? "pending"}
                    probe={probe}
                  />
                  {probe && (
                    <TrendGraph
                      series={series}
                      momentum={probe.momentum_pct}
                      title={`${probe.hype_term || c.query} (${series?.range ?? "—"})`}
                      height={160}
                    />
                  )}
                </div>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
