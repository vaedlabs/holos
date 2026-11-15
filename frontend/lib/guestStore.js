/**
 * A guest's data, kept in this browser only (Plan C.8, P5.2; Part E #50, #61).
 *
 *   const store = guestStore()                       // localStorage
 *   const input = store.chatInput(message)           // message + profile + last 6 turns
 *   store.recordTurn(events)                         // after `done`: history, cards, logs
 *   await store.confirm(id, { at, meal, leftOut })   // a held entry, dated as confirmed
 *   store.discard(id)                                // "Don't log"
 *   await store.clearMyData()                        // nothing left; the session ends
 *
 * The server keeps nothing for a guest: the profile and the last 6 turns go with each
 * message, and what the person logs stays here until they import it into an account
 * (C.18). One JSON record in localStorage (owner, 15 Nov 2026: no IndexedDB), kept under
 * 3 MB by dropping the oldest answers' displays, then the oldest traces.
 *
 * A held entry waits with no time limit; a newer one of its kind replaces the waiting
 * ones from earlier turns; one turn's entries of a kind wait together (C.17). It is
 * logged only if the profile is the one it was checked against (`profile_hash`, the
 * server's sha256 of the profile as compact JSON with sorted keys).
 *
 * Each exchange is kept as the server sent it, signed (Part E #63): the message as the
 * server took it and the answer with `sig`, `prev` and `shown`. Changing either here
 * makes the server refuse it, and everything before it, in chats and at import.
 */

import { signOut } from './api'

const KEY = 'holos.guest.v1'
export const LIMITS = {
  turnsSent: 6, // ChatPayload.guest_history
  traces: 20,
  bytes: 3_000_000,
  importBytes: 1024 * 1024, // limits.IMPORT_BYTES
  importTurns: 50, // limits.IMPORT_TURNS
  importLogs: 500, // limits.IMPORT_LOG_ENTRIES
  daysBack: 30, // limits.LOG_DATE_BACK
  minutesAhead: 5, // limits.LOG_DATE_AHEAD
}
// What a saved turn keeps (C.5 History): the events that show the person something
const SHOWN = new Set(['section_start', 'text', 'item', 'sources', 'section_end',
                       'pending_write', 'committed', 'logged_note', 'crisis', 'notice'])
const EMPTY_PROFILE = { condition_ids: [], allergen_tags: [], diet_tags: [], notes: '' }

export const MESSAGES = {
  profile_changed: 'Your profile changed since this was checked, so it was not logged. ' +
                   'Log it again if you still want it.',
  bad_date: `Choose a date and time in the last ${LIMITS.daysBack} days, not in the future.`,
  bad_left_out: 'Only what the warning names can be left out.',
  not_found: 'There is no such entry to confirm.',
}

