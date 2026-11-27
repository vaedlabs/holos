/**
 * The CSP of Plan C.6, as lib/csp.js writes it (P5.5): the browser tests (tests/e2e) show it
 * working; this pins each directive, and that development alone adds 'unsafe-eval' and ws:
 * (owner, 27 Nov 2026, Part E #80).
 */

import { describe, expect, it } from 'vitest'

import { contentSecurityPolicy, newNonce, originOf } from '@/lib/csp'

const directives = (policy) => Object.fromEntries(policy.split('; ').map((d) => {
  const [name, ...sources] = d.split(' ')
  return [name, sources]
}))

describe('the CSP', () => {
  it('is C.6, with this request\'s nonce and the API', () => {
    expect(directives(contentSecurityPolicy({ nonce: 'abc', apiOrigin: 'https://api.example.com' }))).toEqual({
      'default-src': ["'self'"],
      'script-src': ["'self'", "'nonce-abc'", 'https://challenges.cloudflare.com'],
      'frame-src': ['https://challenges.cloudflare.com'],
      'connect-src': ["'self'", 'https://api.example.com'],
      'img-src': ["'self'", 'blob:', 'data:'],
      'style-src': ["'self'", "'unsafe-inline'"],
      'object-src': ["'none'"],
      'base-uri': ["'none'"],
      'frame-ancestors': ["'none'"],
    })
  })

  it("development alone adds 'unsafe-eval' and ws:", () => {
    const dev = directives(contentSecurityPolicy({ nonce: 'abc', apiOrigin: 'http://localhost:8000', dev: true }))
    expect(dev['script-src']).toContain("'unsafe-eval'")
    expect(dev['connect-src']).toContain('ws:')
  })

  it('a nonce is new each time, and an origin is scheme and host', () => {
    expect(new Set(Array.from({ length: 50 }, newNonce)).size).toBe(50)
    expect(originOf('http://localhost:8000/')).toBe('http://localhost:8000')
  })
})
