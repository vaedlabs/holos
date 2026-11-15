/**
 * A fake backend for the stream and API tests: each request is answered by the next
 * handler, and every request is recorded (method, URL, headers, the chat payload).
 */

export const encoder = new TextEncoder()

/** One event on the wire, as the backend writes it (orchestration/stream.py). */
export function wire({ name, data }) {
  return `id: ${data.seq}\nevent: ${name}\ndata: ${JSON.stringify(data)}\n\n`
}

/**
 * A streamed response: `parts` (strings) sent in order; then it closes, or with
 * `hang: true` stays open and silent until the request is aborted.
 */
export function streamed(parts, { hang = false, status = 200 } = {}) {
  return (init) => {
    const body = new ReadableStream({
      start(controller) {
        for (const part of parts) controller.enqueue(encoder.encode(part))
        if (!hang) {
          controller.close()
          return
        }
        init.signal?.addEventListener('abort', () =>
          controller.error(new DOMException('aborted', 'AbortError')))
      },
    })
    return new Response(body, { status, headers: { 'content-type': 'text/event-stream' } })
  }
}

export function json(status, body, headers = {}) {
  return () => new Response(body === undefined ? null : JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json', ...headers } })
}

export function fakeFetch(handlers) {
  const calls = []
  const queue = [...handlers]
  const fetchImpl = async (url, init = {}) => {
    const call = { url, method: init.method || 'GET', headers: init.headers || {} }
    if (init.body instanceof FormData) call.payload = JSON.parse(init.body.get('payload'))
    else if (typeof init.body === 'string') call.body = JSON.parse(init.body)
    calls.push(call)
    const next = queue.shift()
    if (!next) throw new Error(`no answer for ${call.method} ${url}`)
    if (next instanceof Error) throw next
    return next(init)
  }
  return { fetchImpl, calls }
}

/** No browser here: the tests decide when the network changes. */
export const quietNetwork = { onOffline: () => () => {}, onOnline: () => () => {} }
