'use client'

import { useEffect } from 'react'
import { toast } from 'sonner'

export const DEMO_TEXT = "Demo. Not medical advice. Don't enter real health information."
const SEEN = 'holos.demo-notice'

/**
 * The demo notice (P5.4): a toast that stays until closed, once per browser session, on the
 * chat and the pages where health details are entered (onboarding, profile). It draws attention
 * once without staying on screen (owner, 26 Nov 2026, Part E #78). Storage that can't be read
 * shows it again; that is all it costs.
 */
export default function DemoNotice() {
  useEffect(() => {
    if (seen()) return
    toast(DEMO_TEXT, { id: 'demo', duration: Infinity, closeButton: true })
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
