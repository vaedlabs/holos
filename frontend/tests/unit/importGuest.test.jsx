// @vitest-environment jsdom
/**
 * A guest's data offered to the account that signed in (C.18, P5.4; Part E #78): nothing
 * is saved without a yes; Save imports and clears the browser copy; Discard clears it;
 * closing keeps it for the next sign-in; a failed save keeps it and retries with the same ID.
 */

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import ImportGuest from '@/components/ImportGuest'
import { importGuest } from '@/lib/api'
import { guestStore } from '@/lib/guestStore'

vi.mock('@/lib/api', async (actual) => ({ ...(await actual()), importGuest: vi.fn() }))

afterEach(cleanup)
beforeEach(() => vi.mocked(importGuest).mockReset())

function memoryStorage() {
  const items = new Map()
  return { getItem: (k) => items.get(k) ?? null, setItem: (k, v) => items.set(k, v),
           removeItem: (k) => items.delete(k), get length() { return items.size } }
}

const KEY = 'holos.guest.v1'
const STORED = { version: 1, profile: { condition_ids: [], allergen_tags: ['peanut'], diet_tags: [], notes: '' },
                 turns: [{ role: 'user', content: 'hi', ts: '2026-11-26T08:00:00Z' },
                         { role: 'assistant', content: 'Hello', ts: '2026-11-26T08:00:01Z' }],
                 pending: [], logs: [], traces: [] }
const RESULT = { imported: { history: 2, logs: 0 }, skipped: [], review: [], history_refused: [] }

function setup(stored = STORED) {
  const storage = memoryStorage()
  if (stored) storage.setItem(KEY, JSON.stringify(stored))
  const store = guestStore(storage, { endSession: vi.fn() })
  const onImported = vi.fn()
  render(<ImportGuest store={store} onImported={onImported} />)
  return { storage, onImported }
}

describe('the guest-data offer', () => {
  it('asks only when this browser holds guest data', () => {
    setup(null)
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('says what is here and saves nothing until asked', () => {
    setup()
    expect(screen.getByRole('dialog').textContent).toContain('2 messages and a health profile')
    expect(screen.getByRole('dialog').textContent).not.toContain('Each log entry') // none here
    expect(importGuest).not.toHaveBeenCalled()
    // Neither button holds the focus, so Enter alone does nothing irreversible
    expect(document.activeElement).toBe(screen.getByRole('dialog'))
  })

  it('Save imports, clears the browser copy and shows what came in', async () => {
    vi.mocked(importGuest).mockResolvedValue({
      ...RESULT, imported: { history: 2, logs: 3 },
      skipped: [{ index: 0, reason: 'Dated over a day ahead.' }, { index: 1, reason: 'Dated over a day ahead.' }],
      review: [{ index: 2, warnings: ['Contains peanut: you have a peanut allergy'] }],
      history_refused: [{ index: 0, reason: "This part of the conversation was changed outside Holos, so it wasn't imported." }],
    })
    const { storage, onImported } = setup()
    fireEvent.click(screen.getByRole('button', { name: 'Save to my account' }))
    await screen.findByText('Saved to your account')
    const body = vi.mocked(importGuest).mock.calls[0][0]
    expect(body.profile).toEqual(STORED.profile)
    expect(body.history).toHaveLength(2)
    expect(storage.length).toBe(0)
    expect(onImported).toHaveBeenCalledOnce()
    const text = screen.getByRole('dialog').textContent
    expect(text).toContain('2 messages, 3 log entries and a health profile saved')
    expect(text).toContain('2 log entries not saved')
    expect(text.match(/Dated over a day ahead/g)).toHaveLength(1) // each reason once
    expect(text).toContain('1 message not saved')
    expect(text).toContain('Contains peanut: you have a peanut allergy')
  })

  it('a profile alone says the profile was saved, not "0 messages"', async () => {
    vi.mocked(importGuest).mockResolvedValue({ ...RESULT, imported: { history: 0, logs: 0 } })
    setup({ ...STORED, turns: [] })
    fireEvent.click(screen.getByRole('button', { name: 'Save to my account' }))
    await screen.findByText('Saved to your account')
    expect(screen.getByRole('dialog').textContent).toContain('A health profile saved')
    expect(screen.getByRole('dialog').textContent).not.toContain('0 messages')
  })

  it('Discard clears the browser copy without importing', () => {
    const { storage } = setup()
    fireEvent.click(screen.getByRole('button', { name: 'Discard guest data' }))
    expect(storage.length).toBe(0)
    expect(importGuest).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('closing keeps the data, to ask at the next sign-in', async () => {
    const { storage } = setup()
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(storage.length).toBe(1)
    expect(importGuest).not.toHaveBeenCalled()
  })

  it('a failed save keeps the data, says why, and retries with the same import ID', async () => {
    vi.mocked(importGuest).mockRejectedValueOnce(new Error("Holos can't be reached right now."))
      .mockResolvedValueOnce(RESULT)
    const { storage } = setup()
    fireEvent.click(screen.getByRole('button', { name: 'Save to my account' }))
    await screen.findByText("Holos can't be reached right now.")
    expect(storage.length).toBe(1)
    fireEvent.click(screen.getByRole('button', { name: 'Save to my account' }))
    await screen.findByText('Saved to your account')
    const [first, second] = vi.mocked(importGuest).mock.calls.map(([body]) => body.import_id)
    expect(second).toBe(first)
  })
})
