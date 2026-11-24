'use client'

import { useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { CircleAlert } from 'lucide-react'

import AuthShell from '@/components/AuthShell'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Field, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Spinner } from '@/components/ui/spinner'
import { acceptInvite } from '@/lib/api'

// DRAFT: the owner approves the privacy wording in P7.5 (CONSENT_VERSION "2026-10-draft")
const CONSENT = 'I agree that Holos keeps what I enter (my profile, chats and logs) to answer ' +
                'me, and that I can delete all of it at any time.'

/** An invite link (Plan C.18): the person picks their email and password and agrees. */
export default function InvitePage() {
  const router = useRouter()
  const { token } = useParams()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [consent, setConsent] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (!consent) {
      setError('Please agree to the privacy note to continue.')
      return
    }
    setLoading(true)
    try {
      await acceptInvite(token, email.trim(), password, true)
      router.push('/onboarding')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell title="Join Holos">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Field>
          <FieldLabel htmlFor="email">Email</FieldLabel>
          <Input id="email" type="email" autoComplete="email" required value={email}
                 onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field>
          <FieldLabel htmlFor="password">Password</FieldLabel>
          <Input id="password" type="password" autoComplete="new-password" required value={password}
                 onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <div className="flex items-start gap-2.5">
          <Checkbox id="consent" checked={consent} onCheckedChange={(next) => setConsent(next === true)}
                    className="mt-0.5" />
          <Label htmlFor="consent" className="leading-snug font-normal text-foreground-secondary">{CONSENT}</Label>
        </div>
        {error && (
          <Alert variant="destructive">
            <CircleAlert />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <Button type="submit" size="lg" disabled={loading} className="w-full">
          {loading ? <><Spinner /> Creating your account…</> : 'Create account'}
        </Button>
      </form>
    </AuthShell>
  )
}
