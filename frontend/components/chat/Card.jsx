'use client'

import { useState } from 'react'
import { Ban, Check, CircleCheck, RefreshCw, X } from 'lucide-react'

import ApprovalCard from '@/components/ai/ApprovalCard'
import DateTimePicker, { DateTimeField } from '@/components/DateTimePicker'
import ToolChip from '@/components/ai/ToolChip'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Field, FieldDescription, FieldLabel, FieldLegend, FieldSet } from '@/components/ui/field'
import { Label } from '@/components/ui/label'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'

import { Caution } from './Items'

/**
 * An entry's card (C.17; Part E #50, #58). Logged: its "Logged" line, or the coach's
 * sentence about it once that arrives. Held: what conflicts, then Confirm with the date,
 * time and (a meal) the meal it happened, and what the person left out; or "Don't log".
 * Only a waiting card can be decided; every other state says what happened, in one chip.
 */

export const MEALS = ['breakfast', 'lunch', 'dinner', 'snack']
export const STATES = {
  logged: 'Logged.',
  discarded: 'Not logged.',
  replaced: 'A newer entry replaced this one.',
  blocked: "Not logged: it doesn't fit your profile now.",
  closed: "This can't be confirmed any more.",
}

/** "2026-11-15T09:30:00Z" as the person's own "2026-11-15T15:00" (a datetime-local). */
export function localInput(iso) {
  const d = new Date(iso)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// What happened to a decided entry, always as the same chip so every settled card reads alike;
// the icon says which (owner, 24 Nov 2026)
const DECIDED_ICONS = { logged: Check, discarded: X, replaced: RefreshCw, blocked: Ban, closed: Ban }
function Decided({ state, text }) {
  return <ToolChip icon={DECIDED_ICONS[state] ?? Check}>{text}</ToolChip>
}

export default function Card({ card, onConfirm, onDiscard }) {
  if (card.type === 'logged') {
    return (
      <div className="flex flex-col gap-1.5">
        {card.note ? (
          // The coach's sentence about it, in place of the "Logged" line (#58): a sentence, so not a pill
          <p className="m-0 flex items-start gap-2">
            <CircleCheck aria-hidden="true" className="mt-0.5 size-4.5 shrink-0 text-primary" />
            {card.note}
          </p>
        ) : <ToolChip>{card.summary}</ToolChip>}
        {card.warnings.map((w, i) => <Caution key={i}>{w}</Caution>)}
      </div>
    )
  }
  return <HeldCard card={card} onConfirm={onConfirm} onDiscard={onDiscard} />
}

function HeldCard({ card, onConfirm, onDiscard }) {
  const [state, setState] = useState(card.state)
  // Settled elsewhere (a newer entry replaced it): the new state shows at once, keeping what this
  // card said itself (D064, D067); React's "adjust state when a prop changes"
  const [given, setGiven] = useState(card.state)
  if (card.state !== given) {
    setGiven(card.state)
    setState(card.state)
  }
  const [when, setWhen] = useState(() => localInput(card.at))
  const [meal, setMeal] = useState(card.meal)
  const [leftOut, setLeftOut] = useState([])
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const id = `entry-${card.write_id ?? card.index}`

  const decide = async (action) => {
    setBusy(true)
    setMessage('')
    try {
      const result = await action()
      if (result.state) setState(result.state)
      setMessage(result.message || '')
    } finally {
      setBusy(false)
    }
  }
  const confirm = () => decide(() => onConfirm(card, {
    at: new Date(when).toISOString(), meal: card.meal ? meal : undefined, leftOut }))
  const toggle = (a) => setLeftOut((prev) => (prev.includes(a) ? prev.filter((x) => x !== a)
                                                                : [...prev, a]))
  const waiting = state === 'waiting'

  return (
    <ApprovalCard
      eyebrow="Check before logging"
      title={card.summary}
      status={waiting
        ? message && <p role="alert" className="m-0 text-sm text-destructive">{message}</p>
        : <Decided state={state} text={message || STATES[state]} />}
      actions={waiting && (
        <>
          <Button type="button" disabled={busy} onClick={confirm}>Confirm</Button>
          <Button type="button" variant="outline" disabled={busy}
                  onClick={() => decide(() => onDiscard(card))}>
            Don&apos;t log
          </Button>
        </>
      )}>
      {card.warnings.map((w, i) => <Caution key={i}>{w}</Caution>)}
      {waiting && (
        // The date picker opens by the When field, centred across this area, which spans the card
        <DateTimePicker value={when} onChange={setWhen}>
          <div className="grid gap-4 sm:grid-cols-2">
            {/* Alone on its row (no meal), it takes the whole row */}
            <Field className={card.meal ? undefined : 'sm:col-span-2'}>
              <FieldLabel htmlFor={`${id}-when`}>When</FieldLabel>
              <DateTimeField id={`${id}-when`} value={when} />
              {card.time_guessed && <FieldDescription>No time was given: pick when.</FieldDescription>}
            </Field>
            {card.meal && (
              <Field>
                <FieldLabel htmlFor={`${id}-meal`}>Meal</FieldLabel>
                <NativeSelect id={`${id}-meal`} className="w-full" value={meal}
                              onChange={(e) => setMeal(e.target.value)}>
                  {MEALS.map((m) => <NativeSelectOption key={m} value={m}>{m}</NativeSelectOption>)}
                </NativeSelect>
              </Field>
            )}
            {card.attributes?.length > 0 && (
              <FieldSet className="sm:col-span-2">
                <FieldLegend variant="label">I left out</FieldLegend>
                <div className="flex flex-wrap gap-x-4 gap-y-2">
                  {card.attributes.map((a) => (
                    <div key={a} className="flex items-center gap-2">
                      <Checkbox id={`${id}-${a}`} checked={leftOut.includes(a)} onCheckedChange={() => toggle(a)} />
                      <Label htmlFor={`${id}-${a}`}>{a.replace('_', ' ')}</Label>
                    </div>
                  ))}
                </div>
              </FieldSet>
            )}
          </div>
        </DateTimePicker>
      )}
    </ApprovalCard>
  )
}

// After Replace; a reload shows the card's saved state, "Logged."
export const REPLACED_EARLIER = 'Logged; the earlier one was removed.'

/** "7:00 am", or "Sun 15 Nov, 7:00 am" on another day, in the person's own zone. */
export function whenShort(iso, now = new Date()) {
  const d = new Date(iso)
  const time = d.toLocaleTimeString('en-GB', { hour: 'numeric', minute: '2-digit', hour12: true })
  if (d.toDateString() === now.toDateString()) return time
  const day = d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })
  return `${day}, ${time}`
}

