/**
 * The guest store (Plan C.8, P5.2; Part E #50, #61): only 6 turns go with a message, a
 * profile edit drops the held entries checked against the old one, "Clear my data"
 * leaves nothing, held entries follow C.17, and the import fits its contract and 1 MB.
 */

import fs from 'node:fs'
import path from 'node:path'
import Ajv2020 from 'ajv/dist/2020'
import addFormats from 'ajv-formats'
import { describe, expect, it, vi } from 'vitest'

import { LIMITS, MESSAGES, guestStore, profileHash } from '@/lib/guestStore'

const CONTRACTS = path.resolve(__dirname, '../../../contracts')
const ajv = addFormats(new Ajv2020({ strict: false, allErrors: true }))
const validImport = ajv.compile(JSON.parse(
  fs.readFileSync(path.join(CONTRACTS, 'schema', 'import_payload.json'), 'utf8')))

const NOW = new Date('2026-11-15T12:00:00Z')
const KNEE = { condition_ids: ['knee_ligament_injury'], allergen_tags: [], diet_tags: [],
               notes: '' }

/** localStorage, in memory; `quota` in characters, like a browser's. */
function memoryStorage(quota = Infinity) {
  const items = new Map()
  return {
    getItem: (k) => (items.has(k) ? items.get(k) : null),
    setItem: (k, v) => {
      if (v.length > quota) throw new DOMException('full', 'QuotaExceededError')
      items.set(k, v)
    },
    removeItem: (k) => items.delete(k),
    get length() { return items.size },
  }
}

const store = (storage = memoryStorage(), extra = {}) =>
  guestStore(storage, { now: () => NOW, endSession: vi.fn(), ...extra })

const BRIDGES = { catalogue_id: 'glute_bridge', sets: 3, reps: 12, duration_s: null, note: '',
                  activity: null, when: { day: null, time: null, ampm: null, part: null } }
const SQUATS = { ...BRIDGES, catalogue_id: 'back_squat' }
const POHA = { meal: 'breakfast', when: BRIDGES.when, foods: [{
  day: null, name: 'Poha with peanuts', ingredients: ['flattened rice', 'peanut'],
  allergen_tags: ['peanut'], diet_tags: [], portion: '1 plate', calories: 300, note: '',
  protein_g: 8, carbs_g: 50, fat_g: 9 }] }
const PEANUT_CONFLICT = { kind: 'conflict', item: 'Poha with peanuts', rule_id: 'DI-ALG-01',
                          attributes: ['peanut'], reason: 'Contains an allergen in your profile',
                          left_out: false }

let traceN = 0
const SIG = (n) => n.toString(16).padStart(64, 'a') // a stand-in for the server's signature
/** A guest turn's events as the stream sends them, ending in `done`. */
function turnEvents({ held = [], committed = [], text = 'Nice work.', hash = 'h',
                      message = 'log it' } = {}) {
  const trace = `tr${++traceN}`
  let seq = 0
  const ev = (name, fields) => ({ name, data: { seq: seq++, trace_id: trace, ...fields } })
  return [
    ev('accepted', { contract_version: 1, mode: 'guest' }),
    ev('step', { name: 'routed' }),
    ev('section_start', { agent: 'physical', kind: 'log_ack' }),
    ev('text', { agent: 'physical', chunk: text }),
    ev('section_end', { agent: 'physical', removed_count: 0 }),
    ...(committed.length ? [ev('committed', { writes: committed.map(([kind, args]) => ({
      kind, summary: `Logged: ${kind}`, at: '2026-11-15T09:00:00Z',
      entry: { kind, args, warnings: [] }, warnings: [] })) })] : []),
    ...held.map(([kind, args, warnings = []]) => ev('pending_write', {
      summary: `${kind} entry`, warnings: warnings.map((w) => w.reason),
      attributes: warnings.flatMap((w) => w.attributes), at: '2026-11-15T09:00:00Z',
      meal: args.meal ?? null, time_guessed: false, entry: { kind, args, warnings },
      profile_hash: hash })),
    ev('done', { trace: { trace_id: trace, route: 'coaching' }, usage: {},
                 said: { role: 'user', content: message, agents: null, ts: '2026-11-15T09:00:00Z',
                         sig: null, prev: null, shown: null },
                 turn: { role: 'assistant', content: text, agents: ['physical'],
                         ts: '2026-11-15T09:00:05Z', sig: SIG(traceN), prev: null,
                         shown: 'c'.repeat(64) } }),
  ]
}

