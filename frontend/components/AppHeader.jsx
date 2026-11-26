// @ts-check
import Link from 'next/link'

import { cn } from '@/lib/utils'

/**
 * The header bar of the chat and the settings pages: the wordmark (to the chat), then with
 * `section` "/ Health profile" as the page's name; at the end, the page's buttons (`children`).
 * The buttons sit close together, each with a little less padding than a button elsewhere, and
 * on a phone a page's name stands alone, so it fits (owner, 27 Nov 2026).
 */
/** @param {{ section?: string, children?: import('react').ReactNode }} props */
export default function AppHeader({ section, children }) {
  return (
    <header className="sticky top-0 z-(--z-header) border-b bg-card/90 backdrop-blur supports-backdrop-filter:bg-card/75">
      <div className="mx-auto flex h-(--header-height) max-w-chat items-center justify-between gap-2 px-4">
        <div className="flex min-w-0 items-center gap-2">
          {/* With a page name, a phone shows the name alone: the Chat button is the way back */}
          <Link href="/dashboard"
                className={cn('font-heading text-xl font-bold tracking-tight text-foreground no-underline',
                              section && 'hidden sm:inline')}>Holos</Link>
          {section && (
            <>
              <span aria-hidden="true" className="hidden text-muted-foreground sm:inline">/</span>
              <h1 className="m-0 truncate font-heading text-lg font-semibold">{section}</h1>
            </>
          )}
        </div>
        <nav className="flex shrink-0 items-center *:data-[size=default]:px-2.5" aria-label="Main">
          {children}
        </nav>
      </div>
    </header>
  )
}
