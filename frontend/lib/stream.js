// @ts-check
/**
 * The chat stream (Plan C.5, P5.1): one request's events, in order, through dropped
 * connections (Part E #34).
 *
 *   const result = await sendChat({ message, timezone }, { image, onEvent, onStatus })
 *   // {outcome: 'done' | 'error' | 'refused', code, message, keepMessage, clientRequestId}
 *   if (result.keepMessage) await sendChat(sameInput, handlers)  // Retry: a new request ID
 *   await sendChat(sameInput, { ...handlers, clientRequestId })   // after `interrupted`
 *
 * `onEvent({name, data})` gets each event once, by `seq`. `onStatus('reconnecting')`
 * when the stream goes quiet (no event or ping for 20 s) or the network drops, then
 * `onStatus('live')` once it is back. A reconnect asks for the events after the last
 * `seq`, 5 times with a growing wait, then the answer is `interrupted`. A reconnect that
 * finds no request (404) means a crisis stream, which the server doesn't save: the
 * message is sent again, and the helplines come at once (Part E #59, F10).
 *
 * The message stays in the box after anything but a finished answer (`keepMessage`), so
 * Retry sends it again with a new request ID (Part E #58: `connection`). After
 * `interrupted` the server may have finished the answer, saved entries included, so
 * Retry sends the same request ID first: the server attaches it to that request instead
 * of answering, and logging, again (Part E #67). `duplicate_request` or `expired` means
 * it has no answer to give: then a new ID.
 */

import { API_URL, csrfToken, errorOf, forgetSession } from './api'

export const CONTRACT_VERSION = 1 // checked against contracts/ by the tests
export const SILENCE_MS = 20_000
export const BACKOFF_MS = [1000, 2000, 4000, 8000, 16000]
export const INTERRUPTED = 'Your answer was interrupted. Tap to try again.'
// A request the server can't attach to again: Retry sends it as new
export const NOT_ATTACHED = new Set(['duplicate_request', 'expired'])
const TERMINAL = new Set(['done', 'error'])

/**
 * @typedef {import('../types/app').ChatEvent} ChatEvent
 * @typedef {Extract<ChatEvent, { name: 'done' | 'error' }>} Terminal
 * @typedef {(fn: () => void) => () => void} Listen
 * @typedef {{ onOffline: Listen, onOnline: Listen }} Network
 * @typedef {{ outcome: 'done' | 'error' | 'refused', code?: string, message?: string,
 *   retryAfter?: number | null, keepMessage: boolean, clientRequestId: string,
 *   done?: Extract<ChatEvent, { name: 'done' }>['data'] }} ChatResult
 */

/** Server-sent events as they arrive in chunks: `{name, data}`, or `{ping: true}`. */
export class EventParser {
  constructor() {
    this.buffer = ''
    /** @type {string | null} */
    this.name = null
    /** @type {string[]} */
    this.data = []
  }

  /**
   * @param {string} text
   * @returns {Array<ChatEvent | { ping: true }>}
   */
  push(text) {
    this.buffer += text
    const lines = this.buffer.split('\n')
    this.buffer = lines.pop() ?? ''
    /** @type {Array<ChatEvent | { ping: true }>} */
    const out = []
    for (const line of lines) {
      if (line === '') {
        if (this.data.length) {
          try {
            // As the contract says it is; `handle` skips what has no `seq`
            out.push(/** @type {ChatEvent} */ ({ name: this.name || 'message',
                                                data: JSON.parse(this.data.join('\n')) }))
          } catch {
            // not an event of the contract: skipped
          }
        }
        this.name = null
        this.data = []
      } else if (line.startsWith(':')) {
        out.push({ ping: true })
      } else if (line.startsWith('event:')) {
        this.name = line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        this.data.push(line.slice(5).replace(/^ /, ''))
      }
      // `id:` repeats data.seq, which is what reconnects use
    }
    return out
  }
}

/**
 * Wait `ms`, or less when the network comes back.
 * @param {number} ms
 * @param {Listen} onOnline
 * @returns {Promise<void>}
 */
const pause = (ms, onOnline) => new Promise((resolve) => {
  let stop = () => {}
  const end = () => {
    clearTimeout(timer)
    stop()
    resolve()
  }
  const timer = setTimeout(end, ms)
  stop = onOnline(end)
})

/**
 * @param {Record<string, unknown>} input the payload's fields (C.7) but the envelope
 * @param {{ image?: Blob | null, onEvent?: (event: ChatEvent) => void,
 *   onStatus?: (status: 'reconnecting' | 'live') => void, fetchImpl?: typeof fetch,
 *   silenceMs?: number, backoffMs?: number[], network?: Network, resent?: boolean,
 *   clientRequestId?: string }} [options]
 * @returns {Promise<ChatResult>}
 */
