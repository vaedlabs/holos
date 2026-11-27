// @vitest-environment jsdom
/**
 * A crisis message in the chat (C.16, P5.4; owner, Part E #78): the browser's check shows the
 * helplines before any reply, the message is still sent, the server's crisis event takes the
 * card's place (one card), and the card stays when sending fails. And any send that ends without
 * an answer stops loading.
 */

import fs from 'node:fs'
import path from 'node:path'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import ChatPage from '@/app/dashboard/page'
import { sendChat } from '@/lib/stream'

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/hooks/useAuth', () => ({
  useRequireAuth: () => ({ mounted: true, isAuthenticated: true, session: { mode: 'guest' } }),
}))
vi.mock('@/lib/stream', async (actual) => ({ ...(await actual()), sendChat: vi.fn() }))

const SAMPLE = fs.readFileSync(path.resolve(__dirname, '../../../contracts/streams/crisis.jsonl'), 'utf8')
  .split('\n').filter(Boolean).map((l) => { const { event, data } = JSON.parse(l); return { name: event, data } })

/** sendChat held open: `emit` an event, `finish` with a result. */
function held() {
  const control = {}
  vi.mocked(sendChat).mockImplementation((input, { onEvent }) => new Promise((resolve) => {
    Object.assign(control, { input, emit: onEvent, finish: resolve })
  }))
  return control
}

const say = (text) => {
  fireEvent.change(screen.getByRole('textbox', { name: 'Message' }), { target: { value: text } })
  fireEvent.click(screen.getByRole('button', { name: 'Send' }))
}
const cards = () => screen.queryAllByRole('alert').filter((el) => el.textContent.includes('Tele-MANAS'))

beforeEach(() => {
  localStorage.clear()
  vi.mocked(sendChat).mockReset()
})
afterEach(cleanup)

describe('a crisis message', () => {
  it('shows the helplines before any reply, and is still sent', async () => {
    const server = held()
    render(<ChatPage />)
    await act(async () => say('i w4nna d!e'))
    expect(cards()).toHaveLength(1) // nothing has come from the server yet
    expect(server.input.message).toBe('i w4nna d!e')
  })

  it("the server's crisis event takes its place: one card", async () => {
    const server = held()
    render(<ChatPage />)
    await act(async () => say('I want to end my life'))
    await act(async () => server.emit(SAMPLE[0])) // accepted: the browser's card stays
    expect(cards()).toHaveLength(1)
    await act(async () => SAMPLE.slice(1).forEach(server.emit))
    await act(async () => server.finish({ outcome: 'done' }))
    expect(cards()).toHaveLength(1)
  })

  it('keeps the helplines when sending fails', async () => {
    const server = held()
    render(<ChatPage />)
    await act(async () => say('I want to end my life'))
    await act(async () => server.finish({ outcome: 'refused', code: 'connection', message: "Holos can't be reached right now." }))
    expect(cards()).toHaveLength(1)
    expect(screen.getByText("Holos can't be reached right now.")).toBeTruthy()
  })
})

it('an ordinary message shows no crisis card', async () => {
  held()
  render(<ChatPage />)
  await act(async () => say('a 20 minute run for a beginner'))
  expect(cards()).toHaveLength(0)
})

it('a send that ends without an answer stops loading: no "Starting…" left counting', async () => {
  const server = held()
  render(<ChatPage />)
  await act(async () => say('a 20 minute run for a beginner'))
  expect(screen.getByRole('status')).toBeTruthy() // waiting for the answer
  await act(async () => server.emit({ name: 'accepted', data: { seq: 0, trace_id: 't', contract_version: 1, mode: 'guest' } }))
  await act(async () => server.finish({ outcome: 'error', code: 'interrupted', message: 'Your answer was interrupted. Tap to try again.' }))
  expect(screen.queryByRole('status')).toBeNull()
  expect(screen.getByText('Your answer was interrupted. Tap to try again.')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy()
})
