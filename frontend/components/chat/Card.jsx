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
