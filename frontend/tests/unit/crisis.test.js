/**
 * The browser's crisis check (C.16, P5.4) passes every shared case the server's passes
 * (contracts/crisis_cases.jsonl), from the bundled phrases.
 */

import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import { CRISIS_TEXT, HELPLINES, crisisCheck, joinSplitLetters } from '@/lib/crisis'

const CASES = fs.readFileSync(path.resolve(__dirname, '../../../contracts/crisis_cases.jsonl'), 'utf8')
  .split('\n').filter(Boolean).map((line) => JSON.parse(line))

describe('the crisis check', () => {
  it('has the shared cases to pass', () => {
    expect(CASES.length).toBeGreaterThanOrEqual(100)
    expect(CASES.some((c) => c.expect) && CASES.some((c) => !c.expect)).toBe(true)
  })

  it.each(CASES.map((c) => [c.note, c]))('%s', (_note, c) => {
    expect(crisisCheck(c.text).matched, c.text).toBe(c.expect)
  })

  // Where JavaScript's regular expressions differ from Python's; each answer is the server's
  it.each([
    ['I want to die!', true], // "!" is an "i" only between two letters
    ['i want to die!!', true],
    ['I want to dieß', false], // a word goes on past a letter outside ASCII
    ['I want to dieé', false],
    ['मैं मरना चाहता हूँ!', true],
  ])('%s → %s, as on the server', (text, expected) => {
    expect(crisisCheck(text).matched).toBe(expected)
  })

  it('names the phrase from the rules, never the message', () => {
    expect(crisisCheck('ok so... i W4NNA d!e tbh')).toMatchObject({ matched: true, language: 'en' })
    expect(crisisCheck('ok so... i W4NNA d!e tbh').phrase).not.toContain('tbh')
  })

  it('joins split letters but never the words "a" and "I"', () => {
    expect(joinSplitLetters('k.i.l.l')).toBe('kill')
    expect(joinSplitLetters('i d i e')).toBe('i die')
    expect(joinSplitLetters('a b c')).toBe('a b c')
  })

  it('the crisis text and helplines come bundled', () => {
    expect(CRISIS_TEXT).toContain('14416')
    expect(HELPLINES.map((h) => h.contact)).toEqual(['14416', '988', 'findahelpline.com'])
  })
})
