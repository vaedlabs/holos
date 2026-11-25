// @vitest-environment jsdom
/**
 * The chat's answer (P5.3; Part E #50, #58, #59): each sample stream draws its items,
 * model prose never becomes a link, a held entry shows Confirm, formatting and tables
 * read as meant.
 */

import fs from 'node:fs'
import path from 'node:path'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import Answer from '@/components/chat/Answer'
import { REPLACED_EARLIER, whenShort } from '@/components/chat/Card'
import { turnView } from '@/lib/turnView'

afterEach(cleanup)

const STREAMS = path.resolve(__dirname, '../../../contracts/streams')
const sample = (file) => fs.readFileSync(path.join(STREAMS, file), 'utf8').split('\n')
  .filter(Boolean).map((l) => { const { event, data } = JSON.parse(l); return { name: event, data } })
const ev = (name, data) => ({ name, data: { seq: 0, trace_id: 't', ...data } })
const draw = (events, props = {}) => render(
  <Answer view={turnView(events)} onConfirm={vi.fn()} onDiscard={vi.fn()} {...props} />)

describe('sample streams', () => {
  it.each(fs.readdirSync(STREAMS).filter((f) => f.endsWith('.jsonl')))(
    '%s draws every item it sent', (file) => {
      const events = sample(file)
      const { container } = draw(events)
      for (const { data } of events.filter((e) => e.name === 'item')) {
        expect(container.textContent).toContain(data.display)
      }
      // The only links are https sources
      for (const a of container.querySelectorAll('a')) expect(a.href).toMatch(/^https:/)
    })
})

describe('model prose', () => {
  it.each([
    'Read more at [this site](javascript:alert(1)).',
    'See https://evil.example.com/login for details.',
    'Try hxxp://evil[.]com today.',
    '<a href="https://evil.example.com">click</a> and <img src=x onerror=alert(1)>',
    '![a picture](https://evil.example.com/x.png)',
  ])('never becomes a link or an image: %s', (chunk) => {
    const { container } = draw([ev('text', { agent: 'physical', chunk })])
    expect(container.querySelector('a')).toBeNull()
    expect(container.querySelector('img')).toBeNull()
  })

  it('a heading, bold and a list read as meant', () => {
    const { container } = draw([ev('text', { chunk: '## Wind down\nSleep at **10 pm**.\n\n- dim lights\n- no screens' })])
    expect(container.querySelector('h2')).toBeNull() // a heading is a bold line in the answer
    expect(screen.getByText('Wind down').closest('strong')).not.toBeNull()
    expect(screen.getByText('10 pm').tagName).toBe('STRONG')
    expect(container.querySelectorAll('li')).toHaveLength(2)
  })

  it('a comparison table is a table', () => {
    const chunk = '| Food | Protein |\n|---|---|\n| Tofu | 15 g |\n| Chana | 9 g |'
    const { container } = draw([ev('text', { agent: 'nutrition', chunk })])
    const table = container.querySelector('table')
    expect(table).not.toBeNull()
    expect(within(table).getByText('Tofu')).toBeTruthy()
  })

  it('a week plan is a table by day', () => {
    const item = (day, display) => ev('item', { agent: 'physical', display, caveats: [],
      item: { day, catalogue_id: 'x', sets: 2, reps: 10, duration_s: null, intensity: 'low', note: '' } })
    const { container } = draw([ev('section_start', { agent: 'physical', kind: 'plan' }),
                                item('Mon', 'Glute bridge: 2 x 10'), item('Mon', 'Plank: 30 s'),
                                item('Wed', 'Walk: 20 min')])
    const rows = container.querySelectorAll('tbody tr')
    expect(rows).toHaveLength(3)
    expect(rows[0].querySelector('th').textContent).toBe('Mon')
    expect(rows[0].querySelector('th').getAttribute('rowspan')).toBe('2')
  })

  it('only an https source is a link', () => {
    const { container } = draw([ev('sources', { agent: 'nutrition', sources: [
      { id: 's1', title: 'NHS', url: 'https://www.nhs.uk/x' },
      { id: 's2', title: 'Plain', url: 'http://example.com' }] })])
    const links = container.querySelectorAll('a')
    expect(links).toHaveLength(1)
    expect(links[0].getAttribute('rel')).toContain('noopener')
  })
})