describe('profileHash', () => {
  // Computed by the backend's staging.profile_hash (15 Nov 2026)
  it.each([
    [null, '74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b'],
    [{ condition_ids: [], allergen_tags: [], diet_tags: [], notes: '' },
     '796b5333c1ff9a6535c6f332c1a1382c63e0814137068d5bf2f4deec5165156b'],
    [{ notes: 'घुटने में दर्द, desk job — “no gym”', diet_tags: ['vegetarian'],
       allergen_tags: ['peanut', 'milk'], condition_ids: ['knee_ligament_injury'] },
     'da815d9e3fc0a558f290de4a8464851541db9c7923c16186cd105944cb7f74f6'],
  ])('matches the server for %j', async (profile, hash) => {
    expect(await profileHash(profile)).toBe(hash)
  })
})

describe('the chat request', () => {
  it('sends the profile and only the last 6 turns, as the server reads them', async () => {
    const s = store()
    await s.setProfile({ condition_ids: ['knee_ligament_injury'] })
    for (let i = 0; i < 5; i++) {
      s.recordTurn(turnEvents({ text: `answer ${i}`, message: `message ${i}` }))
    }
    const input = s.chatInput('next')
    expect(input.guest_profile).toEqual(KNEE) // every field, as the server hashes it
    expect(input.guest_history).toHaveLength(LIMITS.turnsSent)
    expect(input.guest_history.map((t) => t.content)).toEqual(
      ['message 2', 'answer 2', 'message 3', 'answer 3', 'message 4', 'answer 4'])
    expect(input.guest_history[1]).toEqual({
      role: 'assistant', content: 'answer 2', agents: ['physical'], ts: '2026-11-15T09:00:05Z',
      sig: expect.stringMatching(/^[0-9a-f]{64}$/), prev: null, shown: 'c'.repeat(64) })
    expect(input.guest_history[0]).toEqual(
      { role: 'user', content: 'message 2', ts: '2026-11-15T09:00:00Z' })
  })

  it("keeps the server's copy of the exchange, signature and all (Part E #63)", () => {
    const s = store()
    const events = turnEvents({ message: 'a leg workout' })
    s.recordTurn(events)
    const { said, turn } = events.at(-1).data
    const [kept, answer] = s.chatInput('next').guest_history
    expect(kept).toEqual({ role: 'user', content: said.content, ts: said.ts })
    expect(answer).toMatchObject({ content: turn.content, ts: turn.ts, sig: turn.sig,
                                   prev: turn.prev, shown: turn.shown })
  })

  it('keeps what the answer showed, without the envelope or progress', () => {
    const s = store()
    s.recordTurn(turnEvents({ held: [['workout', BRIDGES]] }))
    const answer = s.data().turns[1]
    expect(answer.display.map((e) => e.event)).toEqual(
      ['section_start', 'text', 'section_end', 'pending_write'])
    expect(answer.display[1].data).toEqual({ agent: 'physical', chunk: 'Nice work.' })
    expect(answer.display[3].data.state).toBe('waiting')
  })

  it('an unfinished turn is not kept', () => {
    const s = store()
    const events = turnEvents().filter((e) => e.name !== 'done')
    s.recordTurn(events)
    expect(s.data().turns).toEqual([])
  })
})

