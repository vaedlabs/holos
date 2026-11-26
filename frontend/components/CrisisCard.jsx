// @ts-check
import { LifeBuoy } from 'lucide-react'

/**
 * The fixed crisis text and its helplines (C.16), in the fixed `--crisis-*` colours (E072), shown
 * at once, never streamed. Each contact is a link a phone can call, or the site to open.
 */
/** @param {{ text: string, helplines: import('@/lib/crisis').Helpline[], role?: string }} props */
export default function CrisisCard({ text, helplines, role = 'alert' }) {
  return (
    <div role={role} className="flex flex-col gap-3 rounded-xl border border-crisis-border bg-crisis-background p-4 text-crisis-foreground">
      <p className="m-0 flex items-start gap-2 font-medium">
        <LifeBuoy aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
        {text}
      </p>
      <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
        {helplines.map((h) => (
          <li key={h.name}>
            <strong>{h.name}</strong> ({h.region}):{' '}
            <a href={contactHref(h.contact)} className="font-semibold text-inherit underline underline-offset-2"
               {...(/^\+?[\d\s-]+$/.test(h.contact) ? {} : { target: '_blank', rel: 'noopener noreferrer' })}>
              {h.contact}
            </a>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** "988" as tel:988; "findahelpline.com" as its https address. @param {string} contact */
export function contactHref(contact) {
  return /^\+?[\d\s-]+$/.test(contact) ? `tel:${contact.replace(/[\s-]/g, '')}` : `https://${contact}`
}
