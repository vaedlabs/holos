// Adapted from beautifului.dev "Tool Chips" (MIT, Copyright (c) 2026 Shane Levine; see LICENSE
// here): a compact pill for something a coach did, like "Logged: Lunch: Dal". The original's
// expanding rows are left out: a caution about an entry is always shown, never folded away.
import { Check } from 'lucide-react'

export default function ToolChip({ icon: Icon = Check, children }) {
  return (
    <span className="inline-flex w-fit max-w-full animate-pop-in items-start gap-1.5 rounded-full bg-primary-tint py-1 pr-3 pl-1.5 text-sm text-primary-tint-foreground">
      <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
        <Icon aria-hidden="true" className="size-3" strokeWidth={3} />
      </span>
      <span className="min-w-0 py-px">{children}</span>
    </span>
  )
}