describe('held entries (C.17)', () => {
  const held = async (s, ...entries) => {
    const hash = await profileHash(s.profile())
    return s.recordTurn(turnEvents({ held: entries, hash }))
  }

  it('a profile edit drops the entries checked against the old profile', async () => {
    const s = store()
    await s.setProfile(KNEE)
    await held(s, ['workout', SQUATS])
    await s.setProfile(KNEE) // the same profile: nothing changes
    expect(s.pending()).toHaveLength(1)
    await s.setProfile({ ...KNEE, notes: 'desk job' })
    expect(s.pending()).toEqual([])
    expect(s.data().turns[1].display.at(-1).data.state).toBe('closed')
  })

  it('a newer entry replaces the waiting ones of its kind; one turn waits together',
     async () => {
       const s = store()
       expect(await held(s, ['workout', BRIDGES], ['meal', POHA])).toEqual([])
       // The turns whose cards it replaced, for the chat to redraw at once (D064)
       expect(await held(s, ['workout', SQUATS], ['workout', BRIDGES]))
         .toEqual([s.data().turns[1].trace_id])
       expect(s.pending().map((p) => [p.kind, p.entry.args.catalogue_id ?? 'poha'])).toEqual(
         [['meal', 'poha'], ['workout', 'back_squat'], ['workout', 'glute_bridge']])
       const first = s.data().turns[1].display
       expect(first.filter((e) => e.event === 'pending_write').map((e) => e.data.state))
         .toEqual(['replaced', 'waiting'])
     })

  it('confirm logs it as the person dates it, with what they left out', async () => {
    const s = store()
    await s.setProfile({ allergen_tags: ['peanut'] })
    await held(s, ['meal', POHA, [PEANUT_CONFLICT]])
    const [entry] = s.pending()
    const at = '2026-11-14T08:15:00+05:30'
    const result = await s.confirm(entry.id, { at, meal: 'lunch', leftOut: ['peanut'] })
    expect(result.ok).toBe(true)
    const [log] = s.data().logs
    expect(log.at).toBe(new Date(at).toISOString())
    expect(log.entry.args.meal).toBe('lunch')
    expect(log.entry.warnings[0].left_out).toBe(true)
    expect(log.entry.time_guessed).toBe(false)
    expect(s.pending()).toEqual([])
    expect(s.data().turns[1].display.at(-1).data.state).toBe('logged')
  })

  it.each([
    [{ leftOut: ['gluten'] }, 'bad_request'],
    [{ at: '2026-10-01T08:00:00Z' }, 'bad_date'], // over 30 days back
    [{ at: '2026-11-15T13:00:00Z' }, 'bad_date'], // ahead of now
  ])('%j is refused and the entry still waits', async (body, code) => {
    const s = store()
    await s.setProfile({ allergen_tags: ['peanut'] })
    await held(s, ['meal', POHA, [PEANUT_CONFLICT]])
    const result = await s.confirm(s.pending()[0].id, body)
    expect(result).toMatchObject({ ok: false, code })
    expect(s.pending()).toHaveLength(1)
  })

  it('a profile changed behind the card is not logged', async () => {
    const s = store()
    await s.setProfile(KNEE)
    await held(s, ['workout', SQUATS])
    const [entry] = s.pending()
    const data = s.data() // another tab saved a new profile without this one's check
    const storage = memoryStorage()
    storage.setItem('holos.guest.v1', JSON.stringify({ ...data, profile: { ...KNEE, notes: 'x' } }))
    const other = store(storage)
    expect(await other.confirm(entry.id)).toMatchObject(
      { ok: false, code: 'profile_changed', message: MESSAGES.profile_changed })
    expect(other.data().logs).toEqual([])
    expect(other.pending()).toEqual([])
  })

  it("\"Don't log\" drops it and marks the card", async () => {
    const s = store()
    await held(s, ['workout', BRIDGES])
    s.discard(s.pending()[0].id)
    expect(s.pending()).toEqual([])
    expect(s.data().turns[1].display.at(-1).data.state).toBe('discarded')
  })

  it('what the turn logged at once is kept for the import', () => {
    const s = store()
    s.recordTurn(turnEvents({ committed: [['workout', BRIDGES]] }))
    expect(s.data().logs).toEqual([{ id: expect.any(String), at: '2026-11-15T09:00:00Z',
                                     entry: { kind: 'workout', args: BRIDGES, warnings: [] } }])
  })
})

