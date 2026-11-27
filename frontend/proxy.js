import { NextResponse } from 'next/server'

import { contentSecurityPolicy, newNonce, originOf } from './lib/csp'

/**
 * Every page gets the CSP of Plan C.6 with a nonce of its own (P5.5). Next 16 calls this
 * file's `proxy` before rendering (Next's "middleware", renamed; Node only: R8, D060). Next
 * reads the nonce from the request's CSP header and puts it on its own scripts, which is why
 * the header is set on the request as well as the response (Next's CSP guide).
 */
export function proxy(request) {
  const nonce = newNonce()
  const policy = contentSecurityPolicy({
    nonce,
    apiOrigin: originOf(process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'),
    dev: process.env.NODE_ENV === 'development',
  })
  const headers = new Headers(request.headers)
  headers.set('x-nonce', nonce)
  headers.set('Content-Security-Policy', policy)
  const response = NextResponse.next({ request: { headers } })
  response.headers.set('Content-Security-Policy', policy)
  return response
}

export const config = {
  matcher: [
    {
      // Pages only: not Next's static files or images, nor the favicon; nor a link's prefetch
      source: '/((?!_next/static|_next/image|favicon.ico).*)',
      missing: [
        { type: 'header', key: 'next-router-prefetch' },
        { type: 'header', key: 'purpose', value: 'prefetch' },
      ],
    },
  ],
}
