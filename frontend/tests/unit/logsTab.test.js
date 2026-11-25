/**
 * Which tab the Logs drawer opens on (owner, 25 Nov 2026): something new, else the tab picked
 * last, else the newest entry's, else Workouts; "new" by log id, so a late-dated entry counts.
 */

import { describe, expect, it } from 'vitest'

import { pickTab, readRemembered, remember } from '@/lib/logsTab'

const meal = (id, at) => ({ id, meal_date: at })
const workout = (id, at) => ({ id, workout_date: at })
const logs = (over = {}) => ({ workouts: [workout(4, '2026-11-25T09:51:00Z')],
                               nutrition: [meal(9, '2026-11-25T08:00:00Z')], mental: [], ...over })
const seenNow = { workouts: 4, nutrition: 9, mental: 0 }

describe('the tab the Logs drawer opens on', () => {
  it('1: something logged since it last looked opens its tab, even dated earlier', () => {
    const now = logs({ nutrition: [meal(9, '2026-11-25T08:00:00Z'), meal(10, '2026-11-25T07:00:00Z')] })
    expect(pickTab(now, { tab: 'workouts', seen: seenNow })).toEqual(
      { tab: 'nutrition', seen: { ...seenNow, nutrition: 10 } })
  })

  it('2: with nothing new, the tab picked last', () => {
    expect(pickTab(logs(), { tab: 'mental', seen: seenNow }).tab).toBe('mental')
  })

  it('2: a deleted entry is nothing new', () => {
    expect(pickTab(logs({ workouts: [] }), { tab: 'mental', seen: seenNow }).tab).toBe('mental')
  })

  it('3: the first time, the newest entry', () => {
    expect(pickTab(logs(), null).tab).toBe('workouts')
    expect(pickTab(logs({ workouts: [] }), null).tab).toBe('nutrition')
  })

  it('4: with no logs at all, Workouts', () => {
    expect(pickTab({ workouts: [], nutrition: [], mental: [] }, null).tab).toBe('workouts')
  })

  it('is remembered in storage, and without storage it still picks', () => {
    const kept = {}
    const storage = { getItem: (k) => kept[k] ?? null, setItem: (k, v) => { kept[k] = v }, removeItem: (k) => { delete kept[k] } }
    remember({ tab: 'mental', seen: seenNow }, storage)
    expect(readRemembered(storage)).toEqual({ tab: 'mental', seen: seenNow })
    const blocked = { getItem: () => { throw new Error('blocked') }, setItem: () => { throw new Error('blocked') } }
    expect(readRemembered(blocked)).toBeNull()
    expect(() => remember({ tab: 'mental', seen: seenNow }, blocked)).not.toThrow()
    expect(pickTab(logs(), readRemembered(blocked)).tab).toBe('workouts')
  })
})
