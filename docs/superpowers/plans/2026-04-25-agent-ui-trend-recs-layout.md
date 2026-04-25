# Agent-UI Trend → Recommendations Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure `agent-ui` page to show candidate-query trend graphs front-and-center while the agent searches, then transition to a 3-column layout (trends left rail, recommendations center, distribution + summary right) once recommendations arrive — using listing names instead of IDs throughout.

**Architecture:** Single-page React (Next.js App Router) refactor. Drive layout from `state.phase` and `rankedList(state).length`. Extract reusable `<TrendGraph>` from `candidate-card.tsx`. Port the `<DistributionCurve>` SVG component from `frontend/app/page.tsx` into a standalone `agent-ui` component. Widen `Recommendation` type in `lib/types.ts` to expose `valuation.dist`, `cost`, and `q50` so the distribution curve can read percentile data. Add a "selected listing" state in the page so the right column renders details for the currently focused recommendation.

**Tech Stack:** Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS, recharts (already installed for `AreaChart`), shadcn/ui primitives in `components/ui/`. Vitest for unit tests (used by existing `agent-state.test.ts`).

---

## Implementation Status (last update 2026-04-25)

**Mode:** subagent-driven-development. Working on `main` branch with explicit user consent (no worktree). Repo root: `/Users/tyler_rlwajnb/Desktop/code-brown`. Pre-existing dirty file `agent-ui/package-lock.json` MUST stay unstaged across all commits — pnpm is the source of truth (`pnpm-lock.yaml`).

**Progress:**
- ✅ Task 1 — Type widening. Commit `1c9e9bf`. `Recommendation` widened with `q50?`, `cost?`, `confidence?`, `valuation?.dist?.{q10,q50,q90}`, and `live_listing.{name?,designer?,url?,image_urls?}`.
- ✅ Task 2 — Distribution + display-name helpers. Commit `55a2583`. **Side effect:** added `vitest ^4.1.5` as devDependency (existing test files already imported from `"vitest"` but the dep was missing). Ran via pnpm; lockfile updated. 7 new + 5 pre-existing = 12/12 tests pass.
- ✅ Task 3 — TrendGraph extracted from `candidate-card.tsx`. Commit `59b0d6d`. Followed by **fix commit `ee68a38`** (`fix(agent-ui): unique gradientId via useId + showHeader prop in TrendGraph`) to address two Important review findings:
  - `gradientId` now derived from React's `useId()` (collision-safe across multiple instances). `useId()` is called unconditionally above the empty-series early return — required by hook rules.
  - New optional prop `showHeader?: boolean` (default `true`). Lets `TrendRail` (Task 5) suppress the internal range/peak header so it doesn't duplicate the rail's external label.
  - Both changes are backward-compatible — `CandidateCard` call site stays `<TrendGraph series={series} momentum={probe.momentum_pct} />`.
- ⏳ Task 4 — TrendStage. **Next up.**
- ⏳ Task 5: TrendRail component (left-rail post-recs)

Task 6: DistributionCurve component (port from legacy frontend)

Task 7: ListingSummary right column

Task 8: Drop ID fallback in RecommendationItem + onSelect

Task 9: Wire phase-driven layout in page.tsx

Task 10: Manual browser verification

Final code review of full implementation

**Tech-stack note:** Project actually uses Next.js 16 + React 19 (the plan front matter said "Next 14 / React 18" — leave as-is, all code in the plan is compatible with both).

**Test runner state:** `cd agent-ui && npx vitest run` yields `3 files / 12 tests pass`. Always re-run after each task. Pre-existing TS errors about missing `vitest` types may surface — they're harmless (vitest ships its own types) and existed at base SHA `668dec7`.

