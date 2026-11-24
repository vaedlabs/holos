'use client'

import { useId, useState } from 'react'
import { Check } from 'lucide-react'

import { Input } from '@/components/ui/input'
import { Toggle } from '@/components/ui/toggle'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'

/**
 * Pick any of `options`, plus your own under Other, as one comma-separated `value` (the
 * preferences fields). An option that conflicts with one already picked (`conflicts`, e.g.
 * Vegan and Pescatarian) can't be picked, and says why. The picked options are read from
 * `value` each render; only the Other text is kept here, as typed.
 */

const split = (text) => (text ? text.split(',').map((v) => v.trim()).filter(Boolean) : [])
const same = (a, b) => a.toLowerCase() === b.toLowerCase()

// The picked look from the chosen design: the primary tint, its outline and a check
const PICKED = 'data-[state=on]:border-primary data-[state=on]:bg-primary-tint data-[state=on]:text-primary'

export default function ButtonSelector({
  label, options, value, onChange, placeholder = 'Type comma-separated values...', conflicts = {},
}) {
  const id = useId()
  const parts = split(value)
  const picked = options.filter((o) => parts.some((p) => same(p, o)))
  const others = parts.filter((p) => !options.some((o) => same(p, o)))
  const [otherOpen, setOtherOpen] = useState(others.length > 0)
  const [otherText, setOtherText] = useState(others.join(', '))

  const emit = (nextPicked, nextOther, open) => {
    onChange([...nextPicked, ...(open ? split(nextOther) : [])].join(', '))
  }
  const blockedBy = (option) => picked.find((p) => (conflicts[p] || []).includes(option))
  const blocked = options.filter((o) => !picked.includes(o) && blockedBy(o))

  return (
    <div role="group" aria-labelledby={`${id}-label`} className="flex flex-col gap-2.5">
      <p id={`${id}-label`} className="m-0 text-sm font-medium">{label}</p>
      <div className="flex flex-wrap gap-2">
        <ToggleGroup type="multiple" variant="outline" spacing={2} className="contents"
                     value={picked} onValueChange={(next) => emit(options.filter((o) => next.includes(o)), otherText, otherOpen)}>
          {options.map((option) => (
            <ToggleGroupItem key={option} value={option} disabled={Boolean(blockedBy(option))}
                             className={`rounded-full ${PICKED}`}>
              {picked.includes(option) && <Check aria-hidden="true" />}
              {option}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <Toggle variant="outline" pressed={otherOpen} className={`rounded-full ${PICKED}`}
                onPressedChange={(open) => {
                  setOtherOpen(open)
                  emit(picked, otherText, open)
                }}>
          {otherOpen && <Check aria-hidden="true" />}
          Other
        </Toggle>
      </div>
      {blocked.length > 0 && (
        <p className="m-0 text-sm text-muted-foreground">
          {blocked.map((o) => `${o} can't go with ${blockedBy(o)}`).join('; ')}.
        </p>
      )}
      {otherOpen && (
        <Input aria-label={`${label}: other`} value={otherText} placeholder={placeholder}
               onChange={(e) => {
                 setOtherText(e.target.value)
                 emit(picked, e.target.value, true)
               }} />
      )}
    </div>
  )
}
