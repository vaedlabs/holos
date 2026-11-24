'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { LogIn } from 'lucide-react'
import { toast } from 'sonner'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api } from '@/lib/api'

import MealLogs from './MealLogs'
import PracticeLogs from './PracticeLogs'
import WorkoutLogs from './WorkoutLogs'

/**
 * The logs panel, toggled by the header's Logs button (P5.3; owner, 24 Nov 2026: the old toggle
 * panel, restyled): it hangs under the header and the chat stays usable beside it. An account
 * sees its workouts, meals and practices, newest first, each deletable, loaded afresh each time
 * it opens. A guest is told the logs are there once they sign in (their entries stay in the
 * browser for the repeat check only, E067).
 */

const KINDS = {
  workouts: { label: 'Workouts', load: () => api.getWorkoutLogs(10, 0), remove: (id) => api.deleteWorkoutLog(id) },
  nutrition: { label: 'Nutrition', load: () => api.getNutritionLogs(10, 0), remove: (id) => api.deleteNutritionLog(id) },
  mental: { label: 'Mental', load: () => api.getMentalFitnessLogs(10, 0), remove: (id) => api.deleteMentalFitnessLog(id) },
}

export const PANEL_ID = 'logs-panel'

export default function LogsPanel({ open, guest }) {
  if (!open) return null
  return (
    <section id={PANEL_ID} aria-label="Logs"
             className="absolute inset-x-4 top-full z-(--z-overlay) mt-2 flex max-h-[min(36rem,calc(100dvh-var(--header-height)-2rem))] animate-pop-in flex-col overflow-hidden rounded-xl border bg-popover text-popover-foreground shadow-popover sm:left-auto sm:w-md">
      {guest ? <GuestLogs /> : <AccountLogs />}
    </section>
  )
}

function GuestLogs() {
  return (
    <div className="flex flex-col items-start gap-3 p-5">
      <p className="m-0 font-heading text-base font-semibold">Logs</p>
      <p className="m-0 text-foreground-secondary">Your logs are available once you sign in.</p>
      <Button asChild>
        <Link href="/login"><LogIn /> Sign in</Link>
      </Button>
    </div>
  )
}

/** Mounted each time the panel opens, so the logs are loaded afresh. */
function AccountLogs() {
  const [logs, setLogs] = useState(null) // {workouts, nutrition, mental}; null while loading
  const [deleting, setDeleting] = useState(null) // {kind, log, title}
  const [tab, setTab] = useState('workouts')

  useEffect(() => {
    let live = true
    Promise.all(Object.entries(KINDS).map(([kind, k]) => k.load()
      .then((data) => [kind, data.logs || []])
      .catch(() => [kind, []])))
      .then((pairs) => { if (live) setLogs(Object.fromEntries(pairs)) })
    return () => { live = false }
  }, [])

  const remove = async () => {
    const { kind, log } = deleting
    setDeleting(null)
    try {
      await KINDS[kind].remove(log.id)
      setLogs((prev) => ({ ...prev, [kind]: prev[kind].filter((l) => l.id !== log.id) }))
    } catch (error) {
      toast.error(error.message || "Couldn't delete that entry.")
    }
  }
  const ask = (kind) => (log, title) => setDeleting({ kind, log, title })

  return (
    <>
      <Tabs value={tab} onValueChange={setTab} className="min-h-0 flex-1 gap-3 p-3">
        <TabsList className="w-full">
          {Object.entries(KINDS).map(([kind, k]) => (
            <TabsTrigger key={kind} value={kind}>{k.label}</TabsTrigger>
          ))}
        </TabsList>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {logs === null ? (
            <div role="status" aria-label="Loading your logs" className="flex flex-col gap-2">
              {[0, 1, 2].map((i) => <Skeleton key={i} className="h-20 w-full rounded-lg" />)}
            </div>
          ) : (
            <>
              <TabsContent value="workouts"><WorkoutLogs logs={logs.workouts} onDelete={ask('workouts')} /></TabsContent>
              <TabsContent value="nutrition"><MealLogs logs={logs.nutrition} onDelete={ask('nutrition')} /></TabsContent>
              <TabsContent value="mental"><PracticeLogs logs={logs.mental} onDelete={ask('mental')} /></TabsContent>
            </>
          )}
        </div>
      </Tabs>
      <AlertDialog open={deleting !== null} onOpenChange={(next) => { if (!next) setDeleting(null) }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {deleting?.title}?</AlertDialogTitle>
            <AlertDialogDescription>It comes off your logs. You can&apos;t undo this.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep it</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={remove}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