**Important when continuing as a fresh agent:**
- Tasks 4 and 5 should pass `series` + `momentum` + `height` to `<TrendGraph>` directly. Task 5 (`TrendRail`) should pass `showHeader={false}` and provide its own header via the surrounding markup (per plan code in Task 5). The plan code in Task 5 currently does NOT include `showHeader={false}` — add it during implementation, since the plan was authored before the `showHeader` prop existed.
- Task 4's `TrendStage` calls `<TrendGraph ... title={...} height={160} />` — the `title` prop already overrides the internal header label, so no `showHeader` change needed there.
- Helpers from Task 2 (`derivePercentiles`, `displayName`, `Percentiles`) are imported via `@/lib/distribution` — used in Tasks 6 and 7.
- All UI components stay under `agent-ui/components/`. Use existing shadcn primitives (`Card`, `CardContent`, `CardHeader`, `CardTitle`, `Badge`) from `@/components/ui/...`.
- `npx tsc --noEmit` after every task. `npx vitest run` after every task. Commit only the files listed for that task — never `package-lock.json`.

**Stop conditions for the next agent:** After completing Tasks 4–9, run Task 10 (manual browser verification) before declaring the implementation done. Tasks 4–9 are mechanical enough for a cheap model; Task 9 (page-level layout refactor) and Task 10 should use a stronger model.

---

## File Structure

**Create:**
- `agent-ui/components/trend-graph.tsx` — extracted reusable trend graph (Area chart + header). Owns no state; takes `series`, `momentum`, optional `title`.
- `agent-ui/components/trend-rail.tsx` — left-rail collapsed view of all candidates with mini trend graphs once recommendations arrive.
- `agent-ui/components/trend-stage.tsx` — full-width "stage" view of candidate trend graphs shown before recommendations are ready.
- `agent-ui/components/distribution-curve.tsx` — SVG bell-curve component ported from `frontend/app/page.tsx:509-624`. Takes price + `{q10,q25,q50,q75,q90}`.
- `agent-ui/components/listing-summary.tsx` — right-column module showing selected listing details + distribution + agent summary text. Always references items by `live_listing.name` (fallback to `designer`), never `id`.
- `agent-ui/lib/distribution.ts` — pure helpers: `derivePercentiles(rec)` returns `{q10,q25,q50,q75,q90}` interpolating q25/q75 from q10/q50/q90; `displayName(listing)` returns formatted name string.
- `agent-ui/lib/distribution.test.ts` — vitest unit tests for the helpers.

**Modify:**
- `agent-ui/lib/types.ts:15-21` — widen `Recommendation` interface to expose `cost`, `q50`, `confidence`, and `valuation: { dist?: { q10: number; q50: number; q90: number } }` and `live_listing` to include `name?: string`.
- `agent-ui/lib/agent-state.ts:13-17` — add `selectedListingId: string | null` to `RankedItem`'s parent state so the page can drive the right column. Also add `selectedListingId` to `AgentUiState`, `initialState`, and a setter pattern (the page sets this directly, no reducer event).
- `agent-ui/components/candidate-card.tsx:91-155` — replace the local `TrendGraph` definition with a re-export/import of the new `trend-graph.tsx`; keep the rest of the card unchanged.
- `agent-ui/app/page.tsx` — full layout refactor: replace the 2-column grid with a phase-driven layout (stage view → 3-column view). Wire `selectedListingId`. Replace IDs with display names throughout.
- `agent-ui/components/recommendation-item.tsx:55` — drop the `|| rec.live_listing.id` fallback for the title; use designer/name only and never the id.

**Test:**
- `agent-ui/lib/distribution.test.ts` (new)
- Existing `agent-ui/lib/agent-state.test.ts` updated for the new `selectedListingId` field on `initialState`.

---1

## Task 1: Type Widening for Recommendation ✅ DONE (commit 1c9e9bf)

**Files:**
- Modify: `agent-ui/lib/types.ts:15-21`

- [x] **Step 1: Update Recommendation interface to expose valuation + listing name**

Replace the existing `Recommendation` block:

```typescript
export interface Recommendation {
  item_id: string
  edge_usd: number
  p_sell: number
  q50?: number
  cost?: number
  confidence?: "high" | "medium" | "low" | "insufficient"
  valuation?: {
    dist?: { q10: number; q50: number; q90: number }
    [key: string]: unknown
  }
  live_listing: {
    id: string
    name?: string
    designer?: string
    url?: string
    image_urls?: string[]
  }
  [key: string]: unknown
}
```

- [x] **Step 2: Type-check**

