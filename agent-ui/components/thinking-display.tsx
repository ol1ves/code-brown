"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

interface ThinkingDisplayProps {
  label: string
  content: string
  defaultExpanded?: boolean
}

export function ThinkingDisplay({ label, content, defaultExpanded = false }: ThinkingDisplayProps) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  if (!content) return null

  return (
    <div className="space-y-2">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setExpanded(!expanded)}
        className="h-auto p-0 text-xs text-muted-foreground hover:text-foreground hover:bg-transparent"
      >
        <svg
          className={cn("h-3 w-3 mr-1 transition-transform", expanded && "rotate-90")}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        {label}
      </Button>
      {expanded && (
        <div className="pl-4 border-l-2 border-primary/30">
          <p className="text-xs text-muted-foreground whitespace-pre-wrap leading-relaxed">
            {content}
          </p>
        </div>
      )}
    </div>
  )
}
