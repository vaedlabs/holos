// @ts-check
/**
 * One answer as the person sees it (Plan C.5, P5.3; Part E #58, #61): events in, a view
 * out. The live stream and the saved history both come through here, so an answer looks
 * the same after a reload.
 *
 *   const view = turnView(events)   // live {name, data} or saved {event, data}
 *   view.sections                   // per coach: text, item tables, sources, cards
 *
 * A coach's text and items keep their order; items in a row make one table. A saved or
 * held entry's card sits in the section of the coach that logged it (by its kind), even
 * a section with no text, and the coach's sentence about it replaces the card's
 * "Logged" line when it comes (#58). Entries that repeat one already logged wait
 * together on one card after the sections, `view.repeats` (#67).
 */

export const COACHES = {
  physical: 'Exercise coach',
  nutrition: 'Food coach',
  mental: 'Mental wellbeing coach',
}
/** @type {Record<string, string>} */
const KIND_COACH = { workout: 'physical', meal: 'nutrition', practice: 'mental' }
// The events a saved answer keeps (C.5 History): the index of a held entry's card among
// them is its place in the history, which the guest store uses as its ID
const SHOWN = new Set(['section_start', 'text', 'item', 'sources', 'section_end',
                       'pending_write', 'committed', 'logged_note', 'crisis', 'notice'])

/**
 * @typedef {import('../types/app').ChatEvent} ChatEvent
 * @typedef {import('../types/app').ShownEvent} ShownEvent
 * @typedef {import('../types/app').AnyEvent} AnyEvent
 * @typedef {import('../types/app').CardData} CardData
 */
/**
 * @template {AnyEvent['name']} N
 * @typedef {import('../types/app').Data<N>} Data
 */
/**
 * @typedef {{ type: 'text', text: string } | { type: 'items', items: Item[] }} Block
 * @typedef {Data<'item'>['item'] & { display?: Data<'item'>['display'], caveats: string[] }} Item
 * @typedef {{ type: 'logged', summary: string, warnings: string[], note: string | null }} LoggedCard
 * @typedef {Omit<CardData, 'state'> & { type: 'held', index: number | null,
 *   state: NonNullable<CardData['state']> }} HeldCard
 * @typedef {{ agent: string, kind: string | null, blocks: Block[], sources: Data<'sources'>['sources'][number][],
 *   warnings: string[], removed: number, error: string | null, cards: Array<LoggedCard | HeldCard> }} Section
 * @typedef {{ own: string[], summary: string[], sections: Section[], repeats: HeldCard[],
 *   crisis: Data<'crisis'> | null, notices: Data<'notice'>[], step: Data<'step'> | null,
 *   done: boolean, error: Data<'error'> | null, traceId: string | null }} TurnView
 */

/** A live `{name, data}` or saved `{event, data}` event, by its name. */
const named = (/** @type {ChatEvent | ShownEvent} */ event) => /** @type {AnyEvent} */ (
  'name' in event ? event : { name: event.event, data: event.data })

/**
 * The data a view keeps: without the envelope.
 * @template {object} T
 * @param {T} data
 * @returns {Omit<T, 'seq' | 'trace_id'>}
 */
function bare(data) {
  const { seq: _seq, trace_id: _trace, ...rest } = /** @type {any} */ (data)
  return rest
}

/**
 * @param {Array<ChatEvent | ShownEvent>} events
 * @returns {TurnView}
 */
