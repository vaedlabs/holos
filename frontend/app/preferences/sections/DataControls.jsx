'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
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
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Field, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { api, signOut } from '@/lib/api'

/**
 * Clearing the conversation and deleting the account. Both ask first in a dialog; deleting the
 * account also wants "DELETE" typed, as before, since nothing of it can come back.
 */
export default function DataControls() {
  const router = useRouter()
  const [clearing, setClearing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [typed, setTyped] = useState('')

  const clear = async () => {
    setClearing(true)
    try {
      await api.clearConversationHistory()
      toast.success('Conversation history cleared.')
    } catch (err) {
      toast.error(err.message || 'Failed to clear conversation history')
    } finally {
      setClearing(false)
    }
  }

  const remove = async () => {
    setDeleting(true)
    try {
      await api.deleteAccount()
      await signOut()
      toast.success('Account deleted.')
      router.push('/login')
    } catch (err) {
      toast.error(err.message || 'Failed to delete account')
      setDeleting(false)
    }
  }

  return (
    <section aria-labelledby="your-data" className="flex flex-col gap-4 rounded-xl border p-5">
      <div className="flex flex-col gap-1">
        <h2 id="your-data" className="m-0 font-heading text-lg font-semibold">Your data</h2>
        <p className="m-0 text-sm text-foreground-secondary">Neither of these can be undone.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button type="button" variant="outline" disabled={clearing}>
              {clearing ? 'Clearing…' : 'Clear Conversation History'}
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Clear all conversation history?</AlertDialogTitle>
              <AlertDialogDescription>Every chat goes. Your logs and profile stay. This can&apos;t be undone.</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Keep it</AlertDialogCancel>
              <AlertDialogAction variant="destructive" onClick={clear}>Clear history</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        <AlertDialog onOpenChange={(open) => { if (!open) setTyped('') }}>
          <AlertDialogTrigger asChild>
            <Button type="button" variant="destructive" disabled={deleting}>
              {deleting ? 'Deleting…' : 'Delete Account'}
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete your account?</AlertDialogTitle>
              <AlertDialogDescription>
                This permanently deletes all your data, including conversation history, logs, medical history and
                preferences. It can&apos;t be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <Field>
              <FieldLabel htmlFor="confirm-delete">Type DELETE to confirm</FieldLabel>
              <Input id="confirm-delete" autoComplete="off" value={typed} onChange={(e) => setTyped(e.target.value)} />
            </Field>
            <AlertDialogFooter>
              <AlertDialogCancel>Keep my account</AlertDialogCancel>
              <AlertDialogAction variant="destructive" disabled={typed !== 'DELETE'} onClick={remove}>
                Delete account
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </section>
  )
}