export async function sendChat(input, {
  image = null, onEvent = () => {}, onStatus = () => {}, fetchImpl = fetch,
  silenceMs = SILENCE_MS, backoffMs = BACKOFF_MS, network = browserNetwork(), resent = false,
  clientRequestId = crypto.randomUUID(),
} = {}) {
  const payload = { contract_version: CONTRACT_VERSION, ...input,
                    client_request_id: clientRequestId }
  let lastSeq = -1
  /** @type {Terminal | null} */
  let terminal = null
  /** @type {AbortController | null} */
  let current = null // the AbortController of the open connection
  const handlers = { image, onEvent, onStatus, fetchImpl, silenceMs, backoffMs, network }

  /** @param {ChatEvent} event */
  const handle = (event) => {
    const seq = event.data?.seq
    if (typeof seq !== 'number' || seq <= lastSeq) return
    lastSeq = seq
    onEvent(event)
    if (TERMINAL.has(event.name)) terminal = /** @type {Terminal} */ (event)
  }

  /** @param {Response} response */
  const read = async (response) => {
    if (!response.body) return
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    const parser = new EventParser()
    /** @type {ReturnType<typeof setTimeout> | undefined} */
    let timer
    const quiet = () => {
      clearTimeout(timer)
      timer = setTimeout(() => current?.abort(), silenceMs)
    }
    quiet()
    try {
      while (!terminal) {
        const { done, value } = await reader.read()
        if (done) break
        quiet()
        for (const item of parser.push(decoder.decode(value, { stream: true }))) {
          if (!('ping' in item)) handle(item)
        }
      }
    } catch {
      // quiet for too long, or the connection dropped: reconnect
    } finally {
      clearTimeout(timer)
      reader.cancel().catch(() => {})
    }
  }

  /** @param {string} url @param {RequestInit} [init] */
  const connect = (url, init = {}) => {
    current = new AbortController()
    return fetchImpl(url, { ...init, credentials: 'include', signal: current.signal })
  }
  const stopListening = network.onOffline(() => current?.abort())

  try {
    // The request (C.5): its HTTP refusals come before any event
    let response = null
    for (let attempt = 0; attempt < 2 && response === null; attempt++) {
      try {
        const sent = await connect(`${API_URL}/agents/chat/stream`, {
          method: 'POST',
          headers: { 'X-CSRF-Token': (await csrfToken(fetchImpl)) || '',
                     'X-Contract-Version': String(CONTRACT_VERSION) },
          body: chatForm(payload, image),
        })
        if (sent.ok) {
          response = sent
          break
        }
        const error = await errorOf(sent)
        if (error.code === 'bad_csrf' && attempt === 0) {
          forgetSession() // a new tab or a new session: fetch the token and try once more
          continue
        }
        if (error.status === 401) forgetSession()
        return { outcome: 'refused', code: error.code, message: error.message,
                 retryAfter: error.retryAfter, keepMessage: true, clientRequestId }
      } catch {
        break // no answer at all: it may have started, so reconnect below
      }
    }
    if (response !== null) await read(response)

    // Reconnects (Part E #34): the same request, from the last event seen
    for (const wait of backoffMs) {
      if (terminal) break
      onStatus('reconnecting')
      await pause(wait, network.onOnline)
      let again
      try {
        again = await connect(
          `${API_URL}/agents/chat/stream/${clientRequestId}?after=${lastSeq}`)
      } catch {
        continue
      }
      if (again.status === 404 && !resent) { // a crisis stream: never saved
        stopListening()
        return sendChat(input, { ...handlers, resent: true })
      }
      if (again.status === 410) {
        const error = await errorOf(again)
        return { outcome: 'error', code: error.code, message: error.message,
                 keepMessage: true, clientRequestId }
      }
      if (!again.ok) continue
      onStatus('live')
      await read(again)
    }
  } finally {
    stopListening()
  }

  // Set inside `handle`, which the checker can't follow from here
  const end = /** @type {Terminal | null} */ (terminal)
  if (!end) {
    return { outcome: 'error', code: 'interrupted', message: INTERRUPTED, keepMessage: true,
             clientRequestId }
  }
  if (end.name === 'done') {
    return { outcome: 'done', keepMessage: false, clientRequestId, done: end.data }
  }
  return { outcome: 'error', code: end.data.code, message: end.data.message,
           retryAfter: end.data.retry_after ?? null, keepMessage: true, clientRequestId }
}

/**
 * The request ID Retry sends after a failed answer (Part E #67): after `interrupted`, the
 * same ID once, so the server's answer comes back if it finished; null for a new one.
 * The same ID interrupted again means the server's request ended there (its worker
 * stopped), and replaying it would show the same interruption at every tap.
 */
/**
 * @param {ChatResult} result
 * @param {{ requestId?: string | null } | null} [again]
 * @returns {string | null}
 */
export function retryId(result, again = null) {
  if (result.code !== 'interrupted' || again?.requestId) return null
  return result.clientRequestId
}

/**
 * The request body (C.7): the payload part, and the photo as one upload.
 * @param {Record<string, unknown>} payload
 * @param {Blob | null} image
 */
function chatForm(payload, image) {
  const form = new FormData()
  form.append('payload', JSON.stringify(payload))
  if (image) form.append('image', image, 'photo.jpg')
  return form
}

/**
 * The browser's network events; none outside a browser (tests pass their own).
 * @returns {Network}
 */
function browserNetwork() {
  /** @param {string} name @returns {Listen} */
  const listen = (name) => (fn) => {
    if (typeof window === 'undefined') return () => {}
    window.addEventListener(name, fn)
    return () => window.removeEventListener(name, fn)
  }
  return { onOffline: listen('offline'), onOnline: listen('online') }
}
