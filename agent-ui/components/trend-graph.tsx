"use client"

import { useId } from "react"
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { cn } from "@/lib/utils"
import type { TrendSeries } from "@/lib/types"

interface TrendGraphProps {
  series: TrendSeries | null
  momentum: number
  title?: string
  className?: string
  height?: number
  showHeader?: boolean
}

export function TrendGraph({
  series,
  momentum,
  title,
  className,
  height = 96,
  showHeader = true,
}: TrendGraphProps) {
  const reactId = useId()

  if (!series || series.points.length === 0) {
    return (
      <div
        className={cn("rounded border border-dashed border-border flex items-center justify-center", className)}
        style={{ height }}
      >
        <span className="text-[10px] text-muted-foreground uppercase tracking-wider">No trend data</span>
      </div>
    )
  }

  const data = series.points.map((p) => ({ t: p.day_unix * 1000, v: p.intensity }))
  const stroke =
    momentum > 0 ? "hsl(var(--primary))"
    : momentum < 0 ? "hsl(var(--destructive))"
    : "hsl(var(--muted-foreground))"
  const gradientId = `trend-${reactId}`
  const max = Math.max(...data.map((d) => d.v), 1)

  return (
    <div className={cn("rounded border border-border bg-muted/20 p-2", className)}>
      {showHeader && (
        <div className="flex items-center justify-between mb-1">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
            {title ?? `Trend (${series.range})`}
          </span>
          <span className="text-[10px] text-muted-foreground">peak {max}</span>
        </div>
      )}
      <div style={{ height }}>
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
