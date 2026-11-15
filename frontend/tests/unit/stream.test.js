/**
 * The stream client (Plan C.5, P5.1; Part E #34, #58, #59): every sample stream parses
 * and fits the contract, the client stops at the terminal event, reconnects from the
 * last event, and keeps the message when the answer didn't finish.
 */

import fs from 'node:fs'
import path from 'node:path'
import Ajv2020 from 'ajv/dist/2020'
import addFormats from 'ajv-formats'
import { beforeEach, describe, expect, it } from 'vitest'

import { rememberSession } from '@/lib/api'
import { CONTRACT_VERSION, EventParser, INTERRUPTED, sendChat } from '@/lib/stream'

import { fakeFetch, json, quietNetwork, streamed, wire } from './fake_server'

const CONTRACTS = path.resolve(__dirname, '../../../contracts')
const SAMPLES = fs.readdirSync(path.join(CONTRACTS, 'streams')).filter((f) => f.endsWith('.jsonl'))
const sample = (file) => fs.readFileSync(path.join(CONTRACTS, 'streams', file), 'utf8')
  .split('\n').filter(Boolean).map((line) => {
    const { event, data } = JSON.parse(line)
    return { name: event, data }
  })

// The contract check runs here, not in the app (owner, 14 Nov 2026: trim 1)
const ajv = addFormats(new Ajv2020({ strict: false, allErrors: true }))
const validEvent = ajv.compile(
  JSON.parse(fs.readFileSync(path.join(CONTRACTS, 'schema', 'stream_event.json'), 'utf8')))
const fits = ({ name, data }) => validEvent({ event: name, data })

// Fast enough for tests, in the same shape as the real values
const FAST = { silenceMs: 50, backoffMs: [1, 1, 1], network: quietNetwork }
const INPUT = { message: 'a leg workout', timezone: 'Asia/Kolkata' }
const ev = (seq, name, fields = {}) => ({ name, data: { seq, trace_id: 't1', ...fields } })
const ACCEPTED = ev(0, 'accepted', { contract_version: 1, mode: 'account' })
const TEXT = ev(1, 'text', { agent: 'physical', chunk: 'Here is your plan.' })
const DONE = ev(2, 'done', { trace: {}, usage: {} })

beforeEach(() => rememberSession({ csrf_token: 'csrf-1' }))

describe('sample streams', () => {
  it.each(SAMPLES)('%s parses in any chunking and fits the contract', (file) => {
    const events = sample(file)
    const text = events.map((e, i) => (i % 2 ? ': ping\n\n' : '') + wire(e)).join('')
    for (const size of [1, 7, 64, text.length]) {
      const parser = new EventParser()
      const got = []
      for (let i = 0; i < text.length; i += size) got.push(...parser.push(text.slice(i, i + size)))
      expect(got.filter((e) => !e.ping)).toEqual(events)
    }
    for (const event of events) expect(fits(event), JSON.stringify(validEvent.errors)).toBe(true)
  })

  it.each(SAMPLES)('%s comes through sendChat in order, ending as its last event', async (file) => {
    const events = sample(file)
    const { fetchImpl } = fakeFetch([streamed(events.map(wire))])
    const seen = []
    const result = await sendChat(INPUT, { ...FAST, fetchImpl, onEvent: (e) => seen.push(e) })
    expect(seen).toEqual(events)
    expect(result.outcome).toBe(events.at(-1).name === 'done' ? 'done' : 'error')
  })

  it('an event outside the contract is rejected', () => {
    expect(fits(ev(3, 'item', { agent: 'physical' }))).toBe(false) // no item, no display
    expect(fits(ev(3, 'secret_event', {}))).toBe(false)
    expect(fits(ev(3, 'text', { chunk: '' }))).toBe(false)
  })

  it('the contract version is the one the backend publishes', () => {
    const published = JSON.parse(fs.readFileSync(path.join(CONTRACTS, 'crisis.json'), 'utf8'))
    expect(CONTRACT_VERSION).toBe(published.contract_version)
  })
})

