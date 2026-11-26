// @ts-check
'use client'

import { TriangleAlert } from 'lucide-react'

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { byDay } from '@/lib/turnView'

/**
 * A coach's items (P5.3): a plan over several days is a table by day, a single session a
 * list. Each row is what the coach gave and the gate kept: its text (`display`), its note,
 * and the cautions the gate added.
 */
/** @typedef {import('@/lib/turnView').Item} Item */

/** @param {{ items: Item[] }} props */
export default function Items({ items }) {
  const days = byDay(items)
  if (days.length === 1 && !days[0].day) {
    return (
      <ul className="m-0 flex list-none flex-col divide-y rounded-lg border bg-card p-0">
        {items.map((item, i) => (
          <li key={i} className="flex flex-col gap-0.5 px-3 py-2.5">
            <span className="font-medium">{item.display}</span>
            <Detail item={item} />
          </li>
        ))}
      </ul>
    )
  }
  return (
    <div className="rounded-lg border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Day</TableHead>
            <TableHead>What</TableHead>
            <TableHead>How</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {days.flatMap(({ day, items: rows }) => rows.map((item, i) => (
            <TableRow key={`${day}-${i}`}>
              {i === 0 && (
                <th scope="row" rowSpan={rows.length}
                    className="border-r px-2 align-top font-medium whitespace-nowrap">{day || '—'}</th>
              )}
              <TableCell className="whitespace-normal">{item.display}</TableCell>
              <TableCell className="whitespace-normal"><Detail item={item} /></TableCell>
            </TableRow>
          )))}
        </TableBody>
      </Table>
    </div>
  )
}

/** @param {{ item: Item }} props */
function Detail({ item }) {
  return (
    <>
      {item.note && <span className="block text-sm text-foreground-secondary">{item.note}</span>}
      {item.caveats.map((c, i) => <Caution key={i}>{c}</Caution>)}
    </>
  )
}

/** A caution the gate added: never folded away, and marked by an icon as well as its colour (C.6). */
/** @param {{ children: import('react').ReactNode }} props */
export function Caution({ children }) {
  return (
    <span className="flex items-start gap-1.5 text-sm text-caution">
      <TriangleAlert aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
      <span>{children}</span>
    </span>
  )
}