describe('repeats (Part E #67)', () => {
  const chatPayload = ajv.compile(JSON.parse(
    fs.readFileSync(path.join(CONTRACTS, 'schema', 'chat_payload.json'), 'utf8')))

  /** A turn whose held entry repeats the stored one `logId`. */
  const repeated = async (s, logId, fields = {}, earlier = '2026-11-15T09:00:00Z') => {
    const events = turnEvents({ held: [['workout', BRIDGES]],
                                hash: await profileHash(s.profile()) })
    const card = events.find((e) => e.name === 'pending_write').data
    Object.assign(card, fields)
    card.repeat_of = { summary: 'Glute bridge', at: earlier, log_id: logId, this_turn: false }
    card.entry.repeat_of = card.repeat_of
    s.recordTurn(events)
    return s.pending()[0].id
  }

  it('each message carries the entries of the last 7 days, at most 50, each with its ID', () => {
    const storage = memoryStorage()
    const s = store(storage)
    for (let i = 0; i < 3; i++) {
      s.recordTurn(turnEvents({ committed: Array.from({ length: 20 }, () => ['workout', BRIDGES]) }))
    }
    const data = s.data()
    data.logs[0].at = '2026-11-07T09:00:00Z' // 8 days back: not sent
    storage.setItem('holos.guest.v1', JSON.stringify(data))
    const input = s.chatInput('hi', { client_request_id: crypto.randomUUID(), contract_version: 1 })
    expect(input.guest_logs).toHaveLength(LIMITS.logsSent)
    expect(input.guest_logs.at(-1)).toEqual(data.logs.at(-1))
    expect(new Set(input.guest_logs.map((l) => l.id)).size).toBe(LIMITS.logsSent)
    expect(LIMITS.logsSent).toBe(chatPayload.schema.properties.guest_logs.anyOf[0].maxItems)
    expect(chatPayload(input)).toBe(true)
  })

  it('Replace logs it in place of the entry it repeats', async () => {
    const s = store()
    s.recordTurn(turnEvents({ committed: [['workout', BRIDGES], ['workout', SQUATS]] }))
    const [bridges, squats] = s.data().logs
    const id = await repeated(s, bridges.id)
    expect((await s.confirm(id, { replace: true })).ok).toBe(true)
    const logs = s.data().logs
    expect(logs.map((l) => l.entry.args.catalogue_id)).toEqual(['back_squat', 'glute_bridge'])
    expect(logs[0]).toEqual(squats)
    expect(logs[1].id).not.toBe(bridges.id)
    expect(logs[1].entry).not.toHaveProperty('repeat_of')
  })

  it.each([
    [true, true, '2026-11-15T09:34:00.000Z'], // only guessed: the earlier time stands (D064)
    [false, true, '2026-11-15T08:00:00.000Z'], // a time the person gave wins
    [true, false, '2026-11-15T08:00:00.000Z'], // Log again: its own time
  ])('Replace keeps the earlier time over a guessed one (guessed %s, replace %s)',
     async (guessed, replace, logged) => {
       const s = store()
       s.recordTurn(turnEvents({ committed: [['workout', BRIDGES]] }))
       const id = await repeated(s, s.data().logs[0].id,
                                 { at: '2026-11-15T08:00:00Z', time_guessed: guessed },
                                 '2026-11-15T09:34:00Z')
       // As the repeat card sends it: the card's own time
       expect((await s.confirm(id, { at: '2026-11-15T08:00:00Z', replace })).ok).toBe(true)
       expect(s.data().logs.at(-1).at).toBe(logged)
     })

  it('Log again keeps both; Replace with nothing to replace is refused', async () => {
    const s = store()
    s.recordTurn(turnEvents({ committed: [['workout', BRIDGES]] }))
    const id = await repeated(s, null)
    expect(await s.confirm(id, { replace: true })).toMatchObject(
      { ok: false, code: 'bad_request', message: MESSAGES.no_replace })
    expect((await s.confirm(id)).ok).toBe(true)
    expect(s.data().logs).toHaveLength(2)
  })
})

