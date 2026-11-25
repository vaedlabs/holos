'use client'

import { useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { CircleAlert, Info } from 'lucide-react'

import AuthShell from '@/components/AuthShell'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Spinner } from '@/components/ui/spinner'
import { acceptInvite, formErrors } from '@/lib/api'

// DRAFT: the owner approves the privacy wording in P7.5 (CONSENT_VERSION "2026-10-draft"). The
// checkbox says it in short; the full wording opens from the (i) beside it (owner, 25 Nov 2026)
const AGREE = 'Please agree to the terms and conditions to continue.'
const CONSENT = 'Holos stores the information you provide, including your profile, chats, and logs. This information is used to answer your questions. You can delete all your data at any time.'

/** An invite link (Plan C.18): the person picks their email and password and agrees. */
export default function InvitePage() {
  const router = useRouter()
  const { token } = useParams()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [consent, setConsent] = useState(false)
  const [error, setError] = useState('')
  const [invalid, setInvalid] = useState({}) // {email, password}: the server's reason, under the field
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (!consent) {
      setError(AGREE)
      return
    }
    setLoading(true)
    try {
      await acceptInvite(token, email.trim(), password, true)
      router.push('/onboarding')
    } catch (err) {
      const { fields, message } = formErrors(err, ['email', 'password'])
      setInvalid(fields)
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell title="Join Holos" silk>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Field data-invalid={invalid.email ? true : undefined}>
          <FieldLabel htmlFor="email">Email</FieldLabel>
          <Input id="email" type="email" autoComplete="email" required value={email}
                 aria-invalid={invalid.email ? true : undefined}
                 onChange={(e) => {
                   setEmail(e.target.value)
                   setInvalid((prev) => ({ ...prev, email: '' }))
                 }} />
          {invalid.email && <FieldError>{invalid.email}</FieldError>}
        </Field>
        <Field data-invalid={invalid.password ? true : undefined}>
          <FieldLabel htmlFor="password">Password</FieldLabel>
          <Input id="password" type="password" autoComplete="new-password" required value={password}
                 aria-invalid={invalid.password ? true : undefined}
                 onChange={(e) => {
                   setPassword(e.target.value)
                   setInvalid((prev) => ({ ...prev, password: '' }))
                 }} />
          {invalid.password && <FieldError>{invalid.password}</FieldError>}
        </Field>
        <div className="flex items-start gap-2.5">
          {/* Ticked, the "please agree" error has been answered: it goes (D064) */}
          <Checkbox id="consent" checked={consent}
                    onCheckedChange={(next) => {
                      setConsent(next === true)
                      if (next === true) setError((prev) => (prev === AGREE ? '' : prev))
                    }}
                    aria-labelledby="consent-words consent-last" className="mt-0.5" />
          {/* The (i) stays on the last word's line, so on a phone it never sits alone. It's in the
              label, but a button there doesn't tick the box; the box is named by the words only */}
          <Label htmlFor="consent" className="inline text-sm font-normal leading-snug text-foreground-secondary">
            <span id="consent-words">I agree to the Holos terms and</span>{' '}
            <span className="whitespace-nowrap">
              <span id="consent-last">conditions</span>{' '}
              <Popover>
                <PopoverTrigger asChild>
                  <Button type="button" variant="ghost" size="icon-xs" aria-label="Read the terms"
                          className="-my-1 align-middle text-muted-foreground">
                    <Info />
                  </Button>
                </PopoverTrigger>
                <PopoverContent side="top" className="text-sm text-foreground-secondary">
                  <p className="m-0 font-medium text-foreground">Terms and conditions</p>
                  <p className="m-0">{CONSENT}</p>
                </PopoverContent>
              </Popover>
            </span>
          </Label>
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