/** JSON as Python writes it with sort_keys and compact separators, non-ASCII kept. */
export function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort()
      .map((k) => `${JSON.stringify(k)}:${canonical(value[k])}`).join(',')}}`
  }
  return JSON.stringify(value ?? null)
}

/** The server's `profile_hash` of a guest profile (staging.profile_hash). */
export async function profileHash(profile) {
  const bytes = new TextEncoder().encode(canonical(profile ?? null))
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

/** A profile with every field, as the server's model dumps it (the hash depends on it). */
export function fullProfile(profile) {
  return profile ? { ...EMPTY_PROFILE, ...profile } : null
}

const fresh = () => ({ version: 1, profile: null, turns: [], pending: [], logs: [], traces: [] })

export function guestStore(storage = globalThis.localStorage,
                           { now = () => new Date(), endSession = signOut } = {}) {
  const read = () => {
    try {
      const data = JSON.parse(storage.getItem(KEY))
      return data?.version === 1 ? data : fresh()
    } catch {
      return fresh() // unreadable: start again rather than fail the chat
    }
  }

  const write = (data) => {
    fit(data, LIMITS.bytes)
    for (;;) {
      try {
        storage.setItem(KEY, JSON.stringify(data))
        return data
      } catch (error) {
        if (!trimOldest(data)) throw error // the browser's quota is smaller still
      }
    }
  }

  const setCard = (data, entry, state) => {
    const turn = data.turns.find((t) => t.trace_id === entry.turn)
    const card = turn?.display?.[entry.card]
    if (card?.event === 'pending_write') card.data.state = state
  }

  return {
    data: read,

    profile: () => read().profile,

    /** Saves the profile; held entries checked against another profile can't be logged. */
    async setProfile(profile) {
      const data = read()
      data.profile = fullProfile(profile)
      const hash = await profileHash(data.profile)
      for (const entry of data.pending.filter((p) => p.profile_hash !== hash)) {
        setCard(data, entry, 'closed')
      }
      data.pending = data.pending.filter((p) => p.profile_hash === hash)
      write(data)
    },

    /** The chat request's guest fields (C.8): the profile and the last 6 turns. */
    chatInput(message, extra = {}) {
      const data = read()
      const history = data.turns.slice(-LIMITS.turnsSent).map(historyTurn)
      return { message, guest_profile: data.profile, guest_history: history, ...extra }
    },

    /** A finished turn (`done`): the signed exchange, what was shown, logs and held entries. */
    recordTurn(events) {
      const done = events.find((e) => e.name === 'done')
      if (!done?.data.turn || !done.data.said) return
      const data = read()
      const traceId = done.data.trace_id
      const display = events.filter((e) => SHOWN.has(e.name)).map(({ name, data: d }) => {
        const { seq, trace_id, ...shown } = d
        return { event: name, data: name === 'pending_write' ? { ...shown, state: 'waiting' }
                                                               : shown }
      })
      data.turns.push(done.data.said) // the server's copy, as signed: never rewritten here
      data.turns.push({ ...done.data.turn, trace_id: traceId, display })

      for (const write of events.filter((e) => e.name === 'committed')
        .flatMap((e) => e.data.writes)) {
        if (write.entry) data.logs.push({ entry: write.entry, at: write.at ?? done.data.turn.ts })
      }
      const held = display.flatMap((e, card) => (e.event === 'pending_write'
        ? [{ id: `${traceId}:${card}`, turn: traceId, card, kind: e.data.entry.kind, ...e.data }]
        : []))
      const kinds = new Set(held.map((h) => h.kind))
      for (const old of data.pending.filter((p) => kinds.has(p.kind))) {
        setCard(data, old, 'replaced')
      }
      data.pending = [...data.pending.filter((p) => !kinds.has(p.kind)), ...held]
      if (done.data.trace) data.traces = [...data.traces, done.data.trace].slice(-LIMITS.traces)
      write(data)
    },

    pending: () => read().pending,

    /**
     * Logs a held entry as the person confirms it: when it happened (`at`, a Date or ISO
     * string with its zone), a meal's meal, and what they left out of its warnings.
     */
    async confirm(id, { at, meal, leftOut = [] } = {}) {
      const data = read()
      const entry = data.pending.find((p) => p.id === id)
      if (!entry) return { ok: false, code: 'not_found', message: MESSAGES.not_found }
      if (entry.profile_hash !== await profileHash(data.profile)) {
        data.pending = data.pending.filter((p) => p.id !== id)
        setCard(data, entry, 'closed')
        write(data)
        return { ok: false, code: 'profile_changed', message: MESSAGES.profile_changed }
      }
      if (!leftOut.every((a) => entry.attributes.includes(a))) {
        return { ok: false, code: 'bad_request', message: MESSAGES.bad_left_out }
      }
      const when = new Date(at ?? entry.at)
      const nowMs = now().getTime()
      if (Number.isNaN(when.getTime()) || when.getTime() > nowMs + LIMITS.minutesAhead * 60_000
          || when.getTime() < nowMs - LIMITS.daysBack * 86_400_000) {
        return { ok: false, code: 'bad_date', message: MESSAGES.bad_date }
      }
      const logged = {
        ...entry.entry,
        args: meal && entry.entry.kind === 'meal' ? { ...entry.entry.args, meal } : entry.entry.args,
        warnings: entry.entry.warnings.map((w) => (w.kind === 'conflict'
          && w.attributes.some((a) => leftOut.includes(a)) ? { ...w, left_out: true } : w)),
        at: when.toISOString(),
        time_guessed: false,
      }
      data.logs.push({ entry: logged, at: when.toISOString() })
      data.pending = data.pending.filter((p) => p.id !== id)
      setCard(data, entry, 'logged')
      write(data)
      return { ok: true, entry: logged }
    },

    /** "Don't log": the entry goes, and its card says so. */
    discard(id) {
      const data = read()
      const entry = data.pending.find((p) => p.id === id)
      if (!entry) return
      data.pending = data.pending.filter((p) => p.id !== id)
      setCard(data, entry, 'discarded')
      write(data)
    },

    /** POST /account/import (C.18): within its limits, the newest displays that fit. */
    importBody(importId = crypto.randomUUID()) {
      const data = read()
      const history = data.turns.slice(-LIMITS.importTurns).map((t) => ({
        ...historyTurn(t), ...(t.role === 'assistant' && t.display ? { display: t.display } : {}),
      }))
      const body = { import_id: importId, profile: data.profile, history,
                     logs: data.logs.slice(-LIMITS.importLogs) }
      for (let i = 0; i < history.length && size(body) > LIMITS.importBytes; i++) {
        delete history[i].display // the oldest go as text only
      }
      return body
    },

    /** "Clear my data": nothing left in this browser, and the guest session ends. */
    async clearMyData() {
      storage.removeItem(KEY)
      await endSession()
    },
  }
}

/** A turn as the server reads it (HistoryTurn), exactly as signed: no display, no trace ID. */
function historyTurn({ role, content, agents, ts, sig, prev, shown }) {
  if (role === 'user') return { role, content, ts }
  return { role, content, agents: agents ?? null, ts, sig: sig ?? null, prev: prev ?? null,
           shown: shown ?? null }
}

const size = (value) => new TextEncoder().encode(JSON.stringify(value)).length

/** Under `limit`: the oldest answers' displays first, then the oldest traces. */
function fit(data, limit) {
  let trimmed = true
  while (trimmed && size(data) > limit) trimmed = trimOldest(data)
}

function trimOldest(data) {
  const turn = data.turns.find((t) => t.display)
  if (turn) {
    turn.display = null
    return true
  }
  if (data.traces.length) {
    data.traces.shift()
    return true
  }
  return false
}
