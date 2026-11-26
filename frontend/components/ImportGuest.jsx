'use client'

import { useMemo, useState } from 'react'
import { CircleAlert } from 'lucide-react'

import { Caution } from '@/components/chat/Items'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Spinner } from '@/components/ui/spinner'
import { importGuest } from '@/lib/api'
import { guestStore } from '@/lib/guestStore'

/**
 * A guest's data still in this browser, offered to the account that signed in (C.18, P5.4).
 * On a shared browser it may be someone else's, and an import can't be undone, so nothing
 * is saved without a yes: Save or Discard; closing keeps it and asks at the next sign-in
 * (owner, 26 Nov 2026, Part E #78). After a save, what came in, what didn't and why.
 */
export default function ImportGuest({ onImported, store: given = null }) {
  const store = useMemo(() => given ?? guestStore(), [given])
  const [open, setOpen] = useState(() => store.hasData())
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  // One ID for this offer, so a retry after a dropped connection gets the first result
  const importId = useMemo(() => crypto.randomUUID(), [])

  if (!open) return null
  const data = store.data()
  const messages = data.turns.length
  const logs = data.logs.length

  const save = async () => {
    setSaving(true)
    setError('')
    try {
      const done = await importGuest(store.importBody(importId))
      store.forget()
      setResult({ ...done, profile: Boolean(data.profile) })
      onImported?.()
    } catch (err) {
      setError(err.message) // the data stays here: Save again, or Discard
    } finally {
      setSaving(false)
    }
  }

  const discard = () => {
    store.forget()
    setOpen(false)
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !saving && setOpen(next)}>
      {/* The dialog takes the focus, not a button: Enter alone must neither import nor discard */}
      <DialogContent className="sm:max-w-md"
                     onOpenAutoFocus={(e) => { e.preventDefault(); e.currentTarget.focus() }}>
        {result ? <Saved result={result} /> : (
          <DialogHeader>
            <DialogTitle>Save your guest data to this account?</DialogTitle>
            <DialogDescription>
              This browser holds what was done here as a guest: {summary(messages, logs, Boolean(data.profile))}.
              Save it only if it&apos;s yours.
              {logs > 0 && ' Each log entry is checked against this account\'s health profile.'}
            </DialogDescription>
          </DialogHeader>
        )}
        {error && (
          <Alert variant="destructive">
            <CircleAlert />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <DialogFooter>
          {result ? (
            <Button type="button" onClick={() => setOpen(false)}>Done</Button>
          ) : (
            <>
              <Button type="button" variant="outline" disabled={saving} onClick={discard}>Discard guest data</Button>
              <Button type="button" disabled={saving} onClick={save}>
                {saving && <Spinner />} Save to my account
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** "4 messages, 2 log entries and a health profile"; empty when there's nothing. */
function summary(messages, logs, profile) {
  const parts = [messages > 0 && plural(messages, 'message'), logs > 0 && plural(logs, 'log entry', 'log entries'),
                 profile && 'a health profile'].filter(Boolean)
  return parts.length > 1 ? `${parts.slice(0, -1).join(', ')} and ${parts.at(-1)}` : parts[0] ?? ''
}

const sentence = (text) => text.charAt(0).toUpperCase() + text.slice(1)

const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`
const unique = (list) => [...new Set(list)]

/** What the import did: the counts, then each reason once. */
function Saved({ result }) {
  const { imported, skipped, review, history_refused: refused } = result
  return (
    <>
      <DialogHeader>
        <DialogTitle>Saved to your account</DialogTitle>
        <DialogDescription>
          {sentence(summary(imported.history, imported.logs, result.profile) || 'Nothing new')} saved.
        </DialogDescription>
      </DialogHeader>
      {(skipped.length > 0 || refused.length > 0 || review.length > 0) && (
        <div className="flex flex-col gap-3">
          {skipped.length > 0 && (
            <Section title={`${plural(skipped.length, 'log entry', 'log entries')} not saved`}
                     lines={unique(skipped.map((s) => s.reason))} />
          )}
          {refused.length > 0 && (
            <Section title={`${plural(refused.length, 'message')} not saved`}
                     lines={unique(refused.map((r) => r.reason))} />
          )}
          {review.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <p className="m-0 font-medium">
                {plural(review.length, 'entry', 'entries')} saved with a warning for this account&apos;s profile
              </p>
              {unique(review.flatMap((r) => r.warnings)).map((w) => <Caution key={w}>{w}</Caution>)}
            </div>
          )}
        </div>
      )}
    </>
  )
}

function Section({ title, lines }) {
  return (
    <div className="flex flex-col gap-1">
      <p className="m-0 font-medium">{title}</p>
      {lines.map((line) => <p key={line} className="m-0 text-foreground-secondary">{line}</p>)}
    </div>
  )
}
