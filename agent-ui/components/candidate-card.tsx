"use client"

import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { cn } from "@/lib/utils"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
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

function TrendGraph({ series, momentum }: { series: TrendSeries | null; momentum: number }) {
  if (!series || series.points.length === 0) {
    return (
      <div className="h-24 rounded border border-dashed border-border flex items-center justify-center">
        <span className="text-[10px] text-muted-foreground uppercase tracking-wider">No trend data</span>
      </div>
    )
  }

  const data = series.points.map((p) => ({
    t: p.day_unix * 1000,
    v: p.intensity,
  }))
  const stroke =
    momentum > 0 ? "hsl(var(--primary))"
    : momentum < 0 ? "hsl(var(--destructive))"
    : "hsl(var(--muted-foreground))"
  const gradientId = `trend-${series.range}-${data.length}-${momentum}`
  const max = Math.max(...data.map((d) => d.v), 1)

  return (
    <div className="rounded border border-border bg-muted/20 p-2">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Trend ({series.range})</span>
        <span className="text-[10px] text-muted-foreground">peak {max}</span>
      </div>
      <div className="h-24">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={stroke} stopOpacity={0.4} />
                <stop offset="100%" stopColor={stroke} stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis dataKey="t" hide />
            <YAxis hide domain={[0, "dataMax"]} />
            <Tooltip
              cursor={{ stroke, strokeOpacity: 0.3 }}
              content={({ active, payload }) => {
                if (!active || !payload || !payload.length) return null
                const p = payload[0].payload as { t: number; v: number }
                const date = new Date(p.t).toLocaleDateString(undefined, { month: "short", day: "numeric" })
                return (
                  <div className="rounded border border-border bg-popover px-2 py-1 text-[10px] text-foreground shadow-sm">
                    {date}: {p.v}
                  </div>
                )
              }}
            />
            <Area
              type="monotone"
              dataKey="v"
              stroke={stroke}
              strokeWidth={1.5}
              fill={`url(#${gradientId})`}
              isAnimationActive={false}
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
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
