'use client'

// Adapted from beautifului.dev "Loading State" (MIT, Copyright (c) 2026 Shane Levine; see LICENSE
// here): the wait before an answer's first words, with the step it's on and the time so far. Only
// its "Drive" grid is kept. The time is hidden from screen readers so they hear the step alone.
import { useEffect, useState } from 'react'

// A chevron wave across a 3×3 grid: each cell starts 90ms after the one before it
const DELAYS = Array.from({ length: 9 }, (_, i) => (i % 3 + Math.abs(Math.floor(i / 3) - 1)) * 90)

function useElapsed() {
  const [tenths, setTenths] = useState(0)
  useEffect(() => {
    const timer = setInterval(() => setTenths((prev) => prev + 1), 100)
    return () => clearInterval(timer)
  }, [])
  const seconds = tenths / 10
  return seconds < 60 ? `${seconds.toFixed(1)}s` : `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`
}

export default function LoadingState({ label }) {
  const elapsed = useElapsed()
  return (
    <div role="status" className="flex w-fit items-center gap-2.5">
      <span aria-hidden="true" className="grid shrink-0 grid-cols-[repeat(3,5px)] gap-0.5">
        {DELAYS.map((delay, i) => (
          <span key={i} className="size-[5px] animate-pixel-on rounded-[1px] bg-primary opacity-15"
                style={{ animationDelay: `${delay}ms` }} />
        ))}
      </span>
      <span className="animate-shimmer-text bg-[linear-gradient(90deg,var(--muted-foreground)_35%,var(--foreground)_50%,var(--muted-foreground)_65%)] bg-size-[200%_100%] bg-clip-text text-sm font-medium text-transparent">
        {label}
      </span>
      <span aria-hidden="true" className="font-mono text-xs text-muted-foreground tabular-nums">{elapsed}</span>
    </div>
  )
}
