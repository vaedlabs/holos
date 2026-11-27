// @vitest-environment jsdom
/**
 * How an answer was made (P5.6): the `blocked_and_retried` sample shows the block and its rule ID;
 * each coach says what it did, from the answer itself; no model calls, retries or cost (owner,
 * 27 Nov 2026). The panel comes under a finished live answer only (Part E #79), closed until
 * asked; never on a saved answer or a crisis reply.
 */

import fs from 'node:fs'
import path from 'node:path'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import AnswerEntry from '@/components/chat/AnswerEntry'
import { RULE_COACH, coachLines, duration, groupDecisions } from '@/lib/trace'
import { turnView } from '@/lib/turnView'

afterEach(cleanup)

const STREAMS = path.resolve(__dirname, '../../../contracts/streams')
const sample = (file) => fs.readFileSync(path.join(STREAMS, file), 'utf8').split('\n')
  .filter(Boolean).map((l) => { const { event, data } = JSON.parse(l); return { name: event, data } })

const entry = (events, fields = {}) => ({ key: 'a', role: 'assistant', events, live: false, ...fields })
const draw = (e) => render(<AnswerEntry entry={e} guest={false} store={null} status="" />)
const toggle = () => screen.queryByRole('button', { name: /How this answer was made/ })

describe('the trace panel', () => {
  it('blocked_and_retried shows the block, its rule ID, and what the coach did', () => {
    draw(entry(sample('blocked_and_retried.jsonl')))
    expect(toggle().getAttribute('aria-expanded')).toBe('false')
    expect(toggle().textContent).toContain('1 safety removal')
    expect(screen.queryByText('EX-KNEE-01')).toBeNull() // closed until asked
    fireEvent.click(toggle())
    expect(toggle().getAttribute('aria-expanded')).toBe('true')
    const panel = document.getElementById(toggle().getAttribute('aria-controls'))
    const text = panel.textContent
    expect(screen.getByText('EX-KNEE-01')).toBeTruthy()
    expect(text).toContain('Removed back_squat')
    expect(text).toContain('High knee load with a knee ligament injury')
    expect(text.match(/EX-KNEE-01/g)).toHaveLength(1) // the same block on the first try and the retry: one line
    expect(text).not.toContain('×')
    expect(text).toContain('Coaching · Exercise coach')
    expect(text).toContain('Suggested 2 exercises, removed 1')
    expect(toggle().textContent).toContain('8.8 s') // the whole answer's time, on the closed line
    // Owner, 27 Nov 2026: no model calls, retries or cost
    expect(text).not.toMatch(/model call|retr|asked again|tokens|\$/i)
    expect(screen.getByText('Removed').className).toContain('text-caution')
  })

  it('every sample that finishes shows it, and none shows text the person wrote', () => {
    for (const file of fs.readdirSync(STREAMS).filter((f) => f.endsWith('.jsonl') && f !== 'crisis.jsonl')) {
      const events = sample(file)
      if (!events.some((e) => e.name === 'done' && e.data.trace)) continue
      const { unmount } = draw(entry(events))
      fireEvent.click(toggle())
      const asked = events.find((e) => e.name === 'done')?.data.said
      if (asked) expect(document.body.textContent).not.toContain(asked)
      unmount()
    }
  })

  it('not while the answer is still coming', () => {
    draw(entry(sample('blocked_and_retried.jsonl'), { live: true }))
    expect(toggle()).toBeNull()
  })

  it('not on a saved answer: history keeps no trace', () => {
    const shown = sample('blocked_and_retried.jsonl').filter((e) => !['accepted', 'step', 'done'].includes(e.name))
    draw(entry(shown, { saved: true }))
    expect(toggle()).toBeNull()
  })

  it('not on a crisis reply; a coach\'s answer that also gives the helplines has it', () => {
    draw(entry(sample('crisis.jsonl')))
    expect(toggle()).toBeNull()
    cleanup()
    draw(entry(sample('risk_flag.jsonl')))
    expect(toggle()).not.toBeNull()
  })
})

