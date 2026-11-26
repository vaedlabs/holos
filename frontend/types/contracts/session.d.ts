// Generated from contracts/schema by npm run contracts:types. Don't edit.

/**
 * Who is here, as a session start, sign-in or GET /session/csrf answers: a contract, so
 * the app's sign-in state and the guest-data offer read a checked shape (Part E #78).
 */
export interface Session {
  csrf_token: string
  expires_at: string
  mode: 'guest' | 'account'
}
