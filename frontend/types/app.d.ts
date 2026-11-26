// The contract shapes as the app holds them (R9, Part E #74). Written by hand, from the
// generated contracts only: a field renamed in contracts/schema fails `npm run typecheck`.

import type { HistoryPage, StreamEvent } from './contracts'

type Named<E> = E extends { event: infer N; data: infer D } ? { name: N; data: D } : never

/** A live event as lib/stream.js hands it on: the SSE name and the contract's data (C.5). */
export type ChatEvent = Named<StreamEvent>

/** An event as a saved answer keeps it (C.5 History, the guest store): `{event, data}`. */
export type ShownEvent = NonNullable<HistoryPage['messages'][number]['display']>[number]

/** Either, by its name: what turnView reads. */
export type AnyEvent = ChatEvent | Named<ShownEvent>

/** A held entry's card, live (`pending_write`) or saved, with its state. */
export type CardData = Extract<AnyEvent, { name: 'pending_write' }>['data'] & {
  state?: Extract<Named<ShownEvent>, { name: 'pending_write' }>['data']['state']
}

/** An event's data by name, without the envelope (`seq`, `trace_id`) a view never shows. */
export type Data<N extends AnyEvent['name']> = Omit<Extract<AnyEvent, { name: N }>['data'], 'seq' | 'trace_id'>

/** One message in the chat as app/dashboard/page.js holds it: the person's, or an answer drawn from
 * its events (live, saved in history, or a guest's from the browser). */
export type Entry = {
  key: string
  role: 'user' | 'assistant'
  text?: string | null
  photo?: string | null
  preview?: string | null
  events?: Array<ChatEvent | ShownEvent> | null
  traceId?: string | null
  live?: boolean
  saved?: boolean
  asked?: { message: string, image?: Blob | null, agents?: string[] }
}
