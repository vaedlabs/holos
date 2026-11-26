// @ts-check
'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import Link from 'next/link'
import { CircleAlert, List, MessageCircle, RotateCcw } from 'lucide-react'

import AuthImage from '@/components/AuthImage'
import HeaderMenu from '@/components/HeaderMenu'
import ImportGuest from '@/components/ImportGuest'
import LogsPanel from '@/components/logs/LogsPanel'
import PromptBar from '@/components/ai/PromptBar'
import AnswerEntry from '@/components/chat/AnswerEntry'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { useRequireAuth } from '@/hooks/useAuth'
import { api } from '@/lib/api'
import { guestStore } from '@/lib/guestStore'
import { shrinkPhoto } from '@/lib/image'
import { NOT_ATTACHED, retryId, sendChat } from '@/lib/stream'
import { COACHES, heldKinds, replaceWaiting, settleCard, stepStatus } from '@/lib/turnView'

/**
 * The chat (Plan C.5, P5.3). Guests keep their history in this browser (P5.2); an
 * account's comes from GET /conversation/messages in pages (C.21). Every answer, live
 * or saved, is drawn from its events by `turnView`, so a reload shows what was shown.
 */

/**
 * @typedef {import('@/types/app').Entry} Entry
 * @typedef {{ message: string, image?: Blob | null, agents?: string[] }} Asked
 * @typedef {{ key: string, requestId: string | null }} Again
 * @typedef {{ message: string, input?: Asked, again?: Again | null }} Failed
 */

const zone = () => Intl.DateTimeFormat().resolvedOptions().timeZone

// Within this distance of the bottom, a growing answer keeps the page scrolled to it
const FOLLOW_PX = 160

export default function ChatPage() {
  const { mounted, isAuthenticated, session } = useRequireAuth({ guest: true })
  if (!mounted || !isAuthenticated) return null
  // Mounted once the session is known, so a guest's history is read as the chat's first state
  return <Chat guest={session?.mode === 'guest'} />
}

