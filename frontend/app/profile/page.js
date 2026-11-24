'use client'

import { useMemo } from 'react'

import HealthProfile from '@/components/HealthProfile'
import PageShell from '@/components/PageShell'
import { useRequireAuth } from '@/hooks/useAuth'
import { guestStore } from '@/lib/guestStore'

/** The health profile (P5.3, Part E #42), for a guest or an account. */
export default function ProfilePage() {
  const { mounted, isAuthenticated, session } = useRequireAuth({ guest: true })
  const guest = session?.mode === 'guest'
  const store = useMemo(() => (guest ? guestStore() : null), [guest])
  if (!mounted || !isAuthenticated) return null
  return (
    <PageShell
      title="Your health profile"
      description={`Holos checks every plan against what you pick here.${guest ? ' As a guest, it stays in this browser.' : ''}`}>
      <HealthProfile mode={guest ? 'guest' : 'account'} store={store} />
    </PageShell>
  )
}
