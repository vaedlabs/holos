'use client'

import Link from 'next/link'

/** The sign-in pages' frame (login, invite): the wordmark, then one card with the form. */
export default function AuthShell({ title, children, footer }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-7 px-4 py-10">
      <Link href="/" className="flex flex-col items-center gap-2 text-foreground no-underline">
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
      {footer && <div className="max-w-sm text-center text-sm text-foreground-secondary">{footer}</div>}
    </div>
  )
}
