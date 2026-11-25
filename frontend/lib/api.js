/**
 * The API client (Plan C.6, P5.1): cookie sessions and the CSRF token.
 *
 *   await startGuest(turnstileToken)          // a guest session
 *   await signIn(email, password)             // an account session
 *   const session = await currentSession()    // {mode, csrf_token, expires_at} or null
 *   await api.getMedicalHistory()             // any route; errors throw ApiError
 *
 * The session lives in an HttpOnly cookie the browser sends with `credentials:
 * 'include'`. State-changing requests also send X-CSRF-Token: the token arrives with the
 * session and is kept in memory only; a new tab asks GET /session/csrf. A 403
 * `bad_csrf` fetches the token again and retries once. Every error is the server's
 * `{code, message}` body, shown to the person as it is.
 */

import { forgetTab } from './logsTab'

export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const SAFE = new Set(['GET', 'HEAD', 'OPTIONS'])

// When the body says nothing (a proxy's error page, a dropped connection)
const FALLBACK = {
  network: "Holos can't be reached right now. Check your connection and try again.",
  401: 'Your session has ended. Please sign in again.',
  403: "This request wasn't allowed. Please reload the page.",
  404: "That isn't here any more.",
  413: 'That is too large to send.',
  429: "You've reached the limit for now. Please try again later.",
  500: 'Something went wrong. Please try again.',
  503: 'Holos is busy right now. Please try again in a moment.',
}

export class ApiError extends Error {
  constructor(status, code, message, retryAfter = null, details = null) {
    super(message)
    this.status = status
    this.code = code
    this.retryAfter = retryAfter
    this.details = details
  }
}

let csrf = null

/** Keep the token a session start, sign-in or GET /session/csrf returned. */
export function rememberSession(body) {
  csrf = body?.csrf_token ?? null
  return body
}

export function forgetSession() {
  csrf = null
}

/** The server's error body as an ApiError; a fallback message when it has none. */
export async function errorOf(response) {
  let body = null
  try {
    body = await response.json()
  } catch {
    body = null
  }
  const retryAfter = body?.retry_after ?? (Number(response.headers.get('retry-after')) || null)
  const message = typeof body?.message === 'string' && body.message
    ? body.message
    : FALLBACK[response.status] || FALLBACK[response.status >= 500 ? 500 : 403]
  return new ApiError(response.status, body?.code || `http_${response.status}`, message,
                      retryAfter, body?.details ?? null)
}

export async function csrfToken(fetchImpl = fetch) {
  if (csrf === null) {
    try {
      const response = await fetchImpl(`${API_URL}/session/csrf`, { credentials: 'include' })
      if (response.ok) rememberSession(await response.json())
    } catch {
      // no session, or no network: the request itself says which
    }
  }
  return csrf
}

/**
 * One request. `body` is sent as JSON, or as is when it is FormData; the result is the
 * JSON body, or null for 204. `raw: true` returns the Response (images, streams).
 */
export async function request(path, { method = 'GET', body, headers = {}, raw = false,
                                      fetchImpl = fetch, retried = false,
                                      withCsrf = !SAFE.has(method) } = {}) {
  const sent = { ...headers }
  if (withCsrf) {
    const token = await csrfToken(fetchImpl)
    if (token) sent['X-CSRF-Token'] = token
  }
  let payload = body
  if (body !== undefined && !(body instanceof FormData)) {
    sent['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  let response
  try {
    response = await fetchImpl(`${API_URL}${path}`, { method, headers: sent, body: payload,
                                                     credentials: 'include' })
  } catch {
    throw new ApiError(0, 'network', FALLBACK.network)
  }
  if (!response.ok) {
    const error = await errorOf(response)
    if (error.code === 'bad_csrf' && !retried) {
      forgetSession()
      return request(path, { method, body, headers, raw, fetchImpl, retried: true, withCsrf })
    }
    if (error.status === 401) forgetSession()
    throw error
  }
  if (raw) return response
  if (response.status === 204) return null
  return (response.headers.get('content-type') || '').includes('application/json')
    ? response.json()
    : null
}

// --- Sessions (C.6) ---
// Starting a session needs no CSRF token: the server checks the Origin instead

/** The current session, or null when there is none (401). */
export async function currentSession(fetchImpl = fetch) {
  try {
    return rememberSession(await request('/session/csrf', { fetchImpl }))
  } catch (error) {
    if (error.status === 401) return null
    throw error
  }
}

export async function startGuest(turnstileToken, fetchImpl = fetch) {
  return rememberSession(await request('/session/start', {
    method: 'POST', body: { turnstile_token: turnstileToken }, fetchImpl, withCsrf: false }))
}

export async function signIn(email, password, fetchImpl = fetch) {
  return rememberSession(await request('/auth/login', {
    method: 'POST', body: { email, password }, fetchImpl, withCsrf: false }))
}

export async function acceptInvite(token, email, password, consent, fetchImpl = fetch) {
  return rememberSession(await request('/invites/accept', {
    method: 'POST', body: { token, email, password, consent }, fetchImpl, withCsrf: false }))
}

/** Ends this session; the person is signed out even when the server can't be reached. */
export async function signOut(fetchImpl = fetch) {
  try {
    await request('/auth/logout', { method: 'POST', fetchImpl })
  } catch {
    // already gone, or offline: the cookie ends with the session anyway
  } finally {
    forgetSession()
    forgetTab() // the Logs drawer's remembered tab is this account's
  }
}

// --- The account's data ---

export const api = {
  getMedicalHistory: () => request('/medical/history'),
  updateMedicalHistory: (data) => request('/medical/history', { method: 'POST', body: data }),
  getUserPreferences: () => request('/preferences'),
  updateUserPreferences: (data) => request('/preferences', { method: 'POST', body: data }),

  // A page of the history (C.21), the newest without `before`
  getConversationHistory: ({ before } = {}) =>
    request(`/conversation/messages${Number.isInteger(before) ? `?before=${before}` : ''}`),
  clearConversationHistory: () => request('/conversation/messages', { method: 'DELETE' }),
  deleteAccount: async () => {
    await request('/auth/delete-account', { method: 'DELETE' })
    forgetSession()
  },

  getWorkoutLogs: (limit = 10, offset = 0) =>
    request(`/logs/workouts?limit=${limit}&offset=${offset}`),
  getNutritionLogs: (limit = 10, offset = 0) =>
    request(`/logs/nutrition?limit=${limit}&offset=${offset}`),
  getMentalFitnessLogs: (limit = 10, offset = 0) =>
    request(`/logs/mental-fitness?limit=${limit}&offset=${offset}`),
  deleteWorkoutLog: (id) => request(`/logs/workouts/${id}`, { method: 'DELETE' }),
  deleteNutritionLog: (id) => request(`/logs/nutrition/${id}`, { method: 'DELETE' }),
  deleteMentalFitnessLog: (id) => request(`/logs/mental-fitness/${id}`, { method: 'DELETE' }),
}