Run: `cd agent-ui && npx tsc --noEmit`
Expected: PASS — no type errors. Existing callers only read `edge_usd`, `p_sell`, `live_listing.{id,name,designer,url,image_urls}`, all preserved.

- [x] **Step 3: Commit**

```bash
git add agent-ui/lib/types.ts
git commit -m "feat(agent-ui): widen Recommendation type with valuation + cost"
```

---

## Task 2: Distribution + Display-Name Helpers ✅ DONE (commit 55a2583, vitest installed)

**Files:**
- Create: `agent-ui/lib/distribution.ts`
- Test: `agent-ui/lib/distribution.test.ts`

- [x] **Step 1: Write failing tests**

Create `agent-ui/lib/distribution.test.ts`:

```typescript
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
    expect(p.q25).toBe(150) // halfway between q10 and q50
    expect(p.q75).toBe(300) // halfway between q50 and q90
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
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd agent-ui && npx vitest run lib/distribution.test.ts`
Expected: FAIL with "Cannot find module './distribution'".

> Note: vitest was NOT in `package.json` at the time. Added `vitest ^4.1.5` as devDependency via `pnpm add -D vitest` and committed `package.json` + `pnpm-lock.yaml` with this task.

- [x] **Step 3: Implement helpers**

Create `agent-ui/lib/distribution.ts`:

```typescript
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
```

- [x] **Step 4: Run tests to verify pass**

Run: `cd agent-ui && npx vitest run lib/distribution.test.ts`
Expected: PASS — all 7 cases green.

- [x] **Step 5: Commit**

```bash
git add agent-ui/lib/distribution.ts agent-ui/lib/distribution.test.ts agent-ui/package.json agent-ui/pnpm-lock.yaml
git commit -m "feat(agent-ui): add percentile + display-name helpers"
```

---

## Task 3: Extract TrendGraph Component ✅ DONE (commits 59b0d6d + ee68a38)

**Files:**
- Create: `agent-ui/components/trend-graph.tsx`
- Modify: `agent-ui/components/candidate-card.tsx:91-155` (and import on line 1-7)

> **Post-review fix landed in commit `ee68a38`:** the `gradientId` is now `trend-${useId()}` (collision-safe across multiple `<TrendGraph>` instances on the same page) and the component accepts an optional `showHeader?: boolean` prop (default `true`) so `TrendRail` (Task 5) can suppress the internal range/peak header. The code block below shows the ORIGINAL plan body — the actual file as committed reflects the fix. New code calling `<TrendGraph>` should be aware that `showHeader={false}` is available, and Task 5 should pass it.

- [x] **Step 1: Create standalone TrendGraph**

Create `agent-ui/components/trend-graph.tsx` (lift the body of the existing `TrendGraph` from `candidate-card.tsx:91-155`, generalised with optional `title` and `className`):

```typescript
"use client"

import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { cn } from "@/lib/utils"
import type { TrendSeries } from "@/lib/types"

interface TrendGraphProps {
  series: TrendSeries | null
  momentum: number
  title?: string
  className?: string
  height?: number
}

export function TrendGraph({ series, momentum, title, className, height = 96 }: TrendGraphProps) {
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
  const gradientId = `trend-${series.range}-${data.length}-${momentum}`
  const max = Math.max(...data.map((d) => d.v), 1)

  return (
    <div className={cn("rounded border border-border bg-muted/20 p-2", className)}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
          {title ?? `Trend (${series.range})`}
        </span>
        <span className="text-[10px] text-muted-foreground">peak {max}</span>
      </div>
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
```

- [x] **Step 2: Refactor candidate-card.tsx to consume it**

In `agent-ui/components/candidate-card.tsx`:

1. Remove the existing `TrendGraph` function (currently lines 91-155).
2. Remove the `Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis` import on line 3.
3. Add import: `import { TrendGraph } from "@/components/trend-graph"` after line 7.
4. The `<TrendGraph series={series} momentum={probe.momentum_pct} />` call on line 65 stays the same.

- [x] **Step 3: Type-check + run existing tests**

Run: `cd agent-ui && npx tsc --noEmit && npx vitest run`
Expected: PASS — TS clean, all existing tests still green (no behaviour change).