/** @param {{ guest: boolean }} props */
function Chat({ guest }) {
  const store = useMemo(() => (guest ? guestStore() : null), [guest])

  const [entries, setEntries] = useState(() => /** @type {Entry[]} */ (store ? guestEntries(store) : []))
  const [before, setBefore] = useState(/** @type {number | null | undefined} */ (null))
  const [draft, setDraft] = useState('')
  const [photo, setPhoto] = useState(/** @type {Blob | null} */ (null))
  const [coaches, setCoaches] = useState(/** @type {string[]} */ ([]))
  const [status, setStatus] = useState('')
  const [failed, setFailed] = useState(/** @type {Failed | null} */ (null)) // the message stays
  const [sending, setSending] = useState(false)
  // An account's history has come (or failed): until then the chat isn't known to be empty, so
  // the prompt bar waits rather than showing in the middle and jumping down
  const [loaded, setLoaded] = useState(guest)
  const empty = loaded && entries.length === 0
  const bottom = useRef(/** @type {HTMLDivElement | null} */ (null))
  const following = useRef(true)
  // Read again after a guest's data is saved to the account, so it shows here at once
  const [reads, setReads] = useState(0)

  // An account's newest page of history
  useEffect(() => {
    if (guest) return undefined
    let live = true
    api.getConversationHistory().then((page) => {
      if (!live) return
      setEntries(page.messages.map(fromHistory))
      setBefore(page.before)
    }).catch((err) => live && setFailed({ message: err.message }))
      .finally(() => live && setLoaded(true))
    return () => { live = false }
  }, [guest, reads])

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
  // And as it grows after that (a card popping in, a block fading in), so nothing stops
  // half-hidden behind the prompt bar (owner, 25 Nov 2026)
  const thread = useRef(/** @type {HTMLElement | null} */ (null))
  useEffect(() => {
    if (typeof ResizeObserver === 'undefined' || !thread.current) return undefined
    const grown = new ResizeObserver(() => {
      if (following.current) bottom.current?.scrollIntoView?.({ block: 'end' })
    })
    grown.observe(thread.current)
    return () => grown.disconnect()
  }, [])

  const older = useCallback(async () => {
    if (!before) return
    following.current = false
    const page = await api.getConversationHistory({ before })
    setEntries((prev) => [...page.messages.map(fromHistory), ...prev])
    setBefore(page.before)
  }, [before])

  // A card the person decided: its answer's events say so, so a newer entry replaces only
  // the cards still waiting (D067 follow-up)
  const settle = useCallback((key, index, state) => setEntries((prev) => prev.map((e) => (
    e.key === key && e.events ? { ...e, events: settleCard(e.events, index, state) } : e))), [])

  // `again`: Retry after an interrupted answer, into the same place; with its request ID,
  // the server's answer if it has one, so nothing is answered or logged twice (#67)
  const send = useCallback(/** @param {Asked} asked @param {Again | null} [again] */
    async function run({ message, image, agents }, again = null) {
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
    const result = await sendChat(store ? store.chatInput(message, input) : input, {
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
      // Earlier cards this answer's entries replaced say so at once, not after a reload: a guest's
      // redraw from the store (D064); an account's waiting ones of the same kind are marked as the
      // server marks them (D067)
      const replaced = store ? store.recordTurn(events) : []
      const shown = new Map(store ? store.data().turns.map((t) => [t.trace_id, t.display]) : [])
      const kinds = guest ? new Set() : heldKinds(events)
      setEntries((prev) => prev.map((e) => {
        if (e.key === key) return { ...e, live: false }
        if (e.traceId && replaced.includes(e.traceId) && shown.get(e.traceId)) return { ...e, events: shown.get(e.traceId) }
        if (kinds.size > 0 && e.role === 'assistant' && e.events) {
          const events = replaceWaiting(e.events, kinds)
          return events === e.events ? e : { ...e, events }
        }
        return e
      }))
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

  /** A coach that failed, asked again on its own. @param {Asked} asked */
  const retryWith = (asked) => (/** @type {string} */ agent) => send({ ...asked, agents: [agent] })

  const submit = async () => {
    const message = draft.trim()
    if (!message || sending) return
    setDraft('')
    const image = photo
    setPhoto(null)
    const go = () => send({ message, image, agents: coaches })
    // The first message: the prompt bar glides from the middle to the foot of the page where the
    // browser can (a view transition); elsewhere, or with reduced motion, it moves at once
    if (empty && document.startViewTransition && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
      let answering
      await document.startViewTransition(() => flushSync(() => { answering = go() })).updateCallbackDone
      // The box moved, so it's a new one: it takes the focus back as soon as it's there, not
      // once the answer has come
      const box = /** @type {HTMLElement | null} */ (document.querySelector('textarea[aria-label="Message"]'))
      box?.focus()
      await answering
      return
    }
    await go()
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

  // The prompt bar and what failed: in the middle under the empty chat, then at the foot of the page
  // once there are messages (owner, 25 Nov 2026). One name for both places, so the move can glide
  const composer = (
    <div className="flex flex-col gap-2 [view-transition-name:prompt]">
      {failed && (
        <Alert variant="destructive">
          <CircleAlert />
          <AlertDescription className="flex flex-wrap items-center justify-between gap-2">
            {failed.message}
            {failed.input && (
              <Button type="button" variant="outline" size="sm" disabled={sending}
                      onClick={() => failed.input && send(failed.input, failed.again)}>
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
  )

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-(--z-header) border-b bg-card/90 backdrop-blur supports-backdrop-filter:bg-card/75">
        <div className="mx-auto flex h-(--header-height) max-w-chat items-center justify-between px-4">
          <Link href="/dashboard" className="font-heading text-xl font-bold tracking-tight text-foreground no-underline">Holos</Link>
          <nav className="flex items-center gap-1" aria-label="Main">
            {/* A guest has it too: their drawer says the logs come with signing in (owner, 24 Nov 2026) */}
            <LogsPanel guest={guest}>
              <Button type="button" variant="ghost"><List /> Logs</Button>
            </LogsPanel>
            <HeaderMenu guest={guest} />
          </nav>
        </div>
      </header>

      <main ref={thread} className="mx-auto flex w-full max-w-chat flex-1 flex-col gap-6 px-4 pt-6 pb-4" aria-live="polite">
        {before && (
          <Button type="button" variant="ghost" className="self-center" onClick={older}>
            Show earlier messages
          </Button>
        )}
        {empty && (
          <div className="my-auto flex flex-col gap-6">
            <Empty className="p-0">
              <EmptyHeader>
                <EmptyMedia variant="icon"><MessageCircle /></EmptyMedia>
                <EmptyTitle>Ask about a workout, a meal or how you feel</EmptyTitle>
                <EmptyDescription>
                  Holos checks every answer against your health profile.{' '}
                  {guest && <Link href="/profile" className="text-primary underline underline-offset-2">Add your health profile</Link>}
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
            {/* -mx-1: as wide as at the foot of the page, whose gutter is px-3 to this one's px-4 */}
            <div className="-mx-1">{composer}</div>
          </div>
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
          <AnswerEntry key={e.key} entry={e} guest={guest} store={store} status={status} onSettled={settle}
                       onRetry={e.saved || e.live || !e.asked ? null : retryWith(e.asked)} />
        )))}
      </main>

      {!empty && loaded && (
        <div className="sticky bottom-0 bg-linear-to-t from-background from-70% to-transparent pt-4">
          <div className="mx-auto max-w-chat px-3 pb-3">{composer}</div>
        </div>
      )}
      {/* Under the prompt bar, not the messages: scrolled to, it leaves the newest in view above the bar */}
      <div ref={bottom} />
      {/* A guest's data left in this browser, offered to the account that signed in (C.18) */}
      {!guest && <ImportGuest onImported={() => setReads((prev) => prev + 1)} />}

    </div>
  )
}

/**
 * A guest's history, kept in this browser (P5.2).
 * @param {ReturnType<typeof guestStore>} store
 * @returns {Entry[]}
 */
function guestEntries(store) {
  return store.data().turns.map((t, i) => (t.role === 'user'
    ? { key: `g${i}`, role: 'user', text: t.content }
    : { key: `g${i}`, role: 'assistant', text: t.content, events: t.display,
        traceId: t.trace_id, saved: true }))
}

/**
 * A message from the account's history (C.21): never retried from here.
 * @param {import('@/types/contracts').HistoryPage['messages'][number]} m
 * @returns {Entry}
 */
function fromHistory(m) {
  return m.role === 'user'
    ? { key: `h${m.id}`, role: 'user', text: m.text, photo: m.photo }
    : { key: `h${m.id}`, role: 'assistant', text: m.text, events: m.display, saved: true }
}
