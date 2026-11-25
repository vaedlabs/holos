'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { CircleAlert } from 'lucide-react'

import AuthShell from '@/components/AuthShell'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { useRedirectIfAuthenticated } from '@/hooks/useAuth'
import { formErrors, signIn } from '@/lib/api'

const looksLikeEmail = (email) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)

export default function LoginPage() {
  const router = useRouter()
  const { mounted } = useRedirectIfAuthenticated()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [invalid, setInvalid] = useState({}) // {email, password}: what to fix before sending

  // Someone already signed in is sent on to the chat
  if (!mounted) return null

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    const errors = {}
    if (!email.trim()) errors.email = 'Email is required'
    else if (!looksLikeEmail(email)) errors.email = 'Please enter a valid email address'
    if (!password.trim()) errors.password = 'Password is required'
    setInvalid(errors)
    if (Object.keys(errors).length > 0) return

    setLoading(true)
    try {
      await signIn(email, password)
      router.push('/dashboard')
    } catch (err) {
      const { fields, message } = formErrors(err, ['email', 'password'])
      setInvalid(fields)
      if (message || !Object.keys(fields).length) {
        setError(message || "Couldn't sign in. Please check your email and password.")
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    // "Sign in", as the landing page and the menu's Sign out say; the silk, as on the invite page
    // (owner, 25 Nov 2026)
    <AuthShell
      title="Sign in"
      silk
      footer={(
        <>
          Accounts are invite-only: open the link you were sent. Or{' '}
          <Link href="/" className="font-medium text-primary underline underline-offset-2">try Holos as a guest</Link>.
        </>
      )}>
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <Field data-invalid={invalid.email ? true : undefined}>
          <FieldLabel htmlFor="email">Email</FieldLabel>
          <Input id="email" type="email" autoComplete="email" value={email} aria-invalid={invalid.email ? true : undefined}
                 onChange={(e) => {
                   setEmail(e.target.value)
                   setInvalid((prev) => ({ ...prev, email: '' }))
                 }} />
          {invalid.email && <FieldError>{invalid.email}</FieldError>}
        </Field>
        <Field data-invalid={invalid.password ? true : undefined}>
          <FieldLabel htmlFor="password">Password</FieldLabel>
          <Input id="password" type="password" autoComplete="current-password" value={password}
                 aria-invalid={invalid.password ? true : undefined}
                 onChange={(e) => {
                   setPassword(e.target.value)
                   setInvalid((prev) => ({ ...prev, password: '' }))
                 }} />
          {invalid.password && <FieldError>{invalid.password}</FieldError>}
        </Field>
        {error && (
          <Alert variant="destructive">
            <CircleAlert />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <Button type="submit" size="lg" disabled={loading} className="w-full">
          {loading ? <><Spinner /> Signing in…</> : 'Sign in'}
        </Button>
      </form>
    </AuthShell>
  )
}
