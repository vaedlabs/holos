/**
 * Deciding a held entry (C.17, Part E #50): every answer becomes the card's state and
 * message; a wrong date or left-out keeps it waiting.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { rememberSession } from '@/lib/api'
import { accountCards, guestCards } from '@/lib/cards'

import { fakeFetch, json } from './fake_server'

beforeEach(() => rememberSession({ csrf_token: 'c' }))
const CARD = { write_id: 'w1', index: 3 }

describe('an account', () => {
  it('Confirm sends the date, meal, left-outs and zone, and shows the Logged line', async () => {
    const { fetchImpl, calls } = fakeFetch([json(200, { writes: [{ summary: 'Logged: Lunch: Poha' }] })])
    const result = await accountCards(fetchImpl).confirm(CARD, { at: '2026-11-15T03:30:00.000Z',
                                                                meal: 'lunch', leftOut: ['peanut'] })
    expect(result).toEqual({ state: 'logged', message: 'Logged: Lunch: Poha' })
    expect(calls[0].url).toMatch(/\/agents\/writes\/w1\/confirm$/)
    expect(calls[0].body).toMatchObject({ at: '2026-11-15T03:30:00.000Z', meal: 'lunch',
                                          left_out: ['peanut'] })
    expect(calls[0].body.timezone).toBeTruthy()
  })

  it.each([
    [410, 'replaced', 'replaced'], [409, 'blocked', 'blocked'], [409, 'discarded', 'discarded'],
    [404, 'not_found', 'closed'], [400, 'bad_date', undefined], [400, 'bad_request', undefined],
  ])('%i %s is %s', async (status, code, state) => {
    const { fetchImpl } = fakeFetch([json(status, { code, message: `said ${code}` })])
    expect(await accountCards(fetchImpl).confirm(CARD, { at: 'x' }))
      .toEqual({ state, message: `said ${code}` })
  })

  it("Replace is sent only when asked for (Part E #67)", async () => {
    const { fetchImpl, calls } = fakeFetch([json(200, { writes: [{ summary: 'Logged' }] }),
                                           json(200, { writes: [{ summary: 'Logged' }] })])
    await accountCards(fetchImpl).confirm(CARD, { at: 'x', replace: true })
    await accountCards(fetchImpl).confirm(CARD, { at: 'x' })
    expect(calls[0].body.replace).toBe(true)
    expect(calls[1].body).not.toHaveProperty('replace')
  })

  it("Don't log, and Don't log after it was logged", async () => {
    const { fetchImpl } = fakeFetch([json(200, { discarded: true }),
                                     json(409, { code: 'logged', message: 'already logged' })])
    expect(await accountCards(fetchImpl).discard(CARD)).toEqual({ state: 'discarded', message: '' })
    expect(await accountCards(fetchImpl).discard(CARD)).toEqual({ state: 'logged', message: 'already logged' })
  })
})

describe('a guest', () => {
  it('the entry is found by its answer and its place in it', async () => {
    const store = { confirm: vi.fn().mockResolvedValue({ ok: true }), discard: vi.fn() }
    expect(await guestCards(store, 'tr9').confirm(CARD, { at: 'x', leftOut: [] }))
      .toEqual({ state: 'logged', message: '' })
    expect(store.confirm).toHaveBeenCalledWith('tr9:3', { at: 'x', meal: undefined, leftOut: [],
                                                         replace: false })
    await guestCards(store, 'tr9').discard(CARD)
    expect(store.discard).toHaveBeenCalledWith('tr9:3')
  })

  it('a changed profile closes the card; a bad date keeps it waiting', async () => {
    const store = { confirm: vi.fn()
      .mockResolvedValueOnce({ ok: false, code: 'profile_changed', message: 'changed' })
      .mockResolvedValueOnce({ ok: false, code: 'bad_date', message: 'date' }) }
    expect(await guestCards(store, 't').confirm(CARD, {})).toEqual({ state: 'closed', message: 'changed' })
    expect(await guestCards(store, 't').confirm(CARD, {})).toEqual({ state: undefined, message: 'date' })
  })
})