- [x] **Step 4: Commit**

```bash
git add agent-ui/components/trend-graph.tsx agent-ui/components/candidate-card.tsx
git commit -m "refactor(agent-ui): extract TrendGraph into reusable component"
```

> Followed by fix commit `ee68a38`: `fix(agent-ui): unique gradientId via useId + showHeader prop in TrendGraph`.

---

## Task 4: TrendStage (full-width pre-recommendations view) ⏳ NEXT

**Files:**
- Create: `agent-ui/components/trend-stage.tsx`

- [ ] **Step 1: Implement TrendStage**

Create `agent-ui/components/trend-stage.tsx`:

```typescript
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
                      title={`${c.query} (${series?.range ?? "—"})`}
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
```

- [ ] **Step 2: Type-check**

Run: `cd agent-ui && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add agent-ui/components/trend-stage.tsx
git commit -m "feat(agent-ui): add TrendStage front-and-center pre-recs view"
```

---

## Task 5: TrendRail (collapsed left-rail post-recommendations view)

**Files:**
- Create: `agent-ui/components/trend-rail.tsx`

- [ ] **Step 1: Implement TrendRail**

Create `agent-ui/components/trend-rail.tsx`:

```typescript
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
          return (
            <div key={c.query} className="space-y-1">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium truncate">{c.query}</span>
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
              <TrendGraph series={series} momentum={probe.momentum_pct} height={64} />
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
```

- [ ] **Step 2: Type-check**

Run: `cd agent-ui && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add agent-ui/components/trend-rail.tsx
git commit -m "feat(agent-ui): add TrendRail collapsed left-rail view"
```

---

## Task 6: DistributionCurve Component

**Files:**
- Create: `agent-ui/components/distribution-curve.tsx`

- [ ] **Step 1: Port DistributionCurve from legacy frontend**

Create `agent-ui/components/distribution-curve.tsx` (adapted from `frontend/app/page.tsx:509-624`, accepting external percentiles + price):

```typescript
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
        <svg viewBox="0 0 400 120" className="w-full h-full" preserveAspectRatio="none">
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
```

- [ ] **Step 2: Type-check**

Run: `cd agent-ui && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add agent-ui/components/distribution-curve.tsx
git commit -m "feat(agent-ui): port DistributionCurve from legacy frontend"
```

---

## Task 7: ListingSummary Right Column

**Files:**
- Create: `agent-ui/components/listing-summary.tsx`

- [ ] **Step 1: Implement ListingSummary**

Create `agent-ui/components/listing-summary.tsx`:

```typescript
"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { DistributionCurve } from "@/components/distribution-curve"
import { ThinkingDisplay } from "@/components/thinking-display"
import { derivePercentiles, displayName } from "@/lib/distribution"
import type { RankedItem } from "@/lib/agent-state"

interface ListingSummaryProps {
  selected: RankedItem | null
  summaryText: string
  summaryThinking: string
  highlights: Array<{ item_id: string; why: string }>
  rankedItems: RankedItem[]
}

function highlightTitle(highlight: { item_id: string; why: string }, rankedItems: RankedItem[]): string {
  const match = rankedItems.find((r) => r.item.live_listing.id === highlight.item_id)
  return match ? displayName(match.item.live_listing) : "Unknown listing"
}

export function ListingSummary({
  selected,
  summaryText,
  summaryThinking,
  highlights,
  rankedItems,
}: ListingSummaryProps) {
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm uppercase tracking-wider text-primary font-medium">
            Distribution
          </CardTitle>
        </CardHeader>
        <CardContent>
          {selected ? (
            <>
              <p className="text-sm font-medium mb-1">{displayName(selected.item.live_listing)}</p>
              <DistributionCurve
                price={Number(selected.item.cost ?? 0)}
                percentiles={derivePercentiles(selected.item)}
              />
            </>
          ) : (
            <p className="text-sm text-muted-foreground italic">Select a recommendation to see its price distribution</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm uppercase tracking-wider text-primary font-medium">
            Summary
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <ThinkingDisplay
            label="Summary Thinking"
            content={summaryThinking}
            defaultExpanded={false}
          />
          {summaryText ? (
            <p className="text-sm leading-relaxed">{summaryText}</p>
          ) : (
            <p className="text-sm text-muted-foreground italic">
              Summary will appear after analysis completes
            </p>
          )}
          {highlights.length > 0 && (
            <div>
              <h4 className="text-sm font-medium mb-2">Key Highlights</h4>
              <ul className="space-y-2">
                {highlights.map((h, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <svg className="h-4 w-4 text-primary shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                      <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                    </svg>
                    <span>
                      <span className="font-medium">{highlightTitle(h, rankedItems)}</span>
                      <span className="text-muted-foreground"> - {h.why}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
```

