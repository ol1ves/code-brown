"use client"

import { cn } from "@/lib/utils"
import { Spinner } from "@/components/ui/spinner"

interface QueryStatusListProps {
  queryStatus: Record<string, "searching" | "done" | "error">
}

export function QueryStatusList({ queryStatus }: QueryStatusListProps) {
  const entries = Object.entries(queryStatus)
  
  if (entries.length === 0) {
    return (
      <p className="text-sm text-muted-foreground italic">No queries started yet</p>
    )
  }

  return (
    <div className="space-y-1.5">
      {entries.map(([query, status]) => (
        <div
          key={query}
          className="flex items-center gap-2 text-sm"
        >
          {status === "searching" && (
            <Spinner className="h-3 w-3" />
          )}
          {status === "done" && (
            <svg className="h-3 w-3 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          )}
          {status === "error" && (
            <svg className="h-3 w-3 text-destructive" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          )}
          <span className={cn(
            "truncate",
            status === "searching" && "text-foreground",
            status === "done" && "text-muted-foreground",
            status === "error" && "text-destructive"
          )}>
            {query}
          </span>
        </div>
      ))}
    </div>
  )
}
