'use client'

import { useId, useState } from 'react'
import { Check } from 'lucide-react'

import { Input } from '@/components/ui/input'
import { optionLabel } from '@/lib/preferenceOptions'

/**
 * Pick any of `options`, plus your own under Other, as one comma-separated `value` (the
 * preferences fields). An option that conflicts with one already picked (`conflicts`, e.g.
 * Vegan and Pescatarian) can't be picked, and says why. The picked options are read from
 * `value` each render; only the Other text is kept here, as typed.
 */

const split = (text) => (text ? text.split(',').map((v) => v.trim()).filter(Boolean) : [])
const same = (a, b) => a.toLowerCase() === b.toLowerCase()

export default function ButtonSelector({
  label, options, value, onChange, placeholder = 'Type comma-separated values...', conflicts = {},
  optional = false,
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
      <p id={`${id}-label`} className="m-0 text-sm font-medium">
        {/* ml-2: the gap a FieldLabel leaves before its "(optional)" */}
        {label}{optional && <span className="ml-2 font-normal text-muted-foreground">(optional)</span>}
      </p>
      <div className="flex flex-wrap gap-2">
        {/* The theme's chip (app/theme.css), as the health profile's pickers */}
        {options.map((option) => {
          const on = picked.includes(option)
          return (
            <label key={option} className="chip">
              <input type="checkbox" className="sr-only" checked={on} disabled={Boolean(blockedBy(option))}
                     onChange={() => emit(options.filter((o) => (o === option ? !on : picked.includes(o))),
                                          otherText, otherOpen)} />
              {on && <Check aria-hidden="true" />}
              {optionLabel(option)}
            </label>
          )
        })}
        <label className="chip">
          <input type="checkbox" className="sr-only" checked={otherOpen}
                 onChange={(e) => {
                   setOtherOpen(e.target.checked)
                   emit(picked, otherText, e.target.checked)
                 }} />
          {otherOpen && <Check aria-hidden="true" />}
          Other
        </label>
      </div>
      {blocked.length > 0 && (
        <p className="m-0 text-sm text-muted-foreground">
          {blocked.map((o) => `${optionLabel(o)} can't go with ${optionLabel(blockedBy(o))}`).join('; ')}.
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