export function turnView(events) {
  /** @type {TurnView} */
  const view = { own: [], summary: [], sections: [], repeats: [], crisis: null, notices: [],
                 step: null, done: false, error: null, traceId: null }
  /** @param {string} agent @returns {Section} */
  const section = (agent) => {
    let found = view.sections.find((s) => s.agent === agent)
    if (!found) {
      found = { agent, kind: null, blocks: [], sources: [], warnings: [], removed: 0,
                error: null, cards: [] }
      view.sections.push(found)
    }
    return found
  }
  /** @param {string | null | undefined} kind */
  const cardSection = (kind) => (kind && KIND_COACH[kind] ? section(KIND_COACH[kind])
                                                          : view.sections.at(-1) || section('physical'))
  let shown = 0
  for (const event of events) {
    const e = named(event)
    const traceId = e.data && 'trace_id' in e.data ? e.data.trace_id : null
    view.traceId ??= traceId ?? null
    const index = SHOWN.has(e.name) ? shown++ : null
    switch (e.name) {
      case 'step':
        view.step = bare(e.data)
        break
      case 'section_start':
        section(e.data.agent).kind = e.data.kind
        break
      case 'text':
        if (e.data.agent) section(e.data.agent).blocks.push({ type: 'text', text: e.data.chunk })
        else (e.data.summary ? view.summary : view.own).push(e.data.chunk)
        break
      case 'item': {
        const { blocks } = section(e.data.agent)
        let last = blocks.at(-1)
        if (last?.type !== 'items') {
          last = { type: 'items', items: [] }
          blocks.push(last)
        }
        last.items.push({ ...e.data.item, display: e.data.display, caveats: e.data.caveats || [] })
        break
      }
      case 'sources':
        section(e.data.agent).sources = e.data.sources
        break
      case 'section_end': {
        const s = section(e.data.agent)
        s.removed = e.data.removed_count || 0
        s.warnings = e.data.warnings || []
        s.error = e.data.error || null
        break
      }
      case 'committed':
        for (const write of e.data.writes) {
          cardSection(write.kind).cards.push({ type: 'logged', summary: write.summary,
                                               warnings: write.warnings || [], note: null })
        }
        break
      case 'logged_note': {
        const card = view.sections.flatMap((s) => s.cards).find((c) => c.type === 'logged')
        if (card) card.note = e.data.text
        break
      }
      case 'pending_write': {
        const data = /** @type {CardData} */ (bare(e.data))
        /** @type {HeldCard} */
        const card = { type: 'held', index, ...data, state: data.state ?? 'waiting' }
        if (data.repeat_of) view.repeats.push(card) // one card for all of them (#67)
        else cardSection(data.kind ?? data.entry?.kind).cards.push(card)
        break
      }
      case 'crisis':
        view.crisis = bare(e.data)
        break
      case 'notice':
        view.notices.push(bare(e.data))
        break
      case 'done':
        view.done = true
        break
      case 'error':
        view.error = bare(e.data)
        break
      default:
        break
    }
  }
  return view
}

/** A week's items by day, for the table: [{day, items}] in the order the coach gave. */
export function byDay(items) {
  const days = []
  for (const item of items) {
    const last = days.at(-1)
    if (last && last.day === item.day) last.items.push(item)
    else days.push({ day: item.day, items: [item] })
  }
  return days
}

/** Only https links, for sources: the one place a link appears (C.6, #59). */
export function safeLink(url) {
  try {
    return new URL(url).protocol === 'https:' ? url : null
  } catch {
    return null
  }
}

// What the person sees while an answer is on its way (C.5 `step`)
export const STEPS = {
  admitted: 'Starting…',
  routed: 'Choosing coaches…',
  agent_started: 'Thinking…',
  tool_call: 'Looking things up…',
  composing: 'Putting it together…',
  still_working: 'Still working on it…',
}

/** The status after a step: a step with no words of its own (the gate, a retry) keeps
 * the last one, so the line never goes blank while the answer is still coming. */
export function stepStatus(current, step) {
  return STEPS[step] || current
}

/** @typedef {NonNullable<CardData['state']>} CardState */

/**
 * The held entry's card at `index` (its place among what the answer showed) with a new state:
 * the person decided it, or a newer entry replaced it. A new array; the rest as it was.
 * @param {Array<ChatEvent | ShownEvent>} events
 * @param {number} index
 * @param {CardState} state
 * @returns {Array<ChatEvent | ShownEvent>}
 */
export function settleCard(events, index, state) {
  let shown = -1
  return events.map((event) => {
    const e = named(event)
    if (SHOWN.has(e.name)) shown++
    if (shown !== index || e.name !== 'pending_write') return event
    return /** @type {ChatEvent | ShownEvent} */ ({ ...event, data: { ...e.data, state } })
  })
}

/**
 * The kinds of entry an answer holds for the person (`pending_write`): a newer held entry
 * replaces the waiting ones of its kind from earlier answers (C.17, Part E #50).
 * @param {Array<ChatEvent | ShownEvent>} events
 * @returns {Set<string>}
 */
export function heldKinds(events) {
  const kinds = new Set()
  for (const event of events) {
    const e = named(event)
    if (e.name !== 'pending_write') continue
    const kind = e.data.kind ?? e.data.entry?.kind
    if (kind) kinds.add(kind)
  }
  return kinds
}

/**
 * An earlier answer's still-waiting cards of these kinds, marked replaced, as the server marks
 * them (D067 follow-up: an account's replaced card kept its buttons until a reload). The same
 * array when nothing changes.
 * @param {Array<ChatEvent | ShownEvent>} events
 * @param {Set<string>} kinds
 * @returns {Array<ChatEvent | ShownEvent>}
 */
export function replaceWaiting(events, kinds) {
  let changed = false
  const out = events.map((event) => {
    const e = named(event)
    if (e.name !== 'pending_write') return event
    const data = /** @type {CardData} */ (e.data)
    const kind = data.kind ?? data.entry?.kind
    if (!kind || !kinds.has(kind) || (data.state ?? 'waiting') !== 'waiting') return event
    changed = true
    return /** @type {ChatEvent | ShownEvent} */ ({ ...event, data: { ...data, state: 'replaced' } })
  })
  return changed ? out : events
}