- [ ] **Step 2: Type-check**

Run: `cd agent-ui && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add agent-ui/components/listing-summary.tsx
git commit -m "feat(agent-ui): add ListingSummary right column with distribution + summary"
```

---

## Task 8: Drop ID Fallback in RecommendationItem + Add onSelect

**Files:**
- Modify: `agent-ui/components/recommendation-item.tsx`

- [ ] **Step 1: Update RecommendationItem to use displayName + accept onSelect**

Replace the file contents with:

```typescript
"use client"

import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import { displayName } from "@/lib/distribution"
import type { RankedItem } from "@/lib/agent-state"

interface RecommendationItemProps {
  item: RankedItem
  rank: number
  isHighlighted?: boolean
  isSelected?: boolean
  highlightReason?: string
  onSelect?: () => void
}

export function RecommendationItem({
  item,
  rank,
  isHighlighted,
  isSelected,
  highlightReason,
  onSelect,
}: RecommendationItemProps) {
  const { item: rec, score, foundAcrossQueries } = item
  const imageUrl = rec.live_listing.image_urls?.[0]
  const title = displayName(rec.live_listing)

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "group w-full text-left flex items-start gap-3 p-3 rounded-lg transition-colors",
        isSelected
          ? "bg-primary/10 border border-primary/30"
          : isHighlighted
          ? "bg-primary/5 border border-primary/20"
          : "hover:bg-secondary/50"
      )}
    >
      <div
        className={cn(
          "flex items-center justify-center w-6 h-6 rounded text-xs font-bold shrink-0",
          rank <= 3 ? "bg-primary text-primary-foreground" : "bg-secondary text-muted-foreground"
        )}
      >
        {rank}
      </div>

      {imageUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={imageUrl}
          alt={title}
          className="w-14 h-14 rounded object-cover shrink-0 bg-secondary"
          loading="lazy"
          onError={(e) => {
            ;(e.currentTarget as HTMLImageElement).style.visibility = "hidden"
          }}
        />
      ) : (
        <div className="w-14 h-14 rounded bg-secondary shrink-0" />
      )}

      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="font-medium text-sm truncate">{title}</p>
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
            Score:{" "}
            <span
              className={cn(
                "font-medium",
                score > 0 ? "text-primary" : score < 0 ? "text-destructive" : "text-foreground"
              )}
            >
              {score.toFixed(2)}
            </span>
          </span>
          <span>
            Edge: <span className="text-foreground">${Number(rec.edge_usd || 0).toFixed(0)}</span>
          </span>
          <span>
            P(Sell):{" "}
            <span className="text-foreground">{(Number(rec.p_sell || 0) * 100).toFixed(0)}%</span>
          </span>
        </div>
      </div>
    </button>
  )
}
```

Note: dropped the `<a>` external-link icon — the row is now a button driving selection. The link to the listing source belongs in `ListingSummary` (out of scope here; users still click through via the rank list when needed — re-add as a nested link only if the user requests it).

- [ ] **Step 2: Type-check**

Run: `cd agent-ui && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add agent-ui/components/recommendation-item.tsx
git commit -m "refactor(agent-ui): use displayName, add selection click in RecommendationItem"
```

---

## Task 9: Wire Phase-Driven Layout in page.tsx

**Files:**
- Modify: `agent-ui/app/page.tsx`

- [ ] **Step 1: Replace page.tsx with phase-driven layout**

Replace the contents of `agent-ui/app/page.tsx` with:

