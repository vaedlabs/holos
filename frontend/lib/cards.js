/**
 * Deciding a held entry (C.17; Part E #50): Confirm or "Don't log", for an account
 * through the server, for a guest in the browser. Each answer becomes the card's new
 * state and the message to show; a wrong date or left-out keeps it waiting. A repeat's
 * Replace is a confirm that deletes the entry it repeats (Part E #67).
 */

import { ApiError, request } from './api'

const ZONE = () => Intl.DateTimeFormat().resolvedOptions().timeZone

/** The server's answer as {state, message}: 410 replaced, 409 blocked/discarded/logged. */
function decided(error) {
  if (!(error instanceof ApiError)) throw error
  const state = { replaced: 'replaced', blocked: 'blocked', discarded: 'discarded',
                  logged: 'logged', not_found: 'closed' }[error.code]
  return { state, message: error.message }
}

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
export const guestCards = (store, traceId) => ({
  async confirm(card, { at, meal, leftOut = [], replace = false }) {
    const result = await store.confirm(`${traceId}:${card.index}`, { at, meal, leftOut, replace })
    if (result.ok) return { state: 'logged', message: '' }
    return { state: result.code === 'profile_changed' || result.code === 'not_found'
      ? 'closed' : undefined, message: result.message }
  },
  async discard(card) {
    store.discard(`${traceId}:${card.index}`)
    return { state: 'discarded', message: '' }
  },
})
