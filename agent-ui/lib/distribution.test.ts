import { describe, expect, it } from "vitest"
import { derivePercentiles, displayName } from "./distribution"
import type { Recommendation } from "./types"

const baseListing = { id: "abc", name: "Cargo Pant", designer: "Rick Owens" }

function makeRec(overrides: Partial<Recommendation> = {}): Recommendation {
  return {
    item_id: "abc",
    edge_usd: 50,
    p_sell: 0.4,
    cost: 100,
    q50: 200,
    live_listing: baseListing,
    ...overrides,
  }
}

describe("derivePercentiles", () => {
  it("uses valuation.dist when present and interpolates q25/q75 from q10-q50-q90", () => {
    const rec = makeRec({ valuation: { dist: { q10: 100, q50: 200, q90: 400 } } })
    const p = derivePercentiles(rec)
    expect(p.q10).toBe(100)
    expect(p.q50).toBe(200)
    expect(p.q90).toBe(400)
    expect(p.q25).toBe(150)
    expect(p.q75).toBe(300)
  })

  it("falls back to scaled q50 when valuation.dist missing", () => {
    const rec = makeRec({ q50: 100, valuation: undefined })
    const p = derivePercentiles(rec)
    expect(p.q10).toBeCloseTo(60)
    expect(p.q25).toBeCloseTo(80)
    expect(p.q50).toBe(100)
    expect(p.q75).toBeCloseTo(120)
    expect(p.q90).toBeCloseTo(140)
  })

  it("returns zero distribution when q50 is missing or zero", () => {
    const rec = makeRec({ q50: 0, valuation: undefined })
    const p = derivePercentiles(rec)
    expect(p).toEqual({ q10: 0, q25: 0, q50: 0, q75: 0, q90: 0 })
  })
})

describe("displayName", () => {
  it("uses 'designer - name' when both present", () => {
    expect(displayName({ id: "x", designer: "Rick Owens", name: "Cargo Pant" })).toBe(
      "Rick Owens - Cargo Pant"
    )
  })
  it("uses name when designer missing", () => {
    expect(displayName({ id: "x", name: "Cargo Pant" })).toBe("Cargo Pant")
  })
  it("uses designer when name missing", () => {
    expect(displayName({ id: "x", designer: "Rick Owens" })).toBe("Rick Owens")
  })
  it("falls back to 'Untitled listing' when both missing — never returns id", () => {
    expect(displayName({ id: "raw-id-123" })).toBe("Untitled listing")
  })
})