```typescript
"use client"

import { useEffect, useMemo, useState } from "react"
import { initialState, rankedList, reduceAgentEvent } from "@/lib/agent-state"
import { streamAgentRun } from "@/lib/agent-stream"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { PhaseIndicator } from "@/components/phase-indicator"
import { RecommendationItem } from "@/components/recommendation-item"
import { TrendStage } from "@/components/trend-stage"
import { TrendRail } from "@/components/trend-rail"
import { ListingSummary } from "@/components/listing-summary"

export default function Page() {
  const [intentText, setIntentText] = useState("")
  const [state, setState] = useState(initialState)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [selectedListingId, setSelectedListingId] = useState<string | null>(null)

  const items = useMemo(() => rankedList(state), [state])

  const highlightMap = useMemo(() => {
    const map: Record<string, string> = {}
    for (const h of state.highlights) map[h.item_id] = h.why
    return map
  }, [state.highlights])

  const showRecsLayout = items.length > 0

  useEffect(() => {
    if (!showRecsLayout) {
      setSelectedListingId(null)
      return
    }
    if (!selectedListingId || !items.find((i) => i.item.live_listing.id === selectedListingId)) {
      setSelectedListingId(items[0].item.live_listing.id)
    }
  }, [items, showRecsLayout, selectedListingId])

  const selected = useMemo(
    () => items.find((i) => i.item.live_listing.id === selectedListingId) ?? null,
    [items, selectedListingId]
  )

  async function onRun() {
    if (!intentText.trim()) return
    setBusy(true)
    setError("")
    setState(initialState)
    setSelectedListingId(null)
    try {
      await streamAgentRun(intentText, (event) => {
        setState((prev) => reduceAgentEvent(prev, event))
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : "Stream failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="min-h-screen bg-background">
      <header className="border-b border-border bg-card/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-[1600px] mx-auto px-4 py-4">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-2xl font-serif italic text-primary tracking-wide">Groogle</h1>
              <p className="text-sm text-muted-foreground">AI-powered item discovery and analysis</p>
            </div>
            <PhaseIndicator currentPhase={state.phase} />
          </div>
        </div>
      </header>

      <div className="max-w-[1600px] mx-auto px-4 py-6">
        <Card className="mb-6">
          <CardContent className="p-4">
            <form
              onSubmit={(e) => {
                e.preventDefault()
                onRun()
              }}
              className="flex gap-3"
            >
              <Input
                value={intentText}
                onChange={(e) => setIntentText(e.target.value)}
                placeholder="Find me underpriced archive 2000s pieces..."
                className="flex-1"
                disabled={busy}
              />
              <Button
                type="submit"
                disabled={busy || !intentText.trim()}
                className="uppercase tracking-wider font-medium"
              >
                {busy ? (
                  <>
                    <Spinner className="mr-2 h-4 w-4" />
                    Searching...
                  </>
                ) : (
                  "Search"
                )}
              </Button>
            </form>
            {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
          </CardContent>
        </Card>

        {showRecsLayout ? (
          <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)_400px]">
            <aside className="space-y-6">
              <TrendRail candidates={state.candidates} hypeResults={state.hypeResults} />
            </aside>

            <section>
              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h2 className="text-sm uppercase tracking-wider text-primary font-medium">
                      Recommendations
                    </h2>
                    <span className="text-xs text-muted-foreground">{items.length} items</span>
                  </div>
                  <div className="space-y-1 max-h-[70vh] overflow-y-auto -mx-2 px-2">
                    {items.map((item, index) => {
                      const id = item.item.live_listing.id
                      return (
                        <RecommendationItem
                          key={id}
                          item={item}
                          rank={index + 1}
                          isHighlighted={!!highlightMap[id]}
                          isSelected={selectedListingId === id}
                          highlightReason={highlightMap[id]}
                          onSelect={() => setSelectedListingId(id)}
                        />
                      )
                    })}
                  </div>
                </CardContent>
              </Card>
            </section>

            <aside>
              <ListingSummary
                selected={selected}
                summaryText={state.summaryText}
                summaryThinking={state.summaryThinking}
                highlights={state.highlights}
                rankedItems={items}
              />
            </aside>
          </div>
        ) : (
          <TrendStage
            candidates={state.candidates}
            hypeStatus={state.hypeStatus}
            hypeResults={state.hypeResults}
            intentReasoning={state.intentReasoning}
          />
        )}
      </div>
    </main>
  )
}
```