describe('sendChat', () => {
  it('stops at the terminal event, whatever follows it', async () => {
    const after = ev(3, 'text', { chunk: 'never shown' })
    const { fetchImpl } = fakeFetch([streamed([ACCEPTED, DONE, after].map(wire), { hang: true })])
    const seen = []
    const result = await sendChat(INPUT, { ...FAST, silenceMs: 60_000, fetchImpl,
                                           onEvent: (e) => seen.push(e.name) })
    expect(result.outcome).toBe('done')
    expect(seen).toEqual(['accepted', 'done'])
  })

  it('sends the request as the contract says', async () => {
    const { fetchImpl, calls } = fakeFetch([streamed([ACCEPTED, DONE].map(wire))])
    await sendChat(INPUT, { ...FAST, fetchImpl })
    const [call] = calls
    expect(call.method).toBe('POST')
    expect(call.headers).toMatchObject({ 'X-CSRF-Token': 'csrf-1', 'X-Contract-Version': '1' })
    expect(call.payload).toMatchObject({ ...INPUT, contract_version: 1 })
    expect(call.payload.client_request_id).toMatch(/^[0-9a-f-]{36}$/)
  })

  it('a 429 is the cap message for the chat, not an error page', async () => {
    const message = "You've reached today's limit. Try again tomorrow."
    const { fetchImpl } = fakeFetch([json(429, { code: 'cap_reached', message, retry_after: 600 })])
    const result = await sendChat(INPUT, { ...FAST, fetchImpl })
    expect(result).toMatchObject({ outcome: 'refused', code: 'cap_reached', message,
                                   retryAfter: 600, keepMessage: true })
  })

  it('a 429 without a body still says what happened', async () => {
    const { fetchImpl } = fakeFetch([json(429, undefined)])
    const result = await sendChat(INPUT, { ...FAST, fetchImpl })
    expect(result.message).toMatch(/limit/)
  })

  it('`connection` keeps the message, and Retry sends it with a new request ID', async () => {
    const failed = ev(1, 'error', { code: 'connection', message: "Holos couldn't connect just now." })
    const { fetchImpl, calls } = fakeFetch([streamed([ACCEPTED, failed].map(wire)),
                                           streamed([ACCEPTED, TEXT, DONE].map(wire))])
    const first = await sendChat(INPUT, { ...FAST, fetchImpl })
    expect(first).toMatchObject({ outcome: 'error', code: 'connection', keepMessage: true })
    const retry = await sendChat(INPUT, { ...FAST, fetchImpl })
    expect(retry.outcome).toBe('done')
    expect(calls[1].payload.message).toBe(INPUT.message)
    expect(calls[1].payload.client_request_id).not.toBe(calls[0].payload.client_request_id)
  })

  it('a silent stream reconnects from the last event, and nothing comes twice', async () => {
    const { fetchImpl, calls } = fakeFetch([
      streamed([ACCEPTED, TEXT].map(wire), { hang: true }),
      streamed([TEXT, DONE].map(wire)), // the server sends from `after`; a repeat is ignored
    ])
    const seen = []
    const statuses = []
    const result = await sendChat(INPUT, { ...FAST, fetchImpl, onEvent: (e) => seen.push(e.name),
                                           onStatus: (s) => statuses.push(s) })
    expect(result.outcome).toBe('done')
    expect(seen).toEqual(['accepted', 'text', 'done'])
    expect(statuses).toEqual(['reconnecting', 'live'])
    expect(calls[1]).toMatchObject({ method: 'GET' })
    expect(calls[1].url).toMatch(new RegExp(`/agents/chat/stream/${calls[0].payload.client_request_id}\\?after=1$`))
  })

  it('a dropped connection reconnects too', async () => {
    const { fetchImpl } = fakeFetch([streamed([wire(ACCEPTED)]), streamed([TEXT, DONE].map(wire))])
    expect((await sendChat(INPUT, { ...FAST, fetchImpl })).outcome).toBe('done')
  })

  it('a 404 on reconnecting a crisis request sends the message again', async () => {
    const crisis = ev(1, 'crisis', { text: 'You are not alone.', helplines: [] })
    const { fetchImpl, calls } = fakeFetch([
      streamed([wire(ACCEPTED)]), // dropped before the helplines
      json(404, { code: 'not_found', message: 'There is no such request.' }),
      streamed([ACCEPTED, crisis, DONE].map(wire)),
    ])
    const seen = []
    const result = await sendChat({ message: 'I want to end it all' },
                                  { ...FAST, fetchImpl, onEvent: (e) => seen.push(e.name) })
    expect(result.outcome).toBe('done')
    expect(seen).toContain('crisis')
    expect(calls.map((c) => c.method)).toEqual(['POST', 'GET', 'POST'])
    expect(calls[2].payload.message).toBe('I want to end it all')
    expect(calls[2].payload.client_request_id).not.toBe(calls[0].payload.client_request_id)
  })

  it('gives up after its reconnects as interrupted, keeping the message', async () => {
    const busy = json(503, { code: 'server_busy', message: 'Holos is busy.' })
    const { fetchImpl, calls } = fakeFetch([streamed([wire(ACCEPTED)]), busy, busy, busy])
    const statuses = []
    const result = await sendChat(INPUT, { ...FAST, fetchImpl, onStatus: (s) => statuses.push(s) })
    expect(result).toMatchObject({ outcome: 'error', code: 'interrupted', message: INTERRUPTED,
                                   keepMessage: true })
    expect(calls).toHaveLength(1 + FAST.backoffMs.length)
    expect(statuses).toEqual(['reconnecting', 'reconnecting', 'reconnecting'])
  })

  it('an expired answer (410) says so', async () => {
    const message = 'This answer is no longer available. Please ask again.'
    const { fetchImpl } = fakeFetch([streamed([wire(ACCEPTED)]), json(410, { code: 'expired', message })])
    expect(await sendChat(INPUT, { ...FAST, fetchImpl })).toMatchObject(
      { outcome: 'error', code: 'expired', message })
  })

  it('a stale CSRF token is fetched again once', async () => {
    const { fetchImpl, calls } = fakeFetch([
      json(403, { code: 'bad_csrf', message: 'Your session token is missing or out of date.' }),
      json(200, { mode: 'account', csrf_token: 'csrf-2', expires_at: 'x' }),
      streamed([ACCEPTED, DONE].map(wire)),
    ])
    expect((await sendChat(INPUT, { ...FAST, fetchImpl })).outcome).toBe('done')
    expect(calls[1].url).toMatch(/\/session\/csrf$/)
    expect(calls[2].headers['X-CSRF-Token']).toBe('csrf-2')
  })
})
