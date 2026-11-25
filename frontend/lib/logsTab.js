/**
 * Which tab the Logs drawer opens on (owner, 25 Nov 2026), the first rule that applies:
 *
 *   1. Something was logged since the drawer last looked: that entry's tab.
 *   2. Otherwise the tab the person picked last.
 *   3. Otherwise the tab with the newest entry.
 *   4. Otherwise Workouts.
 *
 * "Since it last looked" goes by each kind's highest log id, not by when an entry happened, so a
 * meal logged late with an earlier time still counts and a deleted entry doesn't. What it
 * remembers ({tab, seen: {kind: highest id}}) stays in this browser until sign-out; without
 * storage it falls back to rules 3 and 4.
 */

export const KIND_DATES = { workouts: 'workout_date', nutrition: 'meal_date', mental: 'activity_date' }
const KEY = 'holos.logs-tab'

const highest = (list) => list.reduce((top, log) => Math.max(top, Number(log.id) || 0), 0)
const newestAt = (list, kind) => (list[0] ? Date.parse(list[0][KIND_DATES[kind]]) : -Infinity)

/** The kind whose newest entry is the newest of all, or null with none. */
function newestKind(logs, kinds = Object.keys(KIND_DATES)) {
  let best = [null, -Infinity]
  for (const kind of kinds) {
    const at = newestAt(logs[kind] || [], kind)
    if (at > best[1]) best = [kind, at]
  }
  return best[0]
}

/** The tab to open on, and what to remember for next time. */
export function pickTab(logs, remembered) {
  const seen = Object.fromEntries(Object.keys(KIND_DATES).map((k) => [k, highest(logs[k] || [])]))
  const fresh = remembered
    ? Object.keys(KIND_DATES).filter((k) => seen[k] > (remembered.seen?.[k] ?? 0))
    : []
  const tab = (fresh.length > 0 && newestKind(logs, fresh)) // 1
    || (KIND_DATES[remembered?.tab] && remembered.tab) // 2
    || newestKind(logs) // 3
    || 'workouts' // 4
  return { tab, seen }
}

export function readRemembered(storage = globalThis.localStorage) {
  try {
    const value = JSON.parse(storage.getItem(KEY))
    return value && typeof value === 'object' ? value : null
  } catch {
    return null
  }
}

export function remember(value, storage = globalThis.localStorage) {
  try {
    storage.setItem(KEY, JSON.stringify(value))
  } catch {
    // storage blocked or full: the drawer just falls back to rules 3 and 4
  }
}

export function forgetTab(storage = globalThis.localStorage) {
  try {
    storage.removeItem(KEY)
  } catch {
    // nothing kept
  }
}
