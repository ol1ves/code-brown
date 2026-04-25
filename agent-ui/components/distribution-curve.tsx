"use client"

import type { Percentiles } from "@/lib/distribution"

interface DistributionCurveProps {
  price: number
  percentiles: Percentiles
}

export function DistributionCurve({ price, percentiles }: DistributionCurveProps) {
  const { q10, q25, q50, q75, q90 } = percentiles

  if (q50 === 0) {
    return (
      <div className="rounded border border-dashed border-border h-40 flex items-center justify-center">
        <span className="text-xs text-muted-foreground uppercase tracking-wider">No distribution data</span>
      </div>
    )
  }

  const minPrice = q10 * 0.8
  const maxPrice = q90 * 1.2
  const range = maxPrice - minPrice || 1

  const pricePosition = ((price - minPrice) / range) * 100
  const q10Pos = ((q10 - minPrice) / range) * 100
  const q25Pos = ((q25 - minPrice) / range) * 100
  const q50Pos = ((q50 - minPrice) / range) * 100
  const q75Pos = ((q75 - minPrice) / range) * 100
  const q90Pos = ((q90 - minPrice) / range) * 100

  let percentile = 0
  if (price <= q10) percentile = 10
  else if (price <= q25) percentile = 10 + ((price - q10) / (q25 - q10 || 1)) * 15
  else if (price <= q50) percentile = 25 + ((price - q25) / (q50 - q25 || 1)) * 25
  else if (price <= q75) percentile = 50 + ((price - q50) / (q75 - q50 || 1)) * 25
  else if (price <= q90) percentile = 75 + ((price - q75) / (q90 - q75 || 1)) * 15
  else percentile = 90

  return (
    <div className="relative">
      <div className="text-center mb-4">
        <span className="text-3xl font-bold text-primary">{Math.round(percentile)}th</span>
        <span className="text-muted-foreground ml-2">percentile</span>
      </div>

      <div className="relative h-40">
        <svg
          viewBox="0 0 400 120"
          className="w-full h-full"
          preserveAspectRatio="none"
          role="img"
          aria-label={`Price $${Math.round(price)} at ${Math.round(percentile)}th percentile of market distribution`}
        >
          <path
            d="M 0,100 C 40,100 60,95 100,70 C 140,45 170,20 200,10 C 230,20 260,45 300,70 C 340,95 360,100 400,100"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="text-muted-foreground"
          />
          <path
            d="M 0,100 C 40,100 60,95 100,70 C 140,45 170,20 200,10 C 230,20 260,45 300,70 C 340,95 360,100 400,100 L 400,120 L 0,120 Z"
            fill="currentColor"
            className="text-primary/10"
          />
          {[
            { pos: q10Pos },
            { pos: q25Pos },
            { pos: q50Pos },
            { pos: q75Pos },
            { pos: q90Pos },
          ].map((m, i) => (
            <line
              key={i}
              x1={m.pos * 4}
              y1="100"
              x2={m.pos * 4}
              y2="110"
              stroke="currentColor"
              strokeWidth="1"
              className="text-muted-foreground"
            />
          ))}
          <line
            x1={Math.min(Math.max(pricePosition, 0), 100) * 4}
            y1="0"
            x2={Math.min(Math.max(pricePosition, 0), 100) * 4}
            y2="100"
            stroke="currentColor"
            strokeWidth="2"
            strokeDasharray="4"
            className="text-primary"
          />
          <circle
            cx={Math.min(Math.max(pricePosition, 0), 100) * 4}
            cy="50"
            r="6"
            fill="currentColor"
            className="text-primary"
          />
        </svg>

        <div className="flex justify-between text-xs text-muted-foreground mt-2">
          <span>${Math.round(q10)}</span>
          <span>${Math.round(q25)}</span>
          <span className="font-bold text-foreground">${Math.round(q50)}</span>
          <span>${Math.round(q75)}</span>
          <span>${Math.round(q90)}</span>
        </div>
      </div>

      <div className="flex items-center justify-center gap-4 mt-4 text-sm">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-primary" />
          <span className="text-muted-foreground">
            Your Price: <span className="text-foreground font-bold">${Math.round(price)}</span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-0.5 bg-muted-foreground" />
          <span className="text-muted-foreground">Market Distribution</span>
        </div>
      </div>
    </div>
  )
}
