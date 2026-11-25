// @vitest-environment jsdom
/**
 * Onboarding (P5.3): optional answers left empty are sent as "not given" (null), so the
 * last step saves. Found live, 15 Nov 2026: an empty age ("") was refused (422) and a
 * new account could not finish.
 */

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import OnboardingPage from '@/app/onboarding/page'
import { forgetSession, rememberSession } from '@/lib/api'

const push = vi.fn()
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }))
vi.mock('@/hooks/useAuth', () => ({
  useRequireAuth: () => ({ mounted: true, isAuthenticated: true, session: { mode: 'account' } }),
}))

afterEach(() => { cleanup(); vi.unstubAllGlobals(); forgetSession() })

it('finishing with the optional answers left empty saves them as not given', async () => {
  rememberSession({ csrf_token: 'c' })
  const posts = []
  vi.stubGlobal('fetch', vi.fn(async (url, init = {}) => {
    const route = `${init.method || 'GET'} ${new URL(url).pathname}`
    if (init.body) posts.push({ route, body: JSON.parse(init.body) })
    const ok = (body) => new Response(JSON.stringify(body), {
      status: 200, headers: { 'content-type': 'application/json' } })
    if (route === 'GET /profile/check') return ok({ conditions: [], allergens: [], diets: [], unchecked: [] })
    if (route.startsWith('POST')) return ok(JSON.parse(init.body))
    return new Response(JSON.stringify({ code: 'not_found', message: 'none' }), {
      status: 404, headers: { 'content-type': 'application/json' } })
  }))
  render(<OnboardingPage />)
  fireEvent.click(await screen.findByRole('button', { name: /next/i }))
  // Nothing changed on the health step: it goes straight on
  fireEvent.click(await screen.findByRole('button', { name: 'Continue' }))
  fireEvent.click(await screen.findByRole('button', { name: /Complete setup/ }))
  await waitFor(() => expect(push).toHaveBeenCalledWith('/dashboard'))
  const last = posts.filter((p) => p.route === 'POST /preferences').at(-1).body
  expect(last.age).toBeNull()
  expect(Object.values(last)).not.toContain('')
})