/**
 * Entries that repeat one already logged, all of an answer's on one card (C.17; Part E
 * #67): each with its time and the entry it repeats, since a correction differs only in
 * that time; Log again, Replace the earlier ones (only when each has one already saved)
 * or Don't log, for all that still wait.
 */
export function RepeatCard({ cards, onConfirm, onDiscard }) {
  const [states, setStates] = useState(() => cards.map((c) => c.state))
  const given = cards.map((c) => c.state).join()
  const [seen, setSeen] = useState(given)
  if (given !== seen) { // settled elsewhere, as for a held card
    setSeen(given)
    setStates(cards.map((c) => c.state))
  }
  const [swapped, setSwapped] = useState([]) // logged by Replace, this visit
  const [messages, setMessages] = useState([])
  const [busy, setBusy] = useState(false)
  const waiting = cards.filter((_, i) => states[i] === 'waiting')
  const replaceable = waiting.length > 0 && waiting.every((c) => c.repeat_of.log_id)

  const decide = async (action, replace = false) => {
    setBusy(true)
    setMessages([])
    try {
      for (const [i, card] of cards.entries()) {
        if (states[i] !== 'waiting') continue
        const result = await action(card)
        if (result.state) setStates((prev) => prev.map((s, j) => (j === i ? result.state : s)))
        if (replace && result.state === 'logged') setSwapped((prev) => [...prev, i])
        if (result.message && !result.state) setMessages((prev) => [...prev, result.message])
      }
    } finally {
      setBusy(false)
    }
  }
  const confirm = (replace) => decide((card) => onConfirm(card, {
    at: card.at, meal: card.meal ?? undefined, replace }), replace)

  return (
    <ApprovalCard
      aria-label="Possible repeat"
      eyebrow="Possible repeat"
      status={messages.length > 0 && messages.map((m, i) => (
        <p key={i} role="alert" className="m-0 text-sm text-destructive">{m}</p>
      ))}
      actions={waiting.length > 0 && (
        <>
          <span className="mr-auto text-sm font-medium">
            {waiting.length === 1 ? 'Log it again?' : 'Log them again?'}
          </span>
          {/* Replace leads when it can be done (owner, 25 Nov 2026): right for a correction, and
              harmless for a repeat said twice; Log again stays a click away */}
          {replaceable && (
            <Button type="button" disabled={busy} onClick={() => confirm(true)}>
              {waiting.length === 1 ? 'Replace the earlier one' : 'Replace the earlier ones'}
            </Button>
          )}
          <Button type="button" variant={replaceable ? 'outline' : 'default'} disabled={busy}
                  onClick={() => confirm(false)}>
            Log again
          </Button>
          <Button type="button" variant="ghost" disabled={busy} onClick={() => decide(onDiscard)}>
            Don&apos;t log
          </Button>
        </>
      )}>
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {cards.map((c, i) => (
          <li key={c.index ?? i} className="flex flex-col gap-1">
            {/* The same title as a held card's */}
            <h4 className="m-0 font-heading text-base font-semibold">
              {c.summary} · {whenShort(c.at)}
            </h4>
            <p className="m-0 text-sm text-foreground-secondary">
              {c.repeat_of.this_turn ? 'Also earlier in this answer.'
                : `Already logged: ${c.repeat_of.summary} · ${whenShort(c.repeat_of.at)}`}
            </p>
            {states[i] !== 'waiting' && (
              // mt-2 on the row's gap-1: the chip sits as far below its lines as on a held card (gap-3)
              <div className="mt-2">
                <Decided state={states[i]}
                         text={swapped.includes(i) ? REPLACED_EARLIER : STATES[states[i]]} />
              </div>
            )}
          </li>
        ))}
      </ul>
    </ApprovalCard>
  )
}