describe('reading a trace', () => {
  it('times read as people say them', () => {
    expect([duration(5), duration(8800), duration(61_000)]).toEqual(['5 ms', '8.8 s', '1 min 1 s'])
  })

  it('one line per item: its rules and reasons once each; a decision with no item keeps its own', () => {
    const d = (rule, item, reason) => ({ action: 'block', rule_id: rule, rules_version: 1, reason, offending_items: item ? [item] : [] })
    const lines = groupDecisions([
      d('EX-KNEE-01', 'Box jump', 'High knee load'), d('EX-KNEE-02', 'Box jump', 'High impact'),
      d('EX-KNEE-01', 'Box jump', 'High knee load'), // the retry's
      d('EX-KNEE-01', 'Running', 'High knee load'), d('GT-MALFORMED-01', null, 'Unreadable reply'),
    ])
    expect(lines).toEqual([
      { action: 'block', item: 'Box jump', rules: ['EX-KNEE-01', 'EX-KNEE-02'], reasons: ['High knee load', 'High impact'] },
      { action: 'block', item: 'Running', rules: ['EX-KNEE-01'], reasons: ['High knee load'] },
      { action: 'block', item: null, rules: ['GT-MALFORMED-01'], reasons: ['Unreadable reply'] },
    ])
  })

  it('a coach whose suggestions were all removed says so, not "gave advice"', () => {
    const block = (rule) => ({ action: 'block', rule_id: rule, rules_version: 1, reason: 'x', offending_items: ['Box jump'] })
    const trace = { trace_id: 't', route: 'coaching', agents: ['physical', 'nutrition'], retries: 1, sources: [],
                    usage: { tokens_in: 0, tokens_out: 0, cost_usd: 0 }, steps: [], tools: [],
                    decisions: [block('EX-KNEE-01'), block('EX-KNEE-02')] }
    const view = turnView([
      { name: 'section_start', data: { seq: 1, trace_id: 't', agent: 'physical', kind: 'answer' } },
      { name: 'section_start', data: { seq: 2, trace_id: 't', agent: 'nutrition', kind: 'answer' } },
    ])
    expect(coachLines(trace, view).map((c) => c.did)).toEqual(['All suggestions removed', 'Gave advice'])
  })

  it("every rule's prefix names its coach (backend/app/guardrails/rules.yaml)", () => {
    const rules = fs.readFileSync(path.resolve(__dirname, '../../../backend/app/guardrails/rules.yaml'), 'utf8')
    const prefixes = new Set([...rules.matchAll(/^\s*- id: ([A-Z]+)-/gm)].map((m) => m[1]))
    expect(prefixes.size).toBeGreaterThan(0)
    for (const p of prefixes) expect(RULE_COACH[p], `rule prefix ${p}`).toBeDefined()
  })

  it('each coach in a few words, from what its answer shows', () => {
    const trace = { trace_id: 't', route: 'coaching', agents: ['nutrition', 'mental'], decisions: [], retries: 0,
                    sources: [], usage: { tokens_in: 0, tokens_out: 0, cost_usd: 0 },
                    steps: [{ name: 'coach', agent: 'nutrition', start_ms: 0, duration_ms: 3100, queue_ms: 0 }],
                    tools: [{ name: 'log_meal', args: '', duration_ms: 5, status: 'staged' },
                            { name: 'get_recent_logs', args: '', duration_ms: 5, status: 'ok' }] }
    const view = turnView([
      { name: 'section_start', data: { seq: 1, trace_id: 't', agent: 'nutrition', kind: 'answer' } },
      { name: 'committed', data: { seq: 2, trace_id: 't', writes: [{ kind: 'meal', summary: 'Lunch', warnings: [] }] } },
      { name: 'section_start', data: { seq: 3, trace_id: 't', agent: 'mental', kind: 'answer' } },
      { name: 'section_end', data: { seq: 4, trace_id: 't', agent: 'mental', removed_count: 0, decisions: [], warnings: [], error: 'unavailable' } },
    ])
    expect(coachLines(trace, view)).toEqual([
      // get_recent_logs isn't the food coach's to claim with two coaches in the answer
      { who: 'Food coach', did: 'Logged a meal', took: '3.1 s' },
      { who: 'Mental wellbeing coach', did: "Couldn't answer this time", took: null },
    ])
  })

  it('with one coach, its reads and searches are its own; plain advice says so', () => {
    const trace = { trace_id: 't', route: 'coaching', agents: ['physical'], decisions: [], retries: 0, sources: [],
                    usage: { tokens_in: 0, tokens_out: 0, cost_usd: 0 }, steps: [],
                    tools: [{ name: 'web_search', args: '', duration_ms: 900, status: 'ok' },
                            { name: 'get_recent_logs', args: '', duration_ms: 5, status: 'ok' }] }
    const searched = turnView([{ name: 'section_start', data: { seq: 1, trace_id: 't', agent: 'physical', kind: 'answer' } }])
    expect(coachLines(trace, searched)[0].did).toBe('Searched the web, checked recent logs')
    expect(coachLines({ ...trace, tools: [] }, searched)[0]).toEqual({ who: 'Exercise coach', did: 'Gave advice', took: null })
  })
})
