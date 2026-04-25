"use client"

import { cn } from "@/lib/utils"
import type { Phase } from "@/lib/agent-state"

const phases: { key: Phase; label: string }[] = [
  { key: "idle", label: "Ready" },
  { key: "intent", label: "Intent" },
  { key: "probing", label: "Probing" },
  { key: "planning", label: "Planning" },
  { key: "querying", label: "Searching" },
  { key: "summarizing", label: "Summarizing" },
  { key: "done", label: "Done" },
]

const phaseOrder: Record<Phase, number> = {
  idle: 0,
  intent: 1,
  probing: 2,
  planning: 3,
  querying: 4,
  summarizing: 5,
  done: 6,
  error: -1,
}

interface PhaseIndicatorProps {
  currentPhase: Phase
}

export function PhaseIndicator({ currentPhase }: PhaseIndicatorProps) {
  const currentIndex = phaseOrder[currentPhase]

  if (currentPhase === "error") {
return (
      <div className="flex items-center gap-2 px-3 py-1.5 bg-destructive/10 border border-destructive/20 rounded">
        <div className="h-2 w-2 rounded-full bg-destructive" />
        <span className="text-xs font-medium uppercase tracking-wider text-destructive">Error</span>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-1">
      {phases.map((phase, index) => {
        const isActive = phase.key === currentPhase
        const isComplete = currentIndex > index
        const isPending = currentIndex < index

        return (
          <div key={phase.key} className="flex items-center">
            <div
              className={cn(
                "flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-all uppercase tracking-wide",
                isActive && "bg-primary text-primary-foreground",
                isComplete && "bg-secondary text-primary",
                isPending && "bg-transparent text-muted-foreground/40"
              )}
            >
              {isActive && (
                <div className="h-1.5 w-1.5 rounded-full bg-current animate-pulse" />
              )}
              {isComplete && (
                <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              )}
              <span className={cn(isPending && "hidden sm:inline")}>{phase.label}</span>
            </div>
            {index < phases.length - 1 && (
              <div
                className={cn(
                  "w-4 h-px mx-0.5",
                  isComplete ? "bg-muted-foreground/30" : "bg-border"
                )}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
