// @ts-check
/**
 * Deciding a held entry (C.17; Part E #50): Confirm or "Don't log", for an account
 * through the server, for a guest in the browser. Each answer becomes the card's new
 * state and the message to show; a wrong date or left-out keeps it waiting. A repeat's
 * Replace is a confirm that deletes the entry it repeats (Part E #67).
 */

import { ApiError, request } from './api'

/**
 * @typedef {import('./turnView').HeldCard} HeldCard
 * @typedef {import('./guestStore').MealType} MealType
 * @typedef {{ at?: Date | string, meal?: MealType, leftOut?: string[], replace?: boolean }} Decision
 * @typedef {{ state?: HeldCard['state'], message: string }} Decided
 * @typedef {{ confirm(card: HeldCard, decision: Decision): Promise<Decided>,
 *   discard(card: HeldCard): Promise<Decided> }} Cards
 */

const ZONE = () => Intl.DateTimeFormat().resolvedOptions().timeZone

/**
 * The server's answer as {state, message}: 410 replaced, 409 blocked/discarded/logged.
 * @param {unknown} error
 * @returns {Decided}
 */
function decided(error) {
  if (!(error instanceof ApiError)) throw error
  /** @type {Record<string, HeldCard['state']>} */
  const states = { replaced: 'replaced', blocked: 'blocked', discarded: 'discarded',
                   logged: 'logged', not_found: 'closed' }
  const state = states[error.code]
  return { state, message: error.message }
}

/** @param {typeof fetch} [fetchImpl] @returns {Cards} */
export const accountCards = (fetchImpl) => ({
  async confirm(card, { at, meal, leftOut = [], replace = false }) {
    try {
      const body = await request(`/agents/writes/${card.write_id}/confirm`, {
        method: 'POST', fetchImpl,
        body: { at, meal, left_out: leftOut, timezone: ZONE(), ...(replace ? { replace } : {}) } })
      return { state: 'logged', message: body.writes?.[0]?.summary || '' }
    } catch (error) {
      return decided(error)
    }
  },
  async discard(card) {
    try {
      await request(`/agents/writes/${card.write_id}/discard`, { method: 'POST', fetchImpl })
      return { state: 'discarded', message: '' }
    } catch (error) {
      return decided(error)
    }
  },
})

/** A guest's entries: `traceId` is the answer's, the card's place among what it showed. */
/**
 * @param {ReturnType<typeof import('./guestStore').guestStore>} store
 * @param {string} traceId
 * @returns {Cards}
 */
export const guestCards = (store, traceId) => ({
  async confirm(card, { at, meal, leftOut = [], replace = false }) {
    const result = await store.confirm(`${traceId}:${card.index}`, { at, meal, leftOut, replace })
    if (result.ok) return { state: 'logged', message: '' }
    return { state: result.code === 'profile_changed' || result.code === 'not_found'
      ? 'closed' : undefined, message: result.message ?? '' }
  },
  async discard(card) {
    store.discard(`${traceId}:${card.index}`)
    return { state: 'discarded', message: '' }
  },
})
