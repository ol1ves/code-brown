import type { HypeProbeResult, TrendSeries } from "./types"

export function pickPrimarySeries(probe: HypeProbeResult): TrendSeries | null {
  for (const s of [probe.series_30d, probe.series_90d, probe.series_7d]) {
    if (s && s.points && s.points.length > 0) return s
  }
  return null
}
