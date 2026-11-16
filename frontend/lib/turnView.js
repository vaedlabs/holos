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
const KIND_COACH = { workout: 'physical', meal: 'nutrition', practice: 'mental' }
// The events a saved answer keeps (C.5 History): the index of a held entry's card among
// them is its place in the history, which the guest store uses as its ID
const SHOWN = new Set(['section_start', 'text', 'item', 'sources', 'section_end',
                       'pending_write', 'committed', 'logged_note', 'crisis', 'notice'])

export function turnView(events) {
  const view = { own: [], summary: [], sections: [], repeats: [], crisis: null, notices: [],
                 step: null, done: false, error: null, traceId: null }
  const section = (agent) => {
    let found = view.sections.find((s) => s.agent === agent)
    if (!found) {
      found = { agent, kind: null, blocks: [], sources: [], warnings: [], removed: 0,
                error: null, cards: [] }
      view.sections.push(found)
    }
    return found
  }
  const cardSection = (kind) => (KIND_COACH[kind] ? section(KIND_COACH[kind])
                                                  : view.sections.at(-1) || section('physical'))
  let shown = 0
  for (const event of events) {
    const name = event.name ?? event.event
    const { seq, trace_id: traceId, ...data } = event.data || {} // the envelope isn't shown
    view.traceId ??= traceId ?? null
    const index = SHOWN.has(name) ? shown++ : null
    switch (name) {
      case 'step':
        view.step = data
        break
      case 'section_start':
        section(data.agent).kind = data.kind
        break
      case 'text':
        if (data.agent) section(data.agent).blocks.push({ type: 'text', text: data.chunk })
        else (data.summary ? view.summary : view.own).push(data.chunk)
        break
      case 'item': {
        const { blocks } = section(data.agent)
        if (blocks.at(-1)?.type !== 'items') blocks.push({ type: 'items', items: [] })
        blocks.at(-1).items.push({ ...data.item, display: data.display,
                                   caveats: data.caveats || [] })
        break
      }
      case 'sources':
        section(data.agent).sources = data.sources
        break
      case 'section_end': {
        const s = section(data.agent)
        s.removed = data.removed_count || 0
        s.warnings = data.warnings || []
        s.error = data.error || null
        break
      }
      case 'committed':
        for (const write of data.writes) {
          cardSection(write.kind).cards.push({ type: 'logged', summary: write.summary,
                                               warnings: write.warnings || [], note: null })
        }
        break
      case 'logged_note': {
        const card = view.sections.flatMap((s) => s.cards).find((c) => c.type === 'logged')
        if (card) card.note = data.text
        break
      }
      case 'pending_write': {
        const card = { type: 'held', index, state: data.state ?? 'waiting', ...data }
        if (data.repeat_of) view.repeats.push(card) // one card for all of them (#67)
        else cardSection(data.kind ?? data.entry?.kind).cards.push(card)
        break
      }
      case 'crisis':
        view.crisis = data
        break
      case 'notice':
        view.notices.push(data)
        break
      case 'done':
        view.done = true
        break
      case 'error':
        view.error = data
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