describe('Clear my data', () => {
  it('leaves nothing in storage and ends the session', async () => {
    const storage = memoryStorage()
    const endSession = vi.fn()
    const s = store(storage, { endSession })
    await s.setProfile(KNEE)
    s.recordTurn(turnEvents({ committed: [['workout', BRIDGES]] }))
    await s.clearMyData()
    expect(storage.length).toBe(0)
    expect(endSession).toHaveBeenCalledOnce()
    expect(s.data()).toEqual({ version: 1, profile: null, turns: [], pending: [], logs: [],
                               traces: [] })
  })

  it('after sign-in: hasData offers the import, forget clears it and keeps the session', async () => {
    const storage = memoryStorage()
    const endSession = vi.fn()
    const s = store(storage, { endSession })
    expect(s.hasData()).toBe(false)
    await s.setProfile(KNEE)
    expect(s.hasData()).toBe(true)
    s.recordTurn(turnEvents({ committed: [['workout', BRIDGES]] }))
    s.forget()
    expect(storage.length).toBe(0)
    expect(s.hasData()).toBe(false)
    expect(endSession).not.toHaveBeenCalled() // the account that signed in stays signed in
  })

  it('unreadable storage starts again instead of breaking the chat', () => {
    const storage = memoryStorage()
    storage.setItem('holos.guest.v1', '{not json')
    expect(store(storage).chatInput('hi').guest_history).toEqual([])
  })
})

describe('the import body (C.18)', () => {
  it('fits the contract', async () => {
    const s = store()
    await s.setProfile(KNEE)
    const hash = await profileHash(s.profile())
    s.recordTurn(turnEvents({ held: [['workout', SQUATS]], committed: [['workout', BRIDGES]], hash }))
    s.discard(s.pending()[0].id)
    const body = s.importBody('5f2b0a4e-0c1d-4a7b-9a51-2f1c6a3b9d10')
    expect(validImport(body), JSON.stringify(validImport.errors)).toBe(true)
    expect(body.history[1].display.at(-1).data.state).toBe('discarded')
  })

  it('stays within 1 MB: the newest answers keep their displays', () => {
    const s = store()
    const long = 'Squeeze at the top and lower slowly. '.repeat(26) // under the 1,000-character chunk
    for (let i = 0; i < 25; i++) {
      const events = turnEvents({ text: `answer ${i}` })
      events.splice(4, 0, ...Array.from({ length: 60 }, () => (
        { name: 'text', data: { seq: 0, trace_id: 't', agent: 'physical', chunk: long } })))
      s.recordTurn(events)
    }
    const body = s.importBody()
    const size = new TextEncoder().encode(JSON.stringify(body)).length
    expect(size).toBeLessThanOrEqual(LIMITS.importBytes)
    const kept = body.history.filter((t) => t.role === 'assistant').map((t) => 'display' in t)
    const first = kept.indexOf(true)
    expect(first).toBeGreaterThan(0) // the oldest went as text only
    expect(kept.slice(first).every(Boolean)).toBe(true) // and every newer one kept it
  })

  it('sends at most 50 turns and 500 logs', () => {
    const s = store()
    for (let i = 0; i < 30; i++) {
      s.recordTurn(turnEvents({ committed: Array.from({ length: 20 }, () => ['workout', BRIDGES]) }))
    }
    const body = s.importBody()
    expect(body.history).toHaveLength(LIMITS.importTurns)
    expect(body.logs).toHaveLength(LIMITS.importLogs)
    expect(body.history.at(-1).content).toBe('Nice work.')
  })
})

describe('storage limits', () => {
  it('over 3 MB, the oldest displays go first', () => {
    const s = store()
    const big = 'x'.repeat(900)
    for (let i = 0; i < 40; i++) {
      const events = turnEvents()
      events.splice(4, 0, ...Array.from({ length: 100 }, () => (
        { name: 'text', data: { seq: 0, trace_id: 't', agent: 'physical', chunk: big } })))
      s.recordTurn(events)
    }
    const { turns } = s.data()
    expect(JSON.stringify(s.data()).length).toBeLessThanOrEqual(LIMITS.bytes)
    expect(turns).toHaveLength(80) // the history itself stays
    expect(turns[1].display).toBeNull()
    expect(turns.at(-1).display).not.toBeNull()
  })

  it("a browser's smaller quota trims the same way", () => {
    const s = store(memoryStorage(200_000))
    for (let i = 0; i < 20; i++) {
      const events = turnEvents()
      events.splice(4, 0, ...Array.from({ length: 20 }, () => (
        { name: 'text', data: { seq: 0, trace_id: 't', agent: 'physical', chunk: 'y'.repeat(900) } })))
      s.recordTurn(events)
    }
    expect(s.data().turns).toHaveLength(40)
    expect(s.data().turns.at(-1).display).not.toBeNull()
  })
})