describe('cards', () => {
  const held = (fields = {}) => ev('pending_write', { kind: 'meal', summary: 'Breakfast: Poha',
    warnings: ['Poha: contains peanut, which is in your allergies'], attributes: ['peanut'],
    at: '2026-11-15T03:30:00Z', meal: 'breakfast', time_guessed: false, write_id: 'w1', ...fields })

  it('a waiting entry shows Confirm and "Don\'t log"', () => {
    draw([held()])
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeTruthy()
    expect(screen.getByRole('button', { name: "Don't log" })).toBeTruthy()
  })

  it('a decided entry says what happened and offers nothing', () => {
    draw([held({ state: 'replaced' })])
    expect(screen.queryByRole('button', { name: 'Confirm' })).toBeNull()
    expect(screen.getByText('A newer entry replaced this one.')).toBeTruthy()
  })

  it('Confirm sends the date, the meal and what was left out', async () => {
    const onConfirm = vi.fn().mockResolvedValue({ state: 'logged', message: 'Logged: Lunch: Poha' })
    draw([held()], { onConfirm })
    fireEvent.change(screen.getByLabelText('Meal'), { target: { value: 'lunch' } })
    fireEvent.click(screen.getByLabelText('peanut'))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(screen.getByText('Logged: Lunch: Poha')).toBeTruthy())
    const [, body] = onConfirm.mock.calls[0]
    expect(body).toMatchObject({ meal: 'lunch', leftOut: ['peanut'] })
    expect(Date.parse(body.at)).toBe(Date.parse('2026-11-15T03:30:00Z'))
    // One line says it was logged, not "Logged." as well (D062 B5)
    expect(screen.getAllByText(/^Logged/)).toHaveLength(1)
  })

  it('a confirmed card with no words from the server says Logged.', async () => {
    const onConfirm = vi.fn().mockResolvedValue({ state: 'logged', message: '' })
    draw([held()], { onConfirm })
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(screen.getAllByText(/^Logged/)).toHaveLength(1))
    expect(screen.getByText('Logged.')).toBeTruthy()
  })

  it('a refused date keeps it waiting, with the reason', async () => {
    const onConfirm = vi.fn().mockResolvedValue({ message: 'Choose a date in the last 30 days.' })
    draw([held()], { onConfirm })
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(screen.getByText('Choose a date in the last 30 days.')).toBeTruthy())
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeTruthy()
  })

  it("a logged card shows the coach's sentence in place of its Logged line", () => {
    draw([ev('committed', { writes: [{ kind: 'meal', summary: 'Logged: Lunch: Dal' }] }),
          ev('logged_note', { text: 'A warm bowl of dal, nice.' })])
    expect(screen.getByText('A warm bowl of dal, nice.')).toBeTruthy()
    expect(screen.queryByText('Logged: Lunch: Dal')).toBeNull()
  })
})

describe('the repeat card (Part E #67)', () => {
  const repeat = (i, fields = {}) => ev('pending_write', { kind: 'meal', summary: `Lunch: Dal ${i}`,
    warnings: [], attributes: [], at: '2026-11-15T07:30:00Z', meal: 'lunch', time_guessed: false,
    write_id: `w${i}`, repeat_of: { summary: 'Lunch: Dal', at: '2026-11-15T06:30:00Z',
                                     log_id: String(i), this_turn: false }, ...fields })

  it("an answer's repeats are one card naming each earlier entry", () => {
    draw([repeat(1), repeat(2)])
    expect(screen.getAllByRole('region', { name: 'Possible repeat' })).toHaveLength(1)
    expect(screen.getAllByText(/^Already logged: Lunch: Dal · /)).toHaveLength(2)
    expect(screen.getByText('Log them again?')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Confirm' })).toBeNull()
  })

  it('each entry shows its own time: a correction differs only in that', () => {
    draw([repeat(1)])
    const card = screen.getByRole('region', { name: 'Possible repeat' })
    expect(card.textContent).toContain(`Lunch: Dal 1 · ${whenShort('2026-11-15T07:30:00Z')}`)
    expect(card.textContent).toContain(`Already logged: Lunch: Dal · ${whenShort('2026-11-15T06:30:00Z')}`)
  })

  it.each([
    ['Log again', false, 'Logged.'],
    ['Replace the earlier ones', true, REPLACED_EARLIER],
  ])('%s decides every entry still waiting', async (button, replace, said) => {
    const onConfirm = vi.fn().mockResolvedValue({ state: 'logged', message: '' })
    draw([repeat(1), repeat(2), repeat(3, { state: 'discarded' })], { onConfirm })
    fireEvent.click(screen.getByRole('button', { name: button }))
    await waitFor(() => expect(screen.getAllByText(said)).toHaveLength(2))
    expect(onConfirm.mock.calls.map(([card, body]) => [card.write_id, body.replace]))
      .toEqual([['w1', replace], ['w2', replace]])
    expect(onConfirm.mock.calls[0][1].at).toBe('2026-11-15T07:30:00Z')
    expect(screen.queryByRole('button', { name: 'Log again' })).toBeNull()
  })

  it('Replace leads when the earlier entry can be replaced; else Log again', () => {
    draw([repeat(1)])
    const lead = (name) => screen.getByRole('button', { name }).dataset.variant
    expect(lead('Replace the earlier one')).toBe('default')
    expect(lead('Log again')).toBe('outline')
    cleanup()
    draw([repeat(1, { repeat_of: { summary: 'Lunch: Dal', at: '2026-11-15T06:30:00Z', log_id: null,
                                   this_turn: true } })])
    expect(screen.queryByRole('button', { name: /Replace/ })).toBeNull()
    expect(lead('Log again')).toBe('default')
  })

  it("Don't log drops them all", async () => {
    const onDiscard = vi.fn().mockResolvedValue({ state: 'discarded', message: '' })
    draw([repeat(1), repeat(2)], { onDiscard })
    fireEvent.click(screen.getByRole('button', { name: "Don't log" }))
    await waitFor(() => expect(screen.getAllByText('Not logged.')).toHaveLength(2))
  })

  it('an entry of this same answer can be logged again, not replaced', () => {
    draw([repeat(1, { repeat_of: { summary: 'Lunch: Dal', at: '2026-11-15T07:30:00Z',
                                   log_id: null, this_turn: true } })])
    expect(screen.getByText('Also earlier in this answer.')).toBeTruthy()
    expect(screen.getByText('Log it again?')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Replace/ })).toBeNull()
  })
})

describe('a coach that failed', () => {
  const failed = [ev('section_end', { agent: 'mental', removed_count: 0, error: 'unavailable' })]

  it('offers Retry for that coach while the answer is live', () => {
    const onRetry = vi.fn()
    draw(failed, { onRetry })
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(onRetry).toHaveBeenCalledWith('mental')
  })

  it('in history it only says so', () => {
    draw(failed, { onRetry: null })
    expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull()
    expect(screen.getByText("This coach couldn't answer just now.")).toBeTruthy()
  })
})