- [ ] **Step 2: Type-check**

Run: `cd agent-ui && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 3: Run existing tests**

Run: `cd agent-ui && npx vitest run`
Expected: PASS — `agent-state.test.ts` and `distribution.test.ts` both green.

- [ ] **Step 4: Commit**

```bash
git add agent-ui/app/page.tsx
git commit -m "feat(agent-ui): phase-driven 3-column layout (trend rail, recs, summary)"
```

---

## Task 10: Manual Verification in Browser

**Files:** none (verification only)

- [ ] **Step 1: Build + start dev server**

Run: `cd agent-ui && pnpm install && pnpm dev`
Expected: Next dev server boots on port 3000 with no compile errors.

- [ ] **Step 2: Verify pre-recommendations stage**

1. Open `http://localhost:3000`.
2. Type a query and submit (e.g. "underpriced archive 2000s pieces").
3. While the agent is in `intent` / `probing` / `planning` / `querying` *and* `items.length === 0`, confirm:
   - `<TrendStage>` is rendered full-width.
   - Candidate cards stream in with their trend graphs as `hype_done` events arrive.
   - No 3-column layout, no recommendations panel.

- [ ] **Step 3: Verify post-recommendations layout**

Once `query_done` events have populated recommendations, confirm:
- Layout flips to 3 columns: trend rail (left, 320px), recommendations (center), summary (right, 400px).
- Trend rail shows compact (h-16) graphs for every candidate.
- Recommendation rows show `Designer - Name` only — never raw IDs (verify by inspecting at least one row that lacks a designer or name in the backend feed).
- Clicking a recommendation row updates the right column's `<DistributionCurve>` and listing name.
- The summary "Key Highlights" lists items by display name, not item_id.

- [ ] **Step 4: Verify graceful empty / no-data states**

- Stop the agent before any results. Confirm the stage view stays put with `intentReasoning` / "Generating candidate queries..." copy.
- For a recommendation that lacks `valuation.dist`, confirm distribution still renders (scaled fallback) and never crashes.

- [ ] **Step 5: Commit (optional — only if any tweaks were needed during verification)**

If you adjusted styling/layout copy during verification, commit those changes. Otherwise skip.

```bash
git add agent-ui/...
git commit -m "polish(agent-ui): tweaks from manual verification"
```

---

## Self-Review Notes

- **Spec coverage:**
  - "Render candidate query trend data graphs front and center until output ready" → Task 4 (`TrendStage`) + Task 9 (phase-driven render).
  - "Collapse trend graphs to sidebar on left when recommendations are ready" → Task 5 (`TrendRail`) + Task 9.
  - "Recommendations take center column" → Task 9 grid template.
  - "Distribution curve (using percentile + historical spread) on right side module" → Task 2 (percentiles helper interpolating q25/q75 from `valuation.dist.q10/q50/q90`) + Task 6 (`DistributionCurve`) + Task 7 (`ListingSummary`).
  - "Copy UI implementation from legacy frontend folder where applicable" → Task 6 explicitly ports `frontend/app/page.tsx:509-624`.
  - "Summary info on right side; refer by listing name not id" → Task 2 (`displayName`), Task 7 (`ListingSummary` highlights look up name by `item_id`), Task 8 (`RecommendationItem` no longer falls back to `id`).

- **Type consistency:** `Percentiles` defined once in `lib/distribution.ts`, consumed identically in `DistributionCurve` and `ListingSummary`. `RankedItem` from `lib/agent-state.ts` is the single source of truth passed to all three new components.

- **Out of scope (explicitly):** No backend changes. No new agent events. The "select first listing" behaviour is handled in the page via `useEffect`, not via a reducer event. External-link icon dropped from `RecommendationItem`; if the user wants click-through to the source listing back, surface it in `ListingSummary` as a follow-up task.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-25-agent-ui-trend-recs-layout.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
