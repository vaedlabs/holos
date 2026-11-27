// @ts-check
/**
 * The Content Security Policy every page is sent with (Plan C.6, P5.5): scripts only from the
 * app, with this request's nonce, or Cloudflare's Turnstile; nothing else framed but Turnstile;
 * fetches only to the app and the API. Inline styles are allowed: Radix, Sonner and NumberFlow set
 * them (D063). In development, React's error details need `eval` and hot reload needs a
 * websocket: allowed there only (owner, 27 Nov 2026, Part E #80).
 */

const TURNSTILE = 'https://challenges.cloudflare.com'

/** A fresh, unguessable nonce for one request. */
export function newNonce() {
  return btoa(crypto.randomUUID())
}

/**
 * @param {{ nonce: string, apiOrigin: string, dev?: boolean }} options
 * @returns {string} the header's value
 */
export function contentSecurityPolicy({ nonce, apiOrigin, dev = false }) {
  const directives = {
    'default-src': ["'self'"],
    'script-src': ["'self'", `'nonce-${nonce}'`, TURNSTILE, ...(dev ? ["'unsafe-eval'"] : [])],
    'frame-src': [TURNSTILE],
    // 'self' for the App Router's own fetches of the next page
    'connect-src': ["'self'", apiOrigin, ...(dev ? ['ws:'] : [])],
    'img-src': ["'self'", 'blob:', 'data:'],
    'style-src': ["'self'", "'unsafe-inline'"],
    'object-src': ["'none'"],
    'base-uri': ["'none'"],
    'frame-ancestors': ["'none'"],
  }
  return Object.entries(directives).map(([name, sources]) => `${name} ${sources.join(' ')}`).join('; ')
}

/** "http://localhost:8000/" → "http://localhost:8000". @param {string} url */
export const originOf = (url) => new URL(url).origin
