'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { CircleAlert, List, Menu, MessageCircle, RotateCcw } from 'lucide-react'

import AuthImage from '@/components/AuthImage'
import LogsPanel, { PANEL_ID } from '@/components/logs/LogsPanel'
import PromptBar from '@/components/ai/PromptBar'
import AnswerEntry from '@/components/chat/AnswerEntry'
import { Alert, AlertDescription } from '@/components/ui/alert'
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { useRequireAuth } from '@/hooks/useAuth'
import { api, signOut } from '@/lib/api'
import { guestStore } from '@/lib/guestStore'
import { shrinkPhoto } from '@/lib/image'
import { NOT_ATTACHED, retryId, sendChat } from '@/lib/stream'
import { COACHES, stepStatus } from '@/lib/turnView'

/**
 * The chat (Plan C.5, P5.3). Guests keep their history in this browser (P5.2); an
 * account's comes from GET /conversation/messages in pages (C.21). Every answer, live
 * or saved, is drawn from its events by `turnView`, so a reload shows what was shown.
 */

const zone = () => Intl.DateTimeFormat().resolvedOptions().timeZone

// Within this distance of the bottom, a growing answer keeps the page scrolled to it
const FOLLOW_PX = 160

export default function ChatPage() {
  const { mounted, isAuthenticated, session } = useRequireAuth({ guest: true })
  if (!mounted || !isAuthenticated) return null
  // Mounted once the session is known, so a guest's history is read as the chat's first state
  return <Chat guest={session.mode === 'guest'} />
}

