'use client'

import { useMemo } from 'react'

import DemoNotice from '@/components/DemoNotice'
import HealthProfile from '@/components/HealthProfile'
import HeaderMenu from '@/components/HeaderMenu'
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
      section="Health profile"
      end={<HeaderMenu guest={guest} />}
      title="Your health profile"
      description={`Holos checks every plan and meal against what you pick here.${guest ? ' As a guest, it stays in this browser.' : ''}`}>
      <DemoNotice />
      {/* In a card, as on onboarding and the preferences page */}
      <section className="rounded-xl border bg-card p-5 text-card-foreground shadow-card sm:p-6">
        <HealthProfile mode={guest ? 'guest' : 'account'} store={store} />
      </section>
    </PageShell>
  )
}
