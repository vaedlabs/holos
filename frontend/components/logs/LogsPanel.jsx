'use client'

import { useEffect, useRef, useState } from 'react'
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
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api } from '@/lib/api'
import { pickTab, readRemembered, remember } from '@/lib/logsTab'

import MealLogs from './MealLogs'
import PracticeLogs from './PracticeLogs'
import WorkoutLogs from './WorkoutLogs'

/**
 * The logs, in a drawer from the right opened by the header's Logs button (`children`, its
 * trigger; P5.3; owner, 25 Nov 2026: full height, its own scrolling, room for the lists). An
 * account sees its workouts, meals and practices, newest first, each deletable, loaded afresh
 * each time it opens, on the tab `pickTab` chooses (lib/logsTab.js). A guest is told the logs are there once
 * they sign in (their entries stay in the browser for the repeat check only, E067).
 */

const KINDS = {
  workouts: { label: 'Workouts', load: () => api.getWorkoutLogs(10, 0), remove: (id) => api.deleteWorkoutLog(id) },
  nutrition: { label: 'Nutrition', load: () => api.getNutritionLogs(10, 0), remove: (id) => api.deleteNutritionLog(id) },
  mental: { label: 'Mental', load: () => api.getMentalFitnessLogs(10, 0), remove: (id) => api.deleteMentalFitnessLog(id) },
}

export default function LogsPanel({ guest, children }) {
  return (
    <Sheet>
      <SheetTrigger asChild>{children}</SheetTrigger>
      <SheetContent side="right" className="gap-0 data-[side=right]:w-full data-[side=right]:sm:max-w-xl">
        <SheetHeader className="border-b pr-12">
          <SheetTitle className="font-heading text-lg font-semibold">Logs</SheetTitle>
          <SheetDescription className={guest ? undefined : 'sr-only'}>
            {guest ? 'Your logs are available once you sign in.' : 'Your workouts, meals and practices, newest first.'}
          </SheetDescription>
        </SheetHeader>
        {guest ? <GuestLogs /> : <AccountLogs />}
      </SheetContent>
    </Sheet>
  )
}

function GuestLogs() {
  return (
    <div className="flex flex-col items-start gap-3 p-4">
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
  const [tab, setTab] = useState(null) // pickTab's choice, once loaded
  const seen = useRef(null) // each kind's highest log id this time, kept with the tab picked
  const tabs = useRef(null)
  const deleted = useRef(false) // Delete was pressed: the bin the focus came from goes
  const opener = useRef(null) // the bin that asked, for the focus to go back to

  useEffect(() => {
    let live = true
    Promise.all(Object.entries(KINDS).map(([kind, k]) => k.load()
      .then((data) => [kind, data.logs || []])
      .catch(() => [kind, []])))
      .then((pairs) => {
        if (!live) return
        const loaded = Object.fromEntries(pairs)
        const picked = pickTab(loaded, readRemembered())
        seen.current = picked.seen
        remember(picked)
        setLogs(loaded)
        setTab(picked.tab)
      })
    return () => { live = false }
  }, [])

  const remove = async () => {
    const { kind, log, title } = deleting
    deleted.current = true
    setDeleting(null)
    try {
      await KINDS[kind].remove(log.id)
      setLogs((prev) => ({ ...prev, [kind]: prev[kind].filter((l) => l.id !== log.id) }))
      toast.success(`${title} deleted`)
    } catch (error) {
      toast.error(error.message || "Couldn't delete that entry.")
    }
  }
  const ask = (kind) => (log, title) => {
    opener.current = document.activeElement
    setDeleting({ kind, log, title })
  }

  return (
    <>
      <Tabs ref={tabs} value={tab ?? 'workouts'} className="min-h-0 flex-1 gap-3 p-4"
            onValueChange={(next) => {
              setTab(next)
              if (seen.current) remember({ tab: next, seen: seen.current }) // rule 2 from now on
            }}>
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
        {/* Over the drawer, like the drawer over the chat (owner, 25 Nov 2026): it dims and blurs
            the drawer only (the chat is dimmed already; max-w-xl, the drawer's width), and Esc or a
            click anywhere outside closes it as Keep it does. From sm up it sits in the drawer's
            middle (right-72 = half the drawer), near the bin; on a phone the drawer is the screen.
            After a delete the focus goes to the open tab, since the bin it came from is gone; Keep
            it returns it to the bin */}
        <AlertDialogContent className="sm:right-72 sm:left-auto sm:translate-x-1/2"
                            overlayClassName="bg-transparent supports-backdrop-filter:backdrop-blur-none after:absolute after:inset-y-0 after:right-0 after:w-full after:bg-overlay after:backdrop-blur-xs sm:after:max-w-xl"
                            onCloseAutoFocus={(e) => {
                              // Opened from state, not a trigger: the focus is sent back by hand
                              e.preventDefault()
                              const tab = tabs.current?.querySelector('[role=tab][aria-selected=true]')
                              const back = deleted.current || !opener.current?.isConnected ? tab : opener.current
                              deleted.current = false
                              back?.focus()
                            }}>
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
