/**
 * The API client (Plan C.6, P5.1): cookies on every request, the CSRF token on changes,
 * one retry with a fresh token, and the server's own message for every error.
 */

import { beforeEach, describe, expect, it } from 'vitest'

import { ApiError, currentSession, forgetSession, formErrors, rememberSession, request, signIn,
  startGuest } from '@/lib/api'

import { fakeFetch, json } from './fake_server'

beforeEach(() => forgetSession())

describe('request', () => {
  it('sends the token on a change, not on a read', async () => {
    rememberSession({ csrf_token: 'csrf-1' })
    const { fetchImpl, calls } = fakeFetch([json(200, {}), json(200, {})])
    await request('/preferences', { fetchImpl })
    await request('/preferences', { method: 'POST', body: { goals: 'run' }, fetchImpl })
    expect(calls[0].headers).not.toHaveProperty('X-CSRF-Token')
    expect(calls[1].headers['X-CSRF-Token']).toBe('csrf-1')
    expect(calls[1].body).toEqual({ goals: 'run' })
  })

  it('a stale token is fetched again and the request sent once more', async () => {
    rememberSession({ csrf_token: 'old' })
    const stale = json(403, { code: 'bad_csrf', message: 'Your session token is missing or out of date.' })
    const { fetchImpl, calls } = fakeFetch([stale, json(200, { csrf_token: 'new' }), json(200, { ok: 1 })])
    expect(await request('/preferences', { method: 'POST', body: {}, fetchImpl })).toEqual({ ok: 1 })
    expect(calls.map((c) => c.headers['X-CSRF-Token'])).toEqual(['old', undefined, 'new'])
  })

  it('a second stale token is an error, not a loop', async () => {
    rememberSession({ csrf_token: 'old' })
    const stale = json(403, { code: 'bad_csrf', message: 'out of date' })
    const { fetchImpl } = fakeFetch([stale, json(200, { csrf_token: 'new' }), stale])
    await expect(request('/x', { method: 'POST', body: {}, fetchImpl }))
      .rejects.toMatchObject({ status: 403, code: 'bad_csrf' })
  })

  it("the server's message is the error's", async () => {
    const { fetchImpl } = fakeFetch([json(409, { code: 'logged', message: 'This entry is already logged.' })])
    const error = await request('/x', { fetchImpl }).catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect([error.status, error.code, error.message]).toEqual([409, 'logged', 'This entry is already logged.'])
  })

  it('a field error keeps its details', async () => {
    const details = [{ loc: ['body', 'age'], msg: 'too young' }]
    const { fetchImpl } = fakeFetch([json(422, { code: 'bad_request', message: 'Check the form.', details })])
    expect(await request('/x', { fetchImpl }).catch((e) => e.details)).toEqual(details)
  })

  it('a field error names the field: a form shows it under that field (Part E #73)', async () => {
    const fields = { email: 'not a valid address', token: 'at least 16 characters' }
    const { fetchImpl } = fakeFetch([json(422, { code: 'bad_request',
                                                  message: "Some of what was sent isn't valid.", fields })])
    const error = await request('/x', { fetchImpl }).catch((e) => e)
    expect(error.fields).toEqual(fields)
    expect(formErrors(error, ['email', 'password']))
      .toEqual({ fields: { email: 'Not a valid address' }, message: '' })
    // None of the form's own fields: the message stands
    expect(formErrors(error, ['password']))
      .toEqual({ fields: {}, message: "Some of what was sent isn't valid." })
    expect(formErrors(new ApiError(409, 'taken', 'That email is taken.'), ['email']))
      .toEqual({ fields: {}, message: 'That email is taken.' })
  })

  it('no network is a message, not a crash', async () => {
    const { fetchImpl } = fakeFetch([new TypeError('Failed to fetch')])
    await expect(request('/x', { fetchImpl })).rejects.toMatchObject({ code: 'network' })
  })
})

describe('sessions', () => {
  it('a sign-in keeps its token for the next change', async () => {
    const { fetchImpl, calls } = fakeFetch([
      json(200, { mode: 'account', csrf_token: 'csrf-a', user: { id: 1 } }), json(204)])
    await signIn('a@example.com', 'pw', fetchImpl)
    await request('/auth/logout', { method: 'POST', fetchImpl })
    expect(calls[0].headers).not.toHaveProperty('X-CSRF-Token') // no session yet
    expect(calls[1].headers['X-CSRF-Token']).toBe('csrf-a')
  })

  it('a guest start sends the Turnstile token', async () => {
    const { fetchImpl, calls } = fakeFetch([json(200, { mode: 'guest', csrf_token: 'g' })])
    expect((await startGuest('XXXX.DUMMY.TOKEN.XXXX', fetchImpl)).mode).toBe('guest')
    expect(calls[0].body).toEqual({ turnstile_token: 'XXXX.DUMMY.TOKEN.XXXX' })
  })

  it('no session is null, not an error', async () => {
    const { fetchImpl } = fakeFetch([json(401, { code: 'no_session', message: 'Your session has ended.' })])
    expect(await currentSession(fetchImpl)).toBeNull()
  })
})
