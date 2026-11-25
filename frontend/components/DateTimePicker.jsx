'use client'

import { useEffect, useRef, useState } from 'react'
import { CalendarClock } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Calendar } from '@/components/ui/calendar'
import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

/**
 * A date and time in the theme, in place of the browser's own picker (owner, 24 Nov 2026): the
 * month calendar, then wheels for hour, minute and am/pm. A wheel's values move through a fixed
 * band; the one in the band is chosen, and clicking a value brings it into the band. Hours and
 * minutes go round. `value` and `onChange` use the "2026-11-24T08:00" form of a datetime-local.
 */

const ROW = 36 // px: one value's height in a wheel
const SHOWN = 5 // rows in view; the middle one is the band
const pad = (n) => String(n).padStart(2, '0')

function parse(value) {
  const [date, time = '00:00'] = (value || '').split('T')
  const [y, m, d] = date.split('-').map(Number)
  const [h, min] = time.split(':').map(Number)
  return { day: new Date(y, (m || 1) - 1, d || 1), hour24: h || 0, minute: min || 0 }
}
function format({ day, hour24, minute }) {
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}T${pad(hour24)}:${pad(minute)}`
}

const HOURS = Array.from({ length: 12 }, (_, i) => ({ value: i + 1, label: String(i + 1) }))
const MINUTES = Array.from({ length: 60 }, (_, i) => ({ value: i, label: pad(i) }))
const HALVES = [{ value: 'am', label: 'AM' }, { value: 'pm', label: 'PM' }]

const calm = () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** One wheel: a scrolling list that settles on whole rows; `loop` repeats it so it goes round. */
function Wheel({ label, items, value, onChange, loop = false }) {
  const list = useRef(null)
  const placed = useRef(false)
  const settle = useRef(null)
  const copies = loop ? 3 : 1
  const n = items.length
  const rows = Array.from({ length: n * copies }, (_, i) => items[i % n])
  const at = (index) => (loop ? n + index : index) // a value's row in the middle copy

  // Opens with the current value in the band; after that the wheel leads and `value` follows it
  const startRow = at(Math.max(0, items.findIndex((it) => it.value === value)))
  const attach = (el) => {
    list.current = el
    if (el && !placed.current) {
      placed.current = true
      el.scrollTop = startRow * ROW
    }
  }

  useEffect(() => () => clearTimeout(settle.current), [])

  const onScroll = () => {
    clearTimeout(settle.current)
    settle.current = setTimeout(() => {
      const el = list.current
      if (!el) return
      let row = Math.round(el.scrollTop / ROW)
      // Gone into the first or last copy: jump to the same value in the middle one, unseen
      if (loop && (row < n || row >= 2 * n)) {
        row = n + (((row % n) + n) % n)
        el.scrollTop = row * ROW
      }
      const picked = rows[row]
      if (picked && picked.value !== value) onChange(picked.value)
    }, 90)
  }
  const goTo = (row) => list.current?.scrollTo({ top: row * ROW, behavior: calm() ? 'auto' : 'smooth' })
  const step = (by) => goTo(Math.round(list.current.scrollTop / ROW) + by)

  return (
    <div className="relative" style={{ height: ROW * SHOWN }}>
      {/* The band: whatever sits in it is chosen */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 rounded-md border border-primary/40 bg-primary-tint"
           style={{ top: ROW * Math.floor(SHOWN / 2), height: ROW }} />
      <div ref={attach} role="listbox" aria-label={label} tabIndex={0} onScroll={onScroll}
           onKeyDown={(e) => {
             if (e.key === 'ArrowDown') { e.preventDefault(); step(1) }
             if (e.key === 'ArrowUp') { e.preventDefault(); step(-1) }
           }}
           className="relative h-full w-14 snap-y snap-mandatory overflow-y-scroll rounded-md [scrollbar-width:none] focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none [&::-webkit-scrollbar]:hidden [mask-image:linear-gradient(to_bottom,transparent,black_30%,black_70%,transparent)]"
           style={{ paddingBlock: ROW * Math.floor(SHOWN / 2) }}>
        {rows.map((it, i) => (
          <div key={i} role="option" aria-selected={it.value === value} onClick={() => goTo(i)}
               className="flex snap-center cursor-pointer items-center justify-center font-mono text-sm tabular-nums text-muted-foreground aria-selected:font-medium aria-selected:text-primary"
               style={{ height: ROW }}>
            {it.label}
          </div>
        ))}
      </div>
    </div>
  )
}

const shownAs = (value) => {
  const { day, hour24, minute } = parse(value)
  const date = day.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
  return `${date}, ${hour24 % 12 || 12}:${pad(minute)} ${hour24 >= 12 ? 'pm' : 'am'}`
}

/**
 * The picker around an area of a form (`children`), opened by a DateTimeField inside it. It opens
 * right under (or over) the field, centred across the area: anchored to a strip as wide as the
 * area on the field's row (owner, 24 Nov 2026).
 */
export default function DateTimePicker({ value, onChange, children }) {
  const [open, setOpen] = useState(false)
  const [row, setRow] = useState(null)
  const area = useRef(null)
  const { day, hour24, minute } = parse(value)
  const half = hour24 >= 12 ? 'pm' : 'am'
  const hour12 = hour24 % 12 || 12
  const set = (next) => onChange(format({ day, hour24, minute, ...next }))

  const onOpenChange = (next) => {
    const field = next && area.current?.querySelector('[aria-haspopup="dialog"]')
    if (field) {
      const a = area.current.getBoundingClientRect()
      const f = field.getBoundingClientRect()
      setRow({ top: f.top - a.top, height: f.height })
    }
    setOpen(next)
  }

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <div ref={area} className="relative">
        {children}
        <PopoverAnchor asChild>
          <div aria-hidden="true" className="pointer-events-none absolute inset-x-0" style={row ?? { top: 0, height: 0 }} />
        </PopoverAnchor>
      </div>
      <PopoverContent align="center" sideOffset={6} collisionPadding={16} className="w-auto p-3">
        <div className="flex flex-col gap-3 sm:flex-row">
          <Calendar mode="single" selected={day} defaultMonth={day} className="p-0 [--cell-size:--spacing(9)]"
                    onSelect={(picked) => picked && set({ day: picked })} />
          <div className="flex items-center justify-center gap-1.5 sm:border-l sm:pl-3">
            <Wheel label="Hour" items={HOURS} value={hour12} loop
                   onChange={(h) => set({ hour24: (h % 12) + (half === 'pm' ? 12 : 0) })} />
            <span aria-hidden="true" className="font-mono text-muted-foreground">:</span>
            <Wheel label="Minute" items={MINUTES} value={minute} loop onChange={(m) => set({ minute: m })} />
            <Wheel label="AM or PM" items={HALVES} value={half}
                   onChange={(p) => set({ hour24: (hour24 % 12) + (p === 'pm' ? 12 : 0) })} />
          </div>
        </div>
        <div className="mt-3 flex justify-end">
          <Button type="button" size="sm" onClick={() => setOpen(false)}>Done</Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}

/** The field showing the chosen date and time; it opens the picker it sits in. */
export function DateTimeField({ id, value }) {
  return (
    <PopoverTrigger asChild>
      <Button id={id} type="button" variant="outline"
              className="w-full justify-between border-input font-normal text-(length:--control-text) md:text-sm">
        {shownAs(value)}
        <CalendarClock className="text-muted-foreground" />
      </Button>
    </PopoverTrigger>
  )
}
