'use client'

import { useMemo } from 'react'
import Link from 'next/link'

import HealthProfile from '@/components/HealthProfile'
import { useRequireAuth } from '@/hooks/useAuth'
import { guestStore } from '@/lib/guestStore'

/** The health profile (P5.3, Part E #42), for a guest or an account. */
export default function ProfilePage() {
  const { mounted, isAuthenticated, session } = useRequireAuth({ guest: true })
  const guest = session?.mode === 'guest'
  const store = useMemo(() => (guest ? guestStore() : null), [guest])
  if (!mounted || !isAuthenticated) return null
  return (
    <div className="profile-page">
      <header className="chat-header">
        <span className="chat-brand">Holos</span>
        <Link href="/dashboard" className="btn btn-outline">Back to chat</Link>
      </header>
      <main className="profile-main">
        <h1>Your health profile</h1>
        <p className="text-muted">
          Holos checks every plan against what you pick here.{guest &&
          ' As a guest, it stays in this browser.'}
        </p>
        <HealthProfile mode={guest ? 'guest' : 'account'} store={store} />
      </main>
    </div>
  )
}
