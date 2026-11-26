// @ts-check
/**
 * The crisis check in the browser (Plan C.16, P5.4): the server's check
 * (backend/app/guardrails/crisis.py, normalise.py) run from contracts/crisis.json, so a crisis
 * message shows the helplines at once, even with the backend slow or down (Part E #78). The
 * message is still sent: the server's check is the one that counts. Both pass
 * contracts/crisis_cases.jsonl.
 *
 * Python's `\w` is Unicode and JavaScript's isn't, even with the `u` flag: letters and digits
 * are written as \p{L} and \p{N} here.
 */

import CRISIS from '../../contracts/crisis.json'

/** @typedef {{ name: string, region: string, contact: string }} Helpline */

/** The fixed crisis text and helplines, bundled: nothing to fetch. */
export const CRISIS_TEXT = CRISIS.message
/** @type {Helpline[]} */
export const HELPLINES = CRISIS.helplines

const WORD_CHAR = '[\\p{L}\\p{N}_\\u0300-\\u036f\\u0900-\\u097f]'
// Python's [^\W\d_]: letters, and numbers that aren't decimal digits
const LETTER = '[\\p{L}\\p{Nl}\\p{No}]'
const SEPARATOR = '[.\\-\\s]+'
const ZERO_WIDTH = /[​‌‍⁠﻿]/gu
const WHITESPACE = /\s+/gu
// Three or more single letters split by dots, dashes or spaces: "k.i.l.l", "s u i c i d e"
const SPLIT_LETTERS = new RegExp(
  `(?<!${WORD_CHAR})${LETTER}(?!${WORD_CHAR})(?:${SEPARATOR}${LETTER}(?!${WORD_CHAR})){2,}`, 'gu')
const SEPARATOR_RE = new RegExp(SEPARATOR, 'gu')
// "a" and "I" are words on their own: never joined to a neighbour across a space
const SOLO_WORDS = new Set(['a', 'i'])

const escape = (/** @type {string} */ s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const byLength = (/** @type {string[]} */ keys) => [...keys].sort((a, b) => b.length - a.length)
const alternation = (/** @type {string[]} */ keys) => byLength(keys).map(escape).join('|')
const isSpace = (/** @type {string} */ s) => /^\s+$/u.test(s)

/** @param {string} text @param {Record<string, string>} table one character to its replacement */
function translate(text, table) {
  let out = ''
  for (const ch of text) out += ch in table ? table[ch] : ch
  return out
}

/** @param {string} text */
function normaliseText(text) {
  return text.normalize('NFKC').toLowerCase().replace(ZERO_WIDTH, '').replace(WHITESPACE, ' ').trim()
}

/** @param {string} text */
export function joinSplitLetters(text) {
  return text.replace(SPLIT_LETTERS, (run) => {
    let letters = run.split(SEPARATOR_RE)
    let seps = [...(run.match(SEPARATOR_RE) ?? [])]
    let head = ''
    let tail = ''
    if (SOLO_WORDS.has(letters[0]) && isSpace(seps[0] ?? '')) {
      head = `${letters[0]} `
      letters = letters.slice(1)
      seps = seps.slice(1)
    }
    if (letters.length > 1 && SOLO_WORDS.has(letters.at(-1) ?? '') && isSpace(seps.at(-1) ?? '')) {
      tail = ` ${letters.at(-1)}`
      letters = letters.slice(0, -1)
    }
    if (letters.length < 3) return run
    return head + letters.join('') + tail
  })
}

/**
 * The server's CrisisNormaliser, step for step: NFKC, lowercase, zero-width characters removed,
 * `chars`, `leet` anywhere, `leet_inner` only between two letters, split letters joined, `words`
 * (whole words only), whitespace collapsed.
 * @param {{ chars: Record<string, string>, leet: Record<string, string>,
 *   leet_inner: Record<string, string>, words: Record<string, string> }} rules
 */
export function crisisNormaliser({ chars, leet, leet_inner: leetInner, words }) {
  const inner = Object.keys(leetInner).length
    ? new RegExp(`(?<=${LETTER})(${alternation(Object.keys(leetInner))})(?=${LETTER})`, 'gu') : null
  // Keys are compared after `chars`, so "don't" or a nukta spelling works as a key
  const table = Object.fromEntries(Object.entries(words).map(([k, v]) => [translate(normaliseText(k), chars), v]))
  const wordRe = Object.keys(table).length
    ? new RegExp(`(?<!${WORD_CHAR})(${alternation(Object.keys(table))})(?!${WORD_CHAR})`, 'gu') : null
  return (/** @type {string} */ text) => {
    let out = text.normalize('NFKC').toLowerCase().replace(ZERO_WIDTH, '')
    out = translate(translate(out, chars), leet)
    if (inner) out = out.replace(inner, (m) => leetInner[m])
    out = joinSplitLetters(out.replace(WHITESPACE, ' '))
    if (wordRe) out = out.replace(wordRe, (m) => table[m])
    return out.replace(WHITESPACE, ' ').trim()
  }
}

// A space in a phrase may be missing, so fully split letters ("k i l l m y s e l f" joins to
// "killmyself") still match
const phrasePattern = (/** @type {string} */ p) => p.split(' ').filter(Boolean).map(escape).join('\\s?')
const compile = (/** @type {string[]} */ phrases) => new RegExp(
  `(?<!${WORD_CHAR})(?:${byLength(phrases).map(phrasePattern).join('|') || '(?!x)x'})(?!${WORD_CHAR})`, 'gu')

/**
 * @param {{ phrases: Record<string, string[]>, exceptions: string[],
 *   normalise: Parameters<typeof crisisNormaliser>[0] }} crisis
 */
export function crisisChecker(crisis) {
  const normalise = crisisNormaliser(crisis.normalise)
  /** @type {Map<string, string>} the normalised phrase to its language */
  const language = new Map()
  for (const [lang, phrases] of Object.entries(crisis.phrases)) {
    for (const p of phrases) language.set(normalise(p), lang) // a phrase in two lists: the last, as in Python
  }
  const phrases = compile([...language.keys()])
  const exceptions = compile(crisis.exceptions.map(normalise))
  const compact = new Map([...language.keys()].map((p) => [p.replace(/ /g, ''), p]))

  /** @param {string} message @returns {{ matched: boolean, language?: string, phrase?: string }} */
  return (message) => {
    const text = normalise(message)
    const covered = [...text.matchAll(exceptions)].map((m) => [m.index, m.index + m[0].length])
    for (const m of text.matchAll(phrases)) {
      const [start, end] = [m.index, m.index + m[0].length]
      if (covered.some(([s, e]) => s <= start && end <= e)) continue
      const phrase = compact.get(m[0].replace(/\s/gu, '')) ?? m[0]
      return { matched: true, language: language.get(phrase), phrase }
    }
    return { matched: false }
  }
}

/** Whether a message is a crisis message, by the phrases bundled with the app. */
export const crisisCheck = crisisChecker(CRISIS)
