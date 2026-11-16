'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'

import AuthImage from '@/components/AuthImage'
import LogsPanel from '@/components/LogsPanel'
import Answer from '@/components/chat/Answer'
import { useRequireAuth } from '@/hooks/useAuth'
import { api, signOut } from '@/lib/api'
import { accountCards, guestCards } from '@/lib/cards'
import { guestStore } from '@/lib/guestStore'
import { shrinkPhoto } from '@/lib/image'
import { sendChat } from '@/lib/stream'
import { COACHES, stepStatus, turnView } from '@/lib/turnView'

/**
 * The chat (Plan C.5, P5.3). Guests keep their history in this browser (P5.2); an
 * account's comes from GET /conversation/messages in pages (C.21). Every answer, live
 * or saved, is drawn from its events by `turnView`, so a reload shows what was shown.
 */

const zone = () => Intl.DateTimeFormat().resolvedOptions().timeZone

export default function ChatPage() {
  const router = useRouter()
  const { mounted, isAuthenticated, session } = useRequireAuth({ guest: true })
  const guest = session?.mode === 'guest'
  const store = useMemo(() => (guest ? guestStore() : null), [guest])

  const [entries, setEntries] = useState([]) // {key, role, text, photo, events, traceId, live}
  const [before, setBefore] = useState(null)
  const [draft, setDraft] = useState('')
  const [photo, setPhoto] = useState(null)
  const [coaches, setCoaches] = useState([])
  const [status, setStatus] = useState('')
  const [failed, setFailed] = useState(null) // {message, input, image}: the message stays
  const [sending, setSending] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [logsOpen, setLogsOpen] = useState(false)
  const bottom = useRef(null)

  // The history: the guest's from this browser, an account's newest page
  useEffect(() => {
    if (!mounted || !isAuthenticated) return
    if (guest) {
      setEntries(store.data().turns.map((t, i) => (t.role === 'user'
        ? { key: `g${i}`, role: 'user', text: t.content }
        : { key: `g${i}`, role: 'assistant', text: t.content, events: t.display,
            traceId: t.trace_id, saved: true })))
      return
    }
    api.getConversationHistory().then((page) => {
      setEntries(page.messages.map(fromHistory))
      setBefore(page.before)
    }).catch((err) => setFailed({ message: err.message }))
  }, [mounted, isAuthenticated, guest, store])

  useEffect(() => { bottom.current?.scrollIntoView?.({ block: 'end' }) }, [entries.length])

  const older = useCallback(async () => {
    if (!before) return
    const page = await api.getConversationHistory({ before })
    setEntries((now) => [...page.messages.map(fromHistory), ...now])
    setBefore(page.before)
  }, [before])

  const send = useCallback(async ({ message, image, agents }) => {
    setSending(true)
    setFailed(null)
    const key = `live-${Date.now()}`
    setEntries((now) => [...now,
      { key: `${key}-q`, role: 'user', text: message, preview: image ? URL.createObjectURL(image) : null },
      { key, role: 'assistant', events: [], live: true, asked: { message, image } }])
    const events = []
    const input = { message, timezone: zone(), ...(agents?.length ? { agents } : {}) }
    const result = await sendChat(guest ? store.chatInput(message, input) : input, {
      image,
      onEvent: (event) => {
        events.push(event)
        if (event.name === 'step') setStatus((now) => stepStatus(now, event.data.name))
        setEntries((now) => now.map((e) => (e.key === key
          ? { ...e, events: [...events], traceId: event.data.trace_id ?? e.traceId } : e)))
      },
      onStatus: (s) => setStatus(s === 'reconnecting' ? 'Reconnecting…' : ''),
    })
    setStatus('')
    setSending(false)
    if (result.outcome === 'done') {
      if (guest) store.recordTurn(events)
      setEntries((now) => now.map((e) => (e.key === key ? { ...e, live: false } : e)))
      return
    }
    if (result.outcome === 'refused') { // nothing came: the question goes back in the box
      setEntries((now) => now.filter((e) => !e.key.startsWith(key)))
    }
    setFailed({ message: result.message, input: { message, image, agents } })
  }, [guest, store])

  const submit = async (e) => {
    e.preventDefault()
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

  if (!mounted || !isAuthenticated) return null

  return (
    <div className="chat-page">
      <header className="chat-header">
        <span className="chat-brand">Holos</span>
        <nav className="chat-nav">
          {!guest && (
            <button type="button" className="btn btn-outline" onClick={() => setLogsOpen((o) => !o)}>
              Logs
            </button>
          )}
          <button type="button" className="btn btn-outline" aria-label="Menu" aria-expanded={menuOpen}
                  onClick={() => setMenuOpen((o) => !o)}>☰</button>
          {menuOpen && (
            <div className="chat-menu" role="menu">
              <Link href="/profile" role="menuitem">Health profile</Link>
              {!guest && <Link href="/preferences" role="menuitem">Preferences</Link>}
              <button type="button" role="menuitem" onClick={leave}>
                {guest ? 'Clear my data' : 'Sign out'}
              </button>
            </div>
          )}
        </nav>
      </header>
      <LogsPanel open={logsOpen && !guest} />

      <main className="chat-thread" aria-live="polite">
        {before && <button type="button" className="btn btn-outline chat-older" onClick={older}>
          Show earlier messages</button>}
        {entries.length === 0 && (
          <p className="chat-empty">
            Ask about a workout, a meal or how you feel.{' '}
            {guest && <Link href="/profile">Add your health profile</Link>}
          </p>
        )}
        {entries.map((e) => (e.role === 'user' ? (
          <div key={e.key} className="chat-bubble chat-bubble-user">
            {e.photo && <AuthImage imagePath={e.photo} alt="Your photo" />}
            {e.preview && <img src={e.preview} alt="Your photo" className="chat-photo" />}
            <p>{e.text}</p>
          </div>
        ) : (
          <div key={e.key} className="chat-bubble chat-bubble-holos">
            <AnswerEntry entry={e} guest={guest} store={store}
                         onRetry={e.saved || e.live ? null
                           : (agent) => send({ ...e.asked, agents: [agent] })} />
          </div>
        )))}
        {status && <p className="chat-status" role="status">{status}</p>}
        <div ref={bottom} />
      </main>

      <form className="chat-composer" onSubmit={submit}>
        {failed && (
          <div className="alert alert-error chat-failed">
            {failed.message}
            {failed.input && (
              <button type="button" className="btn btn-outline" disabled={sending}
                      onClick={() => send(failed.input)}>Retry</button>
            )}
          </div>
        )}
        <fieldset className="chat-coaches">
          <legend>Ask</legend>
          {Object.entries(COACHES).map(([agent, name]) => (
            <label key={agent}>
              <input type="checkbox" checked={coaches.includes(agent)}
                     onChange={() => setCoaches((now) => (now.includes(agent)
                       ? now.filter((a) => a !== agent) : [...now, agent]))} />
              {name}
            </label>
          ))}
        </fieldset>
        <div className="chat-input-row">
          <label className="btn btn-outline chat-attach">
            Photo
            <input type="file" accept="image/*" hidden onChange={attach} />
          </label>
          {photo && <span className="chat-attached">Photo ready <button type="button"
            onClick={() => setPhoto(null)} aria-label="Remove photo">×</button></span>}
          <textarea className="form-textarea" rows={2} maxLength={2000} value={draft}
                    placeholder="Ask Holos…" aria-label="Message"
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) submit(e) }} />
          <button type="submit" className="btn btn-primary" disabled={sending || !draft.trim()}>
            Send
          </button>
        </div>
      </form>
    </div>
  )
}

/** One answer: its events through `turnView`, or its text when nothing was kept. */
function AnswerEntry({ entry, guest, store, onRetry }) {
  const view = useMemo(() => (entry.events ? turnView(entry.events) : null), [entry.events])
  const cards = useMemo(() => (guest ? guestCards(store, entry.traceId) : accountCards()),
                        [guest, store, entry.traceId])
  if (!view) return <p className="chat-plain">{entry.text}</p>
  return <Answer view={view} onRetry={onRetry} onConfirm={cards.confirm}
                 onDiscard={cards.discard} />
}

/** A message from the account's history (C.21): never retried from here. */
function fromHistory(m) {
  return m.role === 'user'
    ? { key: `h${m.id}`, role: 'user', text: m.text, photo: m.photo }
    : { key: `h${m.id}`, role: 'assistant', text: m.text, events: m.display, saved: true }
}
