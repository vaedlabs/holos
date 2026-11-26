'use client'

import dynamic from 'next/dynamic'
import Link from 'next/link'

import HelpNow from '@/components/HelpNow'
import { cn } from '@/lib/utils'

// Only in the browser, and only loaded where a page asks for it (three.js is large)
const Silk = dynamic(() => import('@/components/Silk'), { ssr: false })

/**
 * The sign-in pages' frame (login, invite): the wordmark, then one card with the form. `silk`
 * puts the landing page's moving silk behind it (both pages: owner, 25 Nov 2026), and gives the
 * footer a card's backing so it reads on the silk.
 */
export default function AuthShell({ title, children, footer, silk = false }) {
  return (
    <div className={cn('flex min-h-dvh flex-col items-center justify-center gap-7 px-4 py-10',
                       silk && 'relative isolate overflow-hidden bg-background')}>
      {silk && <Silk speed={5} scale={1} noiseIntensity={1.5} rotation={0} />}
      <HelpNow floating />
      <Link href="/" className={cn('flex flex-col items-center gap-2 no-underline', silk ? 'text-on-silk' : 'text-foreground')}>
        <span aria-hidden="true" className="flex size-12 items-center justify-center rounded-xl bg-primary-tint text-primary">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <circle cx="12" cy="12" r="8.5" />
            <path d="M12 3.5v17M3.5 12h17" />
          </svg>
        </span>
        <span className="font-heading text-3xl font-bold tracking-tight">Holos</span>
      </Link>
      <main className="flex w-full max-w-sm flex-col gap-5 rounded-xl border bg-card p-6 text-card-foreground shadow-card">
        <h1 className="m-0 font-heading text-xl font-semibold">{title}</h1>
        {children}
      </main>
      {footer && (
        <div className={cn('max-w-sm text-center text-sm text-foreground-secondary',
                           silk && 'rounded-lg bg-card/90 px-3 py-2 backdrop-blur')}>
          {footer}
        </div>
      )}
    </div>
  )
}
