'use client'

import { useEffect, useState } from 'react'
import { CircleAlert } from 'lucide-react'

import HeaderMenu from '@/components/HeaderMenu'
import PageShell from '@/components/PageShell'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import { useRequireAuth } from '@/hooks/useAuth'
import { api } from '@/lib/api'

import DataControls from './sections/DataControls'
import PreferencesForm from './sections/PreferencesForm'
import PreferencesSummary from './sections/PreferencesSummary'

/** An account's preferences: what's saved, a form to change it, and the account's data controls. */
export default function PreferencesPage() {
  const { mounted, isAuthenticated } = useRequireAuth()
  const [preferences, setPreferences] = useState(undefined) // undefined while loading, null when none yet
  const [editing, setEditing] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!mounted || !isAuthenticated) return undefined
    let live = true
    api.getUserPreferences()
      .then((data) => { if (live) setPreferences(data) })
      .catch((err) => {
        if (!live) return
        setPreferences(null)
        // None saved yet is a 404, not a failure (D062 B4); a 401 goes to sign-in on its own
        if (err.status !== 404 && err.status !== 401) setError(err.message || 'Failed to load preferences')
      })
    return () => { live = false }
  }, [mounted, isAuthenticated])

  if (!mounted || !isAuthenticated) return null

  return (
    <PageShell section="Preferences" end={<HeaderMenu />} title="Your preferences">
      {error && (
        <Alert variant="destructive">
          <CircleAlert />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {preferences === undefined ? (
        <div role="status" aria-label="Loading your preferences" className="flex flex-col gap-3">
          <Skeleton className="h-6 w-1/3" />
          <Skeleton className="h-32 w-full rounded-xl" />
        </div>
      ) : editing ? (
        <PreferencesForm preferences={preferences}
                         onSaved={(updated) => { setPreferences(updated); setEditing(false) }}
                         onCancel={() => setEditing(false)} />
      ) : (
        <PreferencesSummary preferences={preferences} onEdit={() => setEditing(true)} />
      )}
      <DataControls />
    </PageShell>
  )
}
