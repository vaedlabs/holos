// @ts-check
/**
 * A guest's data, kept in this browser only (Plan C.8, P5.2; Part E #50, #61).
 *
 *   const store = guestStore()                       // localStorage
 *   const input = store.chatInput(message)           // message + profile + last 6 turns
 *   const replaced = store.recordTurn(events)        // after `done`: history, cards, logs
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

/**
 * @typedef {import('../types/app').ChatEvent} ChatEvent
 * @typedef {import('../types/app').ShownEvent} ShownEvent
 * @typedef {import('../types/app').CardData} CardData
 * @typedef {import('../types/contracts').HistoryTurn} HistoryTurn
 * @typedef {import('../types/contracts').UserProfile} UserProfile
 * @typedef {import('../types/contracts').TraceView} TraceView
 * @typedef {import('../types/contracts').ImportPayload} ImportPayload
 * @typedef {import('../types/contracts/history_page').StagedWrite} StagedWrite
 * @typedef {HistoryTurn & { trace_id?: string, display?: ShownEvent[] | null }} StoredTurn
 * @typedef {{ id: string, entry: StagedWrite, at: string }} StoredLog
 * @typedef {import('../types/contracts/history_page').LogMealArgs['meal']} MealType
 * @typedef {Omit<CardData, 'entry' | 'attributes'> & { id: string, turn: string, card: number,
 *   kind: StagedWrite['kind'], entry: StagedWrite, attributes: string[] }} Pending
 * @typedef {{ version: 1, profile: UserProfile | null, turns: StoredTurn[], pending: Pending[],
 *   logs: StoredLog[], traces: TraceView[] }} GuestData
 * @typedef {{ getItem(key: string): string | null, setItem(key: string, value: string): void,
 *   removeItem(key: string): void }} Storage
 */

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
  logsSent: 50, // limits.GUEST_LOGS_SENT: for the repeat check (Part E #67)
  logsDays: 7, // limits.GUEST_LOGS_DAYS
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
  no_replace: 'This entry has no earlier one to replace.',
}

/** A stored entry's ID: what a repeat card's Replace names (Part E #67). */
const newId = () => crypto.randomUUID()

/**
 * JSON as Python writes it with sort_keys and compact separators, non-ASCII kept.
 * @param {any} value
 * @returns {string}
 */
