// @ts-check
'use client'

// In the manner of beautifului.dev's "Thinking" (expandable steps), written for Holos's own
// parts rather than ported: closed it is one quiet line; open, how the answer came about (E072).
import { useId, useMemo, useState } from 'react'
import { ChevronRight, ShieldAlert, ShieldCheck } from 'lucide-react'

import { traceView } from '@/lib/trace'
import { cn } from '@/lib/utils'

/**
 * How an answer was made (P5.6): its route, the safety checks with their rule IDs, and what each
 * coach did, with its time (owner, 27 Nov 2026). Under a finished live answer only (owner, 27 Nov 2026, Part
 * E #79): nothing is fetched or stored for it, so a saved answer has none.
 */
/**
 * @param {{ trace: import('@/lib/trace').TraceView,
 *   view: Pick<import('@/lib/turnView').TurnView, 'sections' | 'repeats'> }} props
 */
export default function TracePanel({ trace, view }) {
  const [open, setOpen] = useState(false)
  const id = useId()
  const v = useMemo(() => traceView(trace, view), [trace, view])
  return (
    <div className="flex flex-col gap-2 text-sm">
      <button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen((prev) => !prev)}
              className="flex w-fit items-start gap-1 rounded-md text-left text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">
        <ChevronRight aria-hidden="true" className={cn('mt-0.5 size-4 shrink-0 transition-transform', open && 'rotate-90')} />
        {/* One run of text, so on a phone the summary wraps after the words, not beside them */}
        <span>How this answer was made{v.summary && <span className="text-xs"> · {v.summary}</span>}</span>
      </button>
      {open && (
        <div id={id} className="flex flex-col gap-3 rounded-lg border bg-card p-3 text-card-foreground">
          <Row label="Route">{v.route}</Row>

          {v.decisions.length > 0 && (
            <Group title="Safety checks">
              {v.decisions.map((d, i) => (
                <li key={i} className="flex items-start gap-2">
                  {d.blocked
                    ? <ShieldAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-caution" />
                    : <ShieldCheck aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-primary" />}
                  <span className="min-w-0">
                    {/* The item stays whole; on a phone its rule IDs move under it, each in one piece */}
                    <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
                      <span>
                        <span className={cn('font-medium', d.blocked && 'text-caution')}>{d.label}</span>
                        {d.item && <> {d.item}</>}
                      </span>
                      {d.rules.map((r) => (
                        <code key={r} className="rounded bg-muted px-1 font-mono text-xs whitespace-nowrap">{r}</code>
                      ))}
                    </span>
                    {d.reasons.map((r) => <span key={r} className="block text-foreground-secondary">{r}</span>)}
                  </span>
                </li>
              ))}
            </Group>
          )}

          {v.coaches.length > 0 && (
            <Group title="Coaches">
              {v.coaches.map((c, i) => (
                <li key={i} className="flex justify-between gap-3">
                  <span className="min-w-0">
                    <span className="font-medium">{c.who}</span>
                    <span className="block text-foreground-secondary">{c.did}</span>
                  </span>
                  {c.took && <span className="shrink-0 text-muted-foreground tabular-nums">{c.took}</span>}
                </li>
              ))}
            </Group>
          )}
        </div>
      )}
    </div>
  )
}

/** @param {{ label: string, children: import('react').ReactNode }} props */
function Row({ label, children }) {
  return (
    <p className="m-0">
      <span className="text-muted-foreground">{label}: </span>{children}
    </p>
  )
}

/** @param {{ title: string, children: import('react').ReactNode }} props */
function Group({ title, children }) {
  return (
    <div className="flex flex-col gap-1">
      <p className="m-0 text-xs font-semibold tracking-wide text-muted-foreground uppercase">{title}</p>
      <ul className="m-0 flex list-none flex-col gap-1 p-0">{children}</ul>
    </div>
  )
}
