'use client'

import Link from 'next/link'

import { Button } from '@/components/ui/button'

/**
 * A settings page's frame (profile, preferences). Each page keeps the header it had: by default
 * the wordmark with Back to chat (the profile), or its own `start` and `end` (the preferences'
 * Home button, title and menu). Below it, the page's heading and its content in one column.
 */
export default function PageShell({ start, end, title, titleAs: Title = 'h1', description, children }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-(--z-header) border-b bg-card/90 backdrop-blur supports-backdrop-filter:bg-card/75">
        <div className="mx-auto flex h-(--header-height) max-w-chat items-center justify-between gap-2 px-4">
          <div className="flex min-w-0 items-center gap-2">
            {start ?? <span className="font-heading text-xl font-bold tracking-tight">Holos</span>}
          </div>
          <nav className="flex items-center gap-1" aria-label="Main">
            {end ?? (
              <Button asChild variant="outline">
                <Link href="/dashboard">Back to chat</Link>
              </Button>
            )}
          </nav>
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-chat flex-col gap-6 px-4 py-8">
        <div className="flex flex-col gap-1.5">
          <Title className="m-0 font-heading text-2xl font-bold tracking-tight">{title}</Title>
          {description && <p className="m-0 text-foreground-secondary">{description}</p>}
        </div>
        {children}
      </main>
    </div>
  )
}