export function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort()
      .map((k) => `${JSON.stringify(k)}:${canonical(value[k])}`).join(',')}}`
  }
  return JSON.stringify(value ?? null)
}

/**
 * The server's `profile_hash` of a guest profile (staging.profile_hash).
 * @param {UserProfile | null} profile
 */
export async function profileHash(profile) {
  const bytes = new TextEncoder().encode(canonical(profile ?? null))
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

/**
 * A profile with every field, as the server's model dumps it (the hash depends on it).
 * @param {Partial<UserProfile> | null} profile
 * @returns {UserProfile | null}
 */
export function fullProfile(profile) {
  return profile ? { ...EMPTY_PROFILE, ...profile } : null
}

/** @returns {GuestData} */
const fresh = () => ({ version: 1, profile: null, turns: [], pending: [], logs: [], traces: [] })

/**
 * @param {Storage} [storage]
 * @param {{ now?: () => Date, endSession?: () => Promise<void> }} [options]
 */
export function guestStore(storage = globalThis.localStorage,
                           { now = () => new Date(), endSession = signOut } = {}) {
  /** @returns {GuestData} */
  const read = () => {
    try {
      const data = JSON.parse(storage.getItem(KEY) ?? 'null')
      return data?.version === 1 ? data : fresh()
    } catch {
      return fresh() // unreadable: start again rather than fail the chat
    }
  }

  /** @param {GuestData} data */
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

  /**
   * @param {GuestData} data
   * @param {Pending} entry
   * @param {NonNullable<CardData['state']>} state
   */
  const setCard = (data, entry, state) => {
    const turn = data.turns.find((t) => t.trace_id === entry.turn)
    const card = turn?.display?.[entry.card]
    if (card?.event === 'pending_write') card.data.state = state
  }

  return {
    data: read,

    profile: () => read().profile,

    /**
     * Saves the profile; held entries checked against another profile can't be logged.
     * @param {Partial<UserProfile>} profile
     */
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

    /**
     * The chat request's guest fields (C.8): the profile, the last 6 turns, and the
     * entries logged in the last 7 days (at most 50), so an entry logged again waits on
     * the repeat card (Part E #67).
     */
    /** @param {string} message @param {Record<string, unknown>} [extra] */
    chatInput(message, extra = {}) {
      const data = read()
      const history = data.turns.slice(-LIMITS.turnsSent).map(historyTurn)
      const since = now().getTime() - LIMITS.logsDays * 86_400_000
      const logs = data.logs.filter((l) => new Date(l.at).getTime() >= since)
        .slice(-LIMITS.logsSent)
      return { message, guest_profile: data.profile, guest_history: history, guest_logs: logs,
               ...extra }
    },

    /**
     * A finished turn (`done`): the signed exchange, what was shown, logs and held entries.
     * Returns the trace IDs of earlier turns whose cards a newer entry replaced, so the chat
     * can redraw them at once (D064).
     * @param {ChatEvent[]} events
     * @returns {string[]}
     */
    recordTurn(events) {
      const done = events.find((e) => e.name === 'done')
      if (!done?.data.turn || !done.data.said) return []
      const data = read()
      const traceId = done.data.trace_id
      /** @type {ShownEvent[]} */
      const display = events.filter((e) => SHOWN.has(e.name)).map(({ name, data: d }) => {
        const { seq: _seq, trace_id: _trace, ...shown } = /** @type {any} */ (d)
        return /** @type {ShownEvent} */ ({
          event: name, data: name === 'pending_write' ? { ...shown, state: 'waiting' } : shown })
      })
      data.turns.push(done.data.said) // the server's copy, as signed: never rewritten here
      data.turns.push({ ...done.data.turn, trace_id: traceId, display })

      for (const write of events.flatMap((e) => (e.name === 'committed' ? e.data.writes : []))) {
        if (write.entry) {
          data.logs.push({ id: newId(), entry: write.entry, at: write.at ?? done.data.turn.ts })
        }
      }
      // A guest's held entry carries the entry itself, to log here when confirmed
      /** @type {Pending[]} */
      const held = display.flatMap((e, card) => (e.event === 'pending_write' && e.data.entry
        ? [{ ...e.data, id: `${traceId}:${card}`, turn: traceId, card, kind: e.data.entry.kind,
             entry: e.data.entry, attributes: e.data.attributes ?? [] }]
        : []))
      const kinds = new Set(held.map((h) => h.kind))
      const replaced = data.pending.filter((p) => kinds.has(p.kind))
      for (const old of replaced) setCard(data, old, 'replaced')
      data.pending = [...data.pending.filter((p) => !kinds.has(p.kind)), ...held]
      if (done.data.trace) data.traces = [...data.traces, done.data.trace].slice(-LIMITS.traces)
      write(data)
      return [...new Set(replaced.map((p) => p.turn))]
    },

    pending: () => read().pending,

    /**
     * Logs a held entry as the person confirms it: when it happened (`at`, a Date or ISO
     * string with its zone), a meal's meal, and what they left out of its warnings. A
     * repeat's `replace` deletes the entry it repeats (Part E #67).
     */
    /**
     * @param {string} id
     * @param {{ at?: Date | string, meal?: MealType, leftOut?: string[], replace?: boolean }} [options]
     */
    async confirm(id, { at, meal, leftOut = [], replace = false } = {}) {
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
      // Only guessed, and the repeat card has no time to pick: Replace keeps the earlier
      // entry's time (D064: a correction moved breakfast from 9:34 to 8:00, Part E #73)
      const kept = replace && entry.time_guessed ? entry.entry.repeat_of?.at : undefined
      const when = new Date(kept ?? at ?? entry.at)
      const nowMs = now().getTime()
      if (Number.isNaN(when.getTime()) || when.getTime() > nowMs + LIMITS.minutesAhead * 60_000
          || when.getTime() < nowMs - LIMITS.daysBack * 86_400_000) {
        return { ok: false, code: 'bad_date', message: MESSAGES.bad_date }
      }
      const earlier = entry.entry.repeat_of?.log_id
      if (replace && !earlier) {
        return { ok: false, code: 'bad_request', message: MESSAGES.no_replace }
      }
      const { repeat_of: _repeat, ...held } = entry.entry
      const logged = {
        ...held,
        args: meal && entry.entry.kind === 'meal' ? { ...entry.entry.args, meal } : entry.entry.args,
        warnings: (entry.entry.warnings ?? []).map((w) => (w.kind === 'conflict'
          && (w.attributes ?? []).some((a) => leftOut.includes(a)) ? { ...w, left_out: true } : w)),
        at: when.toISOString(),
        time_guessed: false,
      }
      if (replace) data.logs = data.logs.filter((l) => l.id !== earlier) // gone already: logged
      data.logs.push({ id: newId(), entry: logged, at: when.toISOString() })
      data.pending = data.pending.filter((p) => p.id !== id)
      setCard(data, entry, 'logged')
      write(data)
      return { ok: true, entry: logged }
    },

    /** "Don't log": the entry goes, and its card says so. */
    /** @param {string} id */
    discard(id) {
      const data = read()
      const entry = data.pending.find((p) => p.id === id)
      if (!entry) return
      data.pending = data.pending.filter((p) => p.id !== id)
      setCard(data, entry, 'discarded')
      write(data)
    },

    /** POST /account/import (C.18): within its limits, the newest displays that fit. */
    /** @returns {ImportPayload} */
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
/** @param {StoredTurn} turn @returns {HistoryTurn} */
function historyTurn({ role, content, agents, ts, sig, prev, shown }) {
  if (role === 'user') return { role, content, ts }
  return { role, content, agents: agents ?? null, ts, sig: sig ?? null, prev: prev ?? null,
           shown: shown ?? null }
}

const size = (/** @type {unknown} */ value) => new TextEncoder().encode(JSON.stringify(value)).length

/** Under `limit`: the oldest answers' displays first, then the oldest traces. */
/** @param {GuestData} data @param {number} limit */
function fit(data, limit) {
  let trimmed = true
  while (trimmed && size(data) > limit) trimmed = trimOldest(data)
}

/** @param {GuestData} data */
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