function Chat({ guest }) {
  const router = useRouter()
  const store = useMemo(() => (guest ? guestStore() : null), [guest])

  const [entries, setEntries] = useState(() => (store ? guestEntries(store) : [])) // {key, role, text, photo, events, traceId, live}
  const [before, setBefore] = useState(null)
  const [draft, setDraft] = useState('')
  const [photo, setPhoto] = useState(null)
  const [coaches, setCoaches] = useState([])
  const [status, setStatus] = useState('')
  const [failed, setFailed] = useState(null) // {message, input, again}: the message stays
  const [sending, setSending] = useState(false)
  const [logsOpen, setLogsOpen] = useState(false)
  const [confirmClear, setConfirmClear] = useState(false)
  const bottom = useRef(null)
  const following = useRef(true)

  // An account's newest page of history
  useEffect(() => {
    if (guest) return undefined
    let live = true
    api.getConversationHistory().then((page) => {
      if (!live) return
      setEntries(page.messages.map(fromHistory))
      setBefore(page.before)
    }).catch((err) => live && setFailed({ message: err.message }))
    return () => { live = false }
  }, [guest])

  // Follow the answer as it grows, unless the person has scrolled up to read
  useEffect(() => {
    const onScroll = () => {
      const { scrollHeight } = document.documentElement
      following.current = window.innerHeight + window.scrollY >= scrollHeight - FOLLOW_PX
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])
  useEffect(() => {
    if (following.current) bottom.current?.scrollIntoView?.({ block: 'end' })
  }, [entries])

  const older = useCallback(async () => {
    if (!before) return
    following.current = false
    const page = await api.getConversationHistory({ before })
    setEntries((prev) => [...page.messages.map(fromHistory), ...prev])
    setBefore(page.before)
  }, [before])

  // `again`: Retry after an interrupted answer, into the same place; with its request ID,
  // the server's answer if it has one, so nothing is answered or logged twice (#67)
  const send = useCallback(async function run({ message, image, agents }, again = null) {
    setSending(true)
    setFailed(null)
    following.current = true
    const key = again?.key ?? `live-${Date.now()}`
    if (again) {
      setEntries((prev) => prev.map((e) => (e.key === key ? { ...e, events: [], live: true } : e)))
    } else {
      setEntries((prev) => [...prev,
        { key: `${key}-q`, role: 'user', text: message, preview: image ? URL.createObjectURL(image) : null },
        { key, role: 'assistant', events: [], live: true, asked: { message, image } }])
    }
    const events = []
    const input = { message, timezone: zone(), ...(agents?.length ? { agents } : {}) }
    const result = await sendChat(guest ? store.chatInput(message, input) : input, {
      image,
      ...(again?.requestId ? { clientRequestId: again.requestId } : {}),
      onEvent: (event) => {
        events.push(event)
        if (event.name === 'step') setStatus((prev) => stepStatus(prev, event.data.name))
        setEntries((prev) => prev.map((e) => (e.key === key
          ? { ...e, events: [...events], traceId: event.data.trace_id ?? e.traceId } : e)))
      },
      onStatus: (s) => setStatus(s === 'reconnecting' ? 'Reconnecting…' : ''),
    })
    setStatus('')
    setSending(false)
    if (result.outcome === 'done') {
      if (guest) store.recordTurn(events)
      setEntries((prev) => prev.map((e) => (e.key === key ? { ...e, live: false } : e)))
      return
    }
    if (again?.requestId && NOT_ATTACHED.has(result.code)) { // no answer to attach to
      await run({ message, image, agents }, { key, requestId: null })
      return
    }
    if (result.outcome === 'refused' && !again) { // nothing came: the question goes back in the box
      setEntries((prev) => prev.filter((e) => !e.key.startsWith(key)))
    }
    setFailed({ message: result.message, input: { message, image, agents },
                again: result.code === 'interrupted'
                  ? { key, requestId: retryId(result, again) } : null })
  }, [guest, store])

  const submit = async () => {
    const message = draft.trim()
    if (!message || sending) return
    setDraft('')
    const image = photo
    setPhoto(null)
    await send({ message, image, agents: coaches })
  }

  const attach = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    try {
      setPhoto(await shrinkPhoto(file))
    } catch (err) {
      setFailed({ message: err.message })
    }
  }

  const leave = async () => {
    if (guest) await store.clearMyData()
    else await signOut()
    router.push('/')
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-(--z-header) border-b bg-card/90 backdrop-blur supports-backdrop-filter:bg-card/75">
        <div className="relative mx-auto flex h-(--header-height) max-w-chat items-center justify-between px-4">
          <span className="font-heading text-xl font-bold tracking-tight">Holos</span>
          <nav className="flex items-center gap-1" aria-label="Main">
            {/* A guest has it too: their panel says the logs come with signing in (owner, 24 Nov 2026) */}
            <Button type="button" variant="ghost" aria-expanded={logsOpen} aria-controls={PANEL_ID}
                    onClick={() => setLogsOpen((prev) => !prev)}>
              <List /> Logs
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button type="button" variant="ghost" size="icon" aria-label="Menu"><Menu /></Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuItem asChild><Link href="/profile">Health profile</Link></DropdownMenuItem>
                {!guest && <DropdownMenuItem asChild><Link href="/preferences">Preferences</Link></DropdownMenuItem>}
                {guest ? (
                  <DropdownMenuItem variant="destructive" onSelect={() => setConfirmClear(true)}>
                    Clear my data
                  </DropdownMenuItem>
                ) : (
                  <DropdownMenuItem onSelect={leave}>Sign out</DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </nav>
          <LogsPanel open={logsOpen} guest={guest} />
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-chat flex-1 flex-col gap-6 px-4 pt-6 pb-4" aria-live="polite">
        {before && (
          <Button type="button" variant="ghost" className="self-center" onClick={older}>
            Show earlier messages
          </Button>
        )}
        {entries.length === 0 && (
          <Empty className="my-auto">
            <EmptyHeader>
              <EmptyMedia variant="icon"><MessageCircle /></EmptyMedia>
              <EmptyTitle>Ask about a workout, a meal or how you feel</EmptyTitle>
              <EmptyDescription>
                Holos checks every answer against your health profile.{' '}
                {guest && <Link href="/profile" className="text-primary underline underline-offset-2">Add your health profile</Link>}
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        )}
        {entries.map((e) => (e.role === 'user' ? (
          <div key={e.key}
               className="flex max-w-[85%] flex-col gap-2 self-end rounded-xl bg-primary-tint px-3.5 py-2.5 text-primary-tint-foreground">
            {e.photo && (
              <AuthImage imagePath={e.photo} alt="Your photo" className="max-h-60 w-auto rounded-lg" />
            )}
            {/* eslint-disable-next-line @next/next/no-img-element -- a blob: URL of the photo just picked */}
            {e.preview && <img src={e.preview} alt="Your photo" className="max-h-60 w-auto rounded-lg" />}
            <p className="m-0 whitespace-pre-wrap">{e.text}</p>
          </div>
        ) : (
          <AnswerEntry key={e.key} entry={e} guest={guest} store={store} status={status}
                       onRetry={e.saved || e.live ? null
                         : (agent) => send({ ...e.asked, agents: [agent] })} />
        )))}
        <div ref={bottom} />
      </main>

      <div className="sticky bottom-0 bg-linear-to-t from-background from-70% to-transparent pt-4">
        <div className="mx-auto flex max-w-chat flex-col gap-2 px-3 pb-3">
          {failed && (
            <Alert variant="destructive">
              <CircleAlert />
              <AlertDescription className="flex flex-wrap items-center justify-between gap-2">
                {failed.message}
                {failed.input && (
                  <Button type="button" variant="outline" size="sm" disabled={sending}
                          onClick={() => send(failed.input, failed.again)}>
                    <RotateCcw /> Retry
                  </Button>
                )}
              </AlertDescription>
            </Alert>
          )}
          <PromptBar value={draft} onChange={setDraft} onSubmit={submit} sending={sending}
                     photo={photo} onPhoto={attach} onRemovePhoto={() => setPhoto(null)}
                     coaches={COACHES} chosen={coaches} onChoose={setCoaches} />
        </div>
      </div>

      <AlertDialog open={confirmClear} onOpenChange={setConfirmClear}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Clear your data from this browser?</AlertDialogTitle>
            <AlertDialogDescription>
              Your chat, logs and health profile are kept only here. Clearing them can&apos;t be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep them</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={leave}>Clear my data</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

/** A guest's history, kept in this browser (P5.2). */
function guestEntries(store) {
  return store.data().turns.map((t, i) => (t.role === 'user'
    ? { key: `g${i}`, role: 'user', text: t.content }
    : { key: `g${i}`, role: 'assistant', text: t.content, events: t.display,
        traceId: t.trace_id, saved: true }))
}

/** A message from the account's history (C.21): never retried from here. */
function fromHistory(m) {
  return m.role === 'user'
    ? { key: `h${m.id}`, role: 'user', text: m.text, photo: m.photo }
    : { key: `h${m.id}`, role: 'assistant', text: m.text, events: m.display, saved: true }
}
