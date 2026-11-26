'use client'

import { useEffect } from 'react'
import { TriangleAlert } from 'lucide-react'
import { toast } from 'sonner'

// Owner, 27 Nov 2026: says the suggestions are AI-generated and not medical advice, without asking
// people to keep their own details out; they test it best on their own (was "Demo. Not medical
// advice. Don't enter real health information.", Part E #78)
export const DEMO_TEXT = "Holos's suggestions are AI-generated. They're checked against your health profile, but they "
  + "aren't medical advice: check with a doctor before acting on anything about your health."
const SEEN = 'holos.demo-notice'

/**
 * The AI notice (P5.4): a toast that stays until closed, once per browser session, on the
 * chat and the pages where health details are entered (onboarding, profile). It draws attention
 * once without staying on screen (owner, 26 Nov 2026, Part E #78). Storage that can't be read
 * shows it again; that is all it costs.
 */
export default function DemoNotice() {
  useEffect(() => {
    if (seen()) return
    // In the theme's caution amber, as a safety caution is elsewhere, so it is seen (owner, 27 Nov 2026)
    toast(DEMO_TEXT, {
      id: 'demo', duration: Infinity, closeButton: true,
      icon: <TriangleAlert className="size-4 text-caution" />,
      className: 'border-caution! border-l-4! font-medium',
    })
    try {
      sessionStorage.setItem(SEEN, '1')
    } catch {
      // private mode or blocked storage: it shows again next page
    }
  }, [])
  return null
}

function seen() {
  try {
    return sessionStorage.getItem(SEEN) === '1'
  } catch {
    return false
  }
}
