// @vitest-environment jsdom
/**
 * How an answer arrives (R7; P5.4): while it's coming, each part fades in and the step it's on
 * shows below it; a saved answer shows at once; a crisis reply shows at once, plain, with no
 * loading line, live or not.
 */

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import AnswerEntry from '@/components/chat/AnswerEntry'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const ev = (name, data) => ({ name, data: { seq: 0, trace_id: 't', ...data } })
const text = ev('text', { agent: 'mental', chunk: 'Try a slow breath out, twice as long as the breath in.' })
const crisis = ev('crisis', { text: "You don't have to face this alone.",
  helplines: [{ name: 'Tele-MANAS', region: 'India', contact: '14416' }] })
const draw = (events, entry = {}) => render(
  <AnswerEntry entry={{ key: 'a', role: 'assistant', events, live: true, ...entry }}
               guest={false} store={null} status="Thinking…" onRetry={null} />)

describe('an answer on its way', () => {
  it('fades each part in and shows the step it is on', () => {
    const { container } = draw([text])
    expect(container.querySelector('.animate-fade-up')).not.toBeNull()
    expect(screen.getByRole('status').textContent).toContain('Thinking…')
  })

  it('a saved answer shows at once, with no loading line', () => {
    const { container } = draw([text, ev('done', {})], { live: false, saved: true })
    expect(container.querySelector('.animate-fade-up')).toBeNull()
    expect(screen.queryByRole('status')).toBeNull()
  })
})

describe('a decided card', () => {
  it('tells the chat its new state, so a newer entry replaces only cards still waiting (D067)', async () => {
    // The account's confirm, answered as the server answers it
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ writes: [{ summary: 'Logged: Lunch' }] }),
      { status: 200, headers: { 'content-type': 'application/json' } })))
    const onSettled = vi.fn()
    const held = ev('pending_write', { kind: 'meal', summary: 'Lunch', warnings: [], attributes: [],
      at: '2026-11-15T07:30:00Z', meal: 'lunch', time_guessed: false, write_id: 'w1' })
    render(<AnswerEntry entry={{ key: 'a', role: 'assistant', events: [text, held], live: false }}
                        guest={false} store={null} status="" onRetry={null} onSettled={onSettled} />)
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(onSettled).toHaveBeenCalledWith('a', 1, 'logged'))
    expect(screen.getByText('Logged: Lunch')).toBeTruthy()
  })
})

describe('a crisis reply', () => {
  it('shows at once with its helplines, and no loading line, while live', () => {
    const { container } = draw([crisis])
    expect(screen.getByRole('alert').textContent).toContain('Tele-MANAS')
    expect(container.querySelector('[class*="animate-"]')).toBeNull()
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('stays plain even when other parts came before it', () => {
    const { container } = draw([text, crisis])
    expect(container.querySelector('.animate-fade-up')).toBeNull()
    expect(screen.queryByRole('status')).toBeNull()
  })
})
