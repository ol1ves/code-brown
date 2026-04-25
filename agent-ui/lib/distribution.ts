import type { Recommendation } from "./types"

export interface Percentiles {
  q10: number
  q25: number
  q50: number
  q75: number
  q90: number
}

export function derivePercentiles(rec: Recommendation): Percentiles {
  const dist = rec.valuation?.dist
  if (dist && typeof dist.q10 === "number" && typeof dist.q50 === "number" && typeof dist.q90 === "number") {
    return {
      q10: dist.q10,
      q25: (dist.q10 + dist.q50) / 2,
      q50: dist.q50,
      q75: (dist.q50 + dist.q90) / 2,
      q90: dist.q90,
    }
  }
  const q50 = Number(rec.q50 ?? 0)
  if (!q50) return { q10: 0, q25: 0, q50: 0, q75: 0, q90: 0 }
  return {
    q10: q50 * 0.6,
    q25: q50 * 0.8,
    q50,
    q75: q50 * 1.2,
    q90: q50 * 1.4,
  }
}

export function displayName(listing: { id: string; name?: string; designer?: string }): string {
  const designer = listing.designer?.trim()
  const name = listing.name?.trim()
  if (designer && name) return `${designer} - ${name}`
  if (name) return name
  if (designer) return designer
  return "Untitled listing"
}
