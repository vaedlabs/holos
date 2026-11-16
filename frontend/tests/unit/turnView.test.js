/**
 * One answer's view (P5.3; Part E #58, #61): every sample stream, live and saved, comes
 * out the same; cards sit with the coach that logged them; a week is a table by day.
 */

import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import { byDay, safeLink, stepStatus, turnView } from '@/lib/turnView'

const STREAMS = path.resolve(__dirname, '../../../contracts/streams')
const SHOWN = new Set(['section_start', 'text', 'item', 'sources', 'section_end',
                       'pending_write', 'committed', 'logged_note', 'crisis', 'notice'])
const sample = (file) => fs.readFileSync(path.join(STREAMS, file), 'utf8').split('\n')
  .filter(Boolean).map((l) => { const { event, data } = JSON.parse(l); return { name: event, data } })
/** What a saved answer keeps (C.5 History): the shown events, without their envelope. */
const saved = (events) => events.filter((e) => SHOWN.has(e.name)).map(({ name, data }) => {
  const { seq, trace_id, ...rest } = data
  return { event: name, data: rest }
})

describe('every sample stream', () => {
  it.each(fs.readdirSync(STREAMS).filter((f) => f.endsWith('.jsonl')))(
    '%s looks the same live and saved', (file) => {
      const live = turnView(sample(file))
      const again = turnView(saved(sample(file)))
      for (const key of ['own', 'summary', 'sections', 'crisis', 'notices']) {
        expect(again[key]).toEqual(live[key])
      }
    })

  it('a plan keeps its text and items in order, the items as one block', () => {
    const view = turnView(sample('plan_single.jsonl'))
    const [physical] = view.sections
    expect(physical.agent).toBe('physical')
    expect(physical.blocks.map((b) => b.type)).toContain('items')
    const items = physical.blocks.find((b) => b.type === 'items').items
    expect(items.every((i) => typeof i.display === 'string')).toBe(true)
  })

  it('a held entry is a waiting card in the logging coach\'s section', () => {
    const view = turnView(sample('pending_write.jsonl'))
    const card = view.sections.flatMap((s) => s.cards).find((c) => c.type === 'held')
    expect(card.state).toBe('waiting')
    expect(view.sections.find((s) => s.cards.includes(card)).agent).toBe('nutrition')
  })
})

describe('cards', () => {
  const ev = (name, data) => ({ name, data: { seq: 0, trace_id: 't', ...data } })

  it('a saved entry sits with its coach even when the coach said nothing', () => {
    const view = turnView([
      ev('section_start', { agent: 'nutrition', kind: 'plan' }),
      ev('text', { agent: 'nutrition', chunk: 'Dinner idea.' }),
      ev('section_end', { agent: 'nutrition', removed_count: 0 }),
      ev('committed', { writes: [{ kind: 'workout', summary: 'Logged: Glute bridge: 3 x 12' }] }),
    ])
    const physical = view.sections.find((s) => s.agent === 'physical')
    expect(physical.blocks).toEqual([])
    expect(physical.cards[0]).toMatchObject({ type: 'logged', summary: 'Logged: Glute bridge: 3 x 12' })
  })

  it("the coach's sentence replaces the card's Logged line", () => {
    const view = turnView([
      ev('committed', { writes: [{ kind: 'meal', summary: 'Logged: Lunch: Dal' }] }),
      ev('logged_note', { text: 'Nice, a warm bowl of dal for lunch.' }),
    ])
    expect(view.sections[0].cards[0].note).toBe('Nice, a warm bowl of dal for lunch.')
  })

  it("a saved card keeps its state, and its place among what was shown", () => {
    const view = turnView([
      { event: 'text', data: { chunk: 'Noted.' } },
      { event: 'pending_write', data: { kind: 'meal', summary: 'Lunch', at: 'x', state: 'logged' } },
    ])
    expect(view.sections[0].cards[0]).toMatchObject({ state: 'logged', index: 1 })
  })
})

describe('helpers', () => {
  it('a week is grouped by day, in the order given', () => {
    const items = [{ day: 'Mon', display: 'a' }, { day: 'Mon', display: 'b' },
                   { day: 'Wed', display: 'c' }]
    expect(byDay(items).map((d) => [d.day, d.items.length])).toEqual([['Mon', 2], ['Wed', 1]])
  })

  it.each([['https://nhs.uk/x', 'https://nhs.uk/x'], ['http://x.com', null],
           ['javascript:alert(1)', null], ['hxxp://x', null], ['not a url', null]])(
    'only https sources link: %s', (url, expected) => {
      expect(safeLink(url)).toBe(expected)
    })
})

describe('the status line', () => {
  it('keeps its words through a step that has none (the gate, a retry)', () => {
    let now = ''
    for (const step of ['admitted', 'routed', 'agent_started', 'gate', 'retry', 'gate']) {
      now = stepStatus(now, step)
    }
    expect(now).toBe('Thinking…')
    expect(stepStatus(now, 'composing')).toBe('Putting it together…')
  })
})
