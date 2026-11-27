// @ts-check
/**
 * An answer's trace as the person reads it (P5.6; C.5 `TraceView`, Part E #39): the route, the
 * safety checks with their rule IDs, and each coach with a few words on what it did and its
 * time (owner, 27 Nov 2026, Part E #79). The words come from the answer itself (its items,
 * removals, entries, sources) and the coach's tools: no model writes them, so they cost
 * nothing and always match what the answer shows. Model calls, retries and cost stay out.
 * The trace holds no text the person wrote, so nothing here can show any.
 *
 * @typedef {import('../types/contracts').TraceView} TraceView
 * @typedef {NonNullable<TraceView['decisions']>[number]} Decision
 * @typedef {import('./turnView').TurnView} TurnView
 */

import { COACHES } from './turnView'

/** @type {Record<string, string>} */
const ROUTES = {
  coaching: 'Coaching', greeting: 'Greeting', meta: 'About Holos', off_topic: 'Off topic',
  unclear: 'Unclear question', other_language: 'Another language', crisis: 'Crisis',
}

/** @type {Record<string, string>} */
const ACTIONS = { block: 'Removed', warn: 'Warned', allow: 'Allowed' }

// Each coach's items and entries, as it says them
/** @type {Record<string, [string, string]>} */
const ITEMS = { physical: ['exercise', 'exercises'], nutrition: ['food', 'foods'], mental: ['practice', 'practices'] }
/** @type {Record<string, string>} */
const ENTRY = { physical: 'workout', nutrition: 'meal', mental: 'practice' }
/** @type {Record<string, string>} an entry's kind to its coach */
const KIND_COACH = { workout: 'physical', meal: 'nutrition', practice: 'mental' }
// A rule belongs to the coach whose answers it checks, by its ID's prefix (rules.yaml: EX- exercise,
// DI- diet, MN- mental); the gate's own (GT-) and others, to the only coach there is
/** @type {Record<string, string>} */
export const RULE_COACH = { EX: 'physical', DI: 'nutrition', MN: 'mental' }
// A write tool belongs to its coach; a read or a search, to the only coach there is
/** @type {Record<string, string>} */
const TOOL_COACH = { log_workout: 'physical', log_meal: 'nutrition', log_practice: 'mental' }

/** "mindfulness_meditation" as "Mindfulness meditation". @param {string} slug */
const words = (slug) => {
  const text = slug.replace(/[_-]+/g, ' ').trim()
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** 5 → "5 ms", 8800 → "8.8 s", 61000 → "1 min 1 s". @param {number} ms */
export function duration(ms) {
  if (ms < 1000) return `${Math.round(ms)} ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`
  return `${Math.floor(ms / 60_000)} min ${Math.round((ms % 60_000) / 1000)} s`
}

/** @param {number} n @param {string} one @param {string} [many] */
const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`

/**
 * One line per item: a rule that fired on the first try and again on the retry, or two rules on
 * the same item, read as one line with each rule and each reason once (owner, 27 Nov 2026). A
 * decision naming no item keeps a line of its own, by its rule.
 * @param {Decision[]} decisions
 */
export function groupDecisions(decisions) {
  /** @type {Map<string, { action: string, item: string | null, rules: string[], reasons: string[] }>} */
  const lines = new Map()
  for (const d of decisions) {
    const items = d.offending_items?.length ? d.offending_items : [null]
    for (const item of items) {
      const key = JSON.stringify([d.action, item ?? d.rule_id, item === null])
      const line = lines.get(key) ?? { action: d.action, item, rules: [], reasons: [] }
      if (!line.rules.includes(d.rule_id)) line.rules.push(d.rule_id)
      if (!line.reasons.includes(d.reason)) line.reasons.push(d.reason)
      lines.set(key, line)
    }
  }
  return [...lines.values()]
}

/**
 * What each coach did, in a few words: "Suggested 4 exercises, removed 2", "Logged a meal,
 * checked recent logs", "All suggestions removed", "Couldn't answer this time". At most three parts.
 * @param {TraceView} trace
 * @param {Pick<TurnView, 'sections' | 'repeats'>} view
 */
export function coachLines(trace, view) {
  const { steps = [], tools = [], decisions = [] } = trace
  const only = view.sections.length === 1 ? view.sections[0].agent : null
  const ruleCoach = (/** @type {string} */ id) => RULE_COACH[id.split('-')[0]] ?? only
  return view.sections.map((s) => {
    const ms = steps.filter((st) => st.name === 'coach' && st.agent === s.agent)
      .reduce((sum, st) => sum + st.duration_ms, 0)
    const took = ms > 0 ? duration(ms) : null
    const who = COACHES[s.agent] ?? words(s.agent)
    if (s.error) return { who, did: "Couldn't answer this time", took }
    const [one, many] = ITEMS[s.agent] ?? ['item', 'items']
    const entry = ENTRY[s.agent] ?? 'entry'
    const items = s.blocks.reduce((n, b) => n + (b.type === 'items' ? b.items.length : 0), 0)
    const logged = s.cards.filter((c) => c.type === 'logged').length
    const held = s.cards.filter((c) => c.type === 'held').length
      + view.repeats.filter((r) => (r.kind ? KIND_COACH[r.kind] : only) === s.agent).length
    const used = new Set(tools.filter((t) => (TOOL_COACH[t.name] ?? only) === s.agent).map((t) => t.name))
    // Nothing left to show because the gate removed it: said so, not "gave advice"
    const blocked = decisions.some((d) => d.action === 'block' && ruleCoach(d.rule_id) === s.agent)
    const parts = [
      items === 0 && blocked && 'all suggestions removed',
      items > 0 && `suggested ${plural(items, one, many)}`,
      s.removed > 0 && `removed ${s.removed}`,
      logged > 0 && (logged === 1 ? `logged a ${entry}` : `logged ${logged} ${entry}s`),
      held > 0 && (held === 1 ? `a ${entry} to confirm` : `${held} ${entry}s to confirm`),
      s.sources.length > 0 ? plural(s.sources.length, 'source') : used.has('web_search') && 'searched the web',
      used.has('get_recent_logs') && 'checked recent logs',
    ].filter(Boolean).slice(0, 3)
    const did = parts.length ? parts.join(', ') : 'gave advice'
    return { who, did: did.charAt(0).toUpperCase() + did.slice(1), took }
  })
}

/**
 * @param {TraceView} trace
 * @param {Pick<TurnView, 'sections' | 'repeats'>} view
 */
export function traceView(trace, view) {
  // Lists the server always sends, though the contract marks them optional (they have defaults)
  const { steps = [], decisions: made = [], agents = [] } = trace
  const end = Math.max(0, ...steps.map((s) => s.start_ms + s.duration_ms))
  const decisions = groupDecisions(made).map((d) => ({
    ...d, label: ACTIONS[d.action] ?? words(d.action), blocked: d.action === 'block',
  }))
  const removed = decisions.filter((d) => d.blocked).length // items removed, not rule firings
  return {
    route: [ROUTES[trace.route] ?? words(trace.route), ...agents.map((a) => COACHES[a] ?? words(a))].join(' · '),
    decisions,
    coaches: coachLines(trace, view),
    // The closed line: what stands out first
    summary: [end > 0 && duration(end), removed > 0 && plural(removed, 'safety removal')].filter(Boolean).join(' · '),
  }
}
