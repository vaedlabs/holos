// @ts-check
'use client'

import { Trash2 } from 'lucide-react'

import { Caution } from '@/components/chat/Items'
import { Button } from '@/components/ui/button'
import { logWhen, warningNotes } from '@/lib/logs'

/** One log: its title and details, what was left out and the conflicts confirmed, when it happened,
 * its notes, and Delete (`name`: what Delete calls it, when the title is only its kind, e.g. "Breakfast"). */
/**
 * @param {{ title: string, name?: string, detail?: string, when: string, notes?: string | null,
 *   warnings?: import('@/lib/logs').WriteWarning[], onDelete: () => void,
 *   children?: import('react').ReactNode }} props
 */
export default function LogItem({ title, name = title, detail, when, notes, warnings, onDelete, children }) {
  const { without, confirmed } = warningNotes(warnings)
  return (
    <li className="flex gap-3 rounded-lg border bg-card p-3">
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <p className="m-0 font-medium">{title}</p>
        {detail && <p className="m-0 text-sm text-foreground-secondary tabular-nums">{detail}</p>}
        {children}
        {without.map((w) => <p key={w} className="m-0 text-sm text-foreground-secondary">{w}</p>)}
        {confirmed.map((reason) => <Caution key={reason}>{reason}. You confirmed this entry.</Caution>)}
        {notes && <p className="m-0 text-sm text-foreground-secondary">{notes}</p>}
        <p className="m-0 text-xs text-muted-foreground">{logWhen(when)}</p>
      </div>
      <Button type="button" variant="ghost" size="icon-sm" aria-label={`Delete ${name}`}
              className="shrink-0 text-muted-foreground hover:text-destructive" onClick={onDelete}>
        <Trash2 />
      </Button>
    </li>
  )
}

/** A tab's list, or what to say when it's empty. */
/** @param {{ empty: string, children?: import('react').ReactNode }} props */
export function LogList({ empty, children }) {
  const items = [children].flat().filter(Boolean)
  if (items.length === 0) return <p className="m-0 py-8 text-center text-sm text-muted-foreground">{empty}</p>
  return <ul className="m-0 flex list-none flex-col gap-2 p-0">{children}</ul>
}
