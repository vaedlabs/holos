'use client'

import { useCallback, useRef, useState } from 'react'
import dynamic from 'next/dynamic'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { CircleAlert } from 'lucide-react'

import Turnstile from '@/components/Turnstile'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { startGuest } from '@/lib/api'

// The moving silk is for this landing page only (owner, 23 Nov 2026): three.js loads here and
// nowhere else, and only in the browser
const Silk = dynamic(() => import('@/components/Silk'), { ssr: false })

// The managed widget first; the interactive one when the server asks for it (C.12)
const SITE_KEYS = {
  managed: process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY,
  interactive: process.env.NEXT_PUBLIC_TURNSTILE_INTERACTIVE_SITE_KEY,
}

export default function Home() {
  const router = useRouter()
  const [checking, setChecking] = useState(null) // null, 'managed' or 'interactive'
  const [error, setError] = useState('')
  const reset = useRef(null)

  const onToken = useCallback(async (token) => {
    setError('')
    try {
      await startGuest(token)
      router.push('/dashboard')
    } catch (err) {
      if (err.code === 'turnstile_interactive') {
        setChecking('interactive')
      } else {
        reset.current?.() // a token is used once: a new check for the next try
      }
      setError(err.message)
    }
  }, [router])

  return (
    <div className="relative isolate flex min-h-dvh flex-col items-center justify-center overflow-hidden bg-background px-4 py-10">
      <Silk speed={5} scale={1} noiseIntensity={1.5} rotation={0} />
      <main className="flex w-full max-w-xl flex-col items-center gap-6 rounded-2xl border bg-card/95 px-6 py-10 text-center text-card-foreground shadow-popover backdrop-blur sm:px-10">
        <h1 className="m-0 font-heading text-6xl font-bold tracking-tight sm:text-7xl">Holos</h1>
        <p className="m-0 max-w-md text-lg text-foreground-secondary">
          AI-powered fitness application with specialized agents for physical fitness, nutrition, and mental wellness.
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <Button type="button" size="lg" onClick={() => setChecking((prev) => prev || 'managed')}>
            Try Holos as a guest
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/login">Sign in</Link>
          </Button>
        </div>
        {checking && (
          <Turnstile key={checking} siteKey={SITE_KEYS[checking]} onToken={onToken}
                     onError={setError} resetRef={reset} />
        )}
        {error && (
          <Alert variant="destructive" className="text-left">
            <CircleAlert />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
      </main>
    </div>
  )
}
