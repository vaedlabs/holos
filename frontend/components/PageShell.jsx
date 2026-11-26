'use client'

import Link from 'next/link'
import { MessageCircle } from 'lucide-react'

import HelpNow from '@/components/HelpNow'
import { Button } from '@/components/ui/button'

/**
 * A settings page's frame (profile, preferences, onboarding). The header: the wordmark (to the
 * chat), then with `section` "/ Health profile" as the page's name; at the end, on any page with
 * a `section`, Chat, since the wordmark isn't plainly a way back (owner, 25 Nov 2026), then the
 * "Need help now?" on every page (P5.4), then the page's own `end` (the menu; `end={false}` for
 * nothing, as on onboarding). Below it, the page's
 * heading (an h2 under a `section`) and its content in one column.
 */
export default function PageShell({ section, end, title, titleAs, description, children }) {
  const Title = titleAs ?? (section ? 'h2' : 'h1')
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-(--z-header) border-b bg-card/90 backdrop-blur supports-backdrop-filter:bg-card/75">
        <div className="mx-auto flex h-(--header-height) max-w-chat items-center justify-between gap-2 px-4">
          <div className="flex min-w-0 items-center gap-2">
            <Link href="/dashboard" className="font-heading text-xl font-bold tracking-tight text-foreground no-underline">Holos</Link>
            {section && (
              <>
                <span aria-hidden="true" className="text-muted-foreground">/</span>
                <h1 className="m-0 truncate font-heading text-lg font-semibold">{section}</h1>
              </>
            )}
          </div>
          <nav className="flex items-center gap-1" aria-label="Main">
            {/* Where the chat has Logs: an icon and its word, the same style */}
            {section && (
              // On a phone its icon alone, so the page's name fits beside "Help" (owner, 27 Nov 2026)
              <Button asChild variant="ghost">
                <Link href="/dashboard" aria-label="Chat"><MessageCircle /> <span className="hidden sm:inline">Chat</span></Link>
              </Button>
            )}
            <HelpNow />
            {end || null}
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
