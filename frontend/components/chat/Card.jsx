'use client'

import { useState } from 'react'

/**
 * An entry's card (C.17; Part E #50, #58). Logged: its "Logged" line, or the coach's
 * sentence about it once that arrives. Held: what conflicts, then Confirm with the date,
 * time and (a meal) the meal it happened, and what the person left out; or "Don't log".
 * Only a waiting card can be decided; every other state says what happened.
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

export default function Card({ card, onConfirm, onDiscard }) {
  if (card.type === 'logged') {
    return (
      <div className="chat-card chat-card-logged">
        <p>{card.note || card.summary}</p>
        {card.warnings.map((w, i) => <p key={i} className="chat-caveat">{w}</p>)}
      </div>
    )
  }
  return <HeldCard card={card} onConfirm={onConfirm} onDiscard={onDiscard} />
}

function HeldCard({ card, onConfirm, onDiscard }) {
  const [state, setState] = useState(card.state)
  const [when, setWhen] = useState(() => localInput(card.at))
  const [meal, setMeal] = useState(card.meal)
  const [leftOut, setLeftOut] = useState([])
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

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
  const toggle = (a) => setLeftOut((now) => (now.includes(a) ? now.filter((x) => x !== a)
                                                              : [...now, a]))
  return (
    <div className={`chat-card chat-card-held chat-card-${state}`}>
      <p className="chat-card-summary">{card.summary}</p>
      {card.warnings.map((w, i) => <p key={i} className="chat-caveat">{w}</p>)}
      {state !== 'waiting' ? (
        <p className="chat-card-state">{STATES[state]}</p>
      ) : (
        <div className="chat-card-form">
          <label>
            When
            <input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />
          </label>
          {card.time_guessed && <span className="chat-hint">No time was given: pick when.</span>}
          {card.meal && (
            <label>
              Meal
              <select value={meal} onChange={(e) => setMeal(e.target.value)}>
                {MEALS.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </label>
          )}
          {card.attributes?.length > 0 && (
            <fieldset>
              <legend>I left out</legend>
              {card.attributes.map((a) => (
                <label key={a}>
                  <input type="checkbox" checked={leftOut.includes(a)} onChange={() => toggle(a)} />
                  {a.replace('_', ' ')}
                </label>
              ))}
            </fieldset>
          )}
          <div className="chat-card-actions">
            <button type="button" className="btn btn-primary" disabled={busy} onClick={confirm}>
              Confirm
            </button>
            <button type="button" className="btn btn-outline" disabled={busy}
                    onClick={() => decide(() => onDiscard(card))}>
              Don&apos;t log
            </button>
          </div>
        </div>
      )}
      {message && <p className="chat-card-message">{message}</p>}
    </div>
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
        if (result.state) setStates((now) => now.map((s, j) => (j === i ? result.state : s)))
        if (replace && result.state === 'logged') setSwapped((now) => [...now, i])
        if (result.message && !result.state) setMessages((now) => [...now, result.message])
      }
    } finally {
      setBusy(false)
    }
  }
  const confirm = (replace) => decide((card) => onConfirm(card, {
    at: card.at, meal: card.meal ?? undefined, replace }), replace)

  return (
    <div className="chat-card chat-card-held chat-card-repeat">
      <ul className="chat-card-repeats">
        {cards.map((c, i) => (
          <li key={c.index ?? i}>
            <p className="chat-card-summary">{c.summary} · {whenShort(c.at)}</p>
            <p className="chat-hint">
              {c.repeat_of.this_turn ? 'Also earlier in this answer.'
                : `Already logged: ${c.repeat_of.summary} · ${whenShort(c.repeat_of.at)}`}
            </p>
            {states[i] !== 'waiting' && (
              <p className="chat-card-state">
                {swapped.includes(i) ? REPLACED_EARLIER : STATES[states[i]]}
              </p>
            )}
          </li>
        ))}
      </ul>
      {waiting.length > 0 && (
        <div className="chat-card-actions">
          <span>{waiting.length === 1 ? 'Log it again?' : 'Log them again?'}</span>
          <button type="button" className="btn btn-primary" disabled={busy}
                  onClick={() => confirm(false)}>Log again</button>
          {replaceable && (
            <button type="button" className="btn btn-outline" disabled={busy}
                    onClick={() => confirm(true)}>
              {waiting.length === 1 ? 'Replace the earlier one' : 'Replace the earlier ones'}
            </button>
          )}
          <button type="button" className="btn btn-outline" disabled={busy}
                  onClick={() => decide(onDiscard)}>Don&apos;t log</button>
        </div>
      )}
      {messages.map((m, i) => <p key={i} className="chat-card-message">{m}</p>)}
    </div>
  )
}
