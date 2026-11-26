'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { currentSession } from '@/lib/api'

/**
 * Who is here (Plan C.6): the session the cookie names, read from GET /session/csrf
 * (`{mode, csrf_token, expires_at}`), or null. The cookie is HttpOnly, so the page can't
 * look at it; asking the server is also the only way to know it hasn't ended.
 */
export function useSession() {
  const [state, setState] = useState(/** @type {{ loading: boolean, session: { mode: 'guest' | 'account',
    csrf_token: string, expires_at: string } | null }} */ ({ loading: true, session: null }))

  useEffect(() => {
    let live = true
    currentSession()
      .then((session) => live && setState({ loading: false, session }))
      .catch(() => live && setState({ loading: false, session: null }))
    return () => { live = false }
  }, [])

  return state
}

/**
 * Pages for an account (the profile, preferences, logs): no session, or a guest's,
 * goes to sign-in. `{guest: true}` lets a guest in too (the chat).
 */
export function useRequireAuth({ guest = false } = {}) {
  const router = useRouter()
  const { loading, session } = useSession()
  const allowed = !!session && (guest || session.mode === 'account')

  useEffect(() => {
    if (!loading && !allowed) router.push('/login')
  }, [loading, allowed, router])

  return { mounted: !loading, isAuthenticated: allowed, session }
}

/** The sign-in pages: someone already signed in goes to the chat. */
export function useRedirectIfAuthenticated() {
  const router = useRouter()
  const { loading, session } = useSession()

  useEffect(() => {
    if (session?.mode === 'account') router.push('/dashboard')
  }, [session, router])

  return { mounted: !loading && session?.mode !== 'account' }
}
