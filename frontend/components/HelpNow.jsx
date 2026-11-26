'use client'

import { LifeBuoy } from 'lucide-react'

import CrisisCard from '@/components/CrisisCard'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { CRISIS_TEXT, HELPLINES } from '@/lib/crisis'
import { cn } from '@/lib/utils'

/**
 * "Need help now?" on every page (P5.4): the crisis text and helplines from the bundled
 * contracts/crisis.json, so it opens with the backend down and fetches nothing. In each page's
 * header; `floating` where a page has none (the landing and sign-in pages).
 */
export default function HelpNow({ floating = false }) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        {/* "Help" alone on a phone, where the header has room for little else */}
        <Button type="button" variant="ghost" aria-label="Need help now?"
                className={cn(floating && 'fixed top-3 right-3 z-(--z-header) bg-card/90 backdrop-blur')}>
          <LifeBuoy /> <span className="sm:hidden">Help</span><span className="hidden sm:inline">Need help now?</span>
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Need help now?</DialogTitle>
          <DialogDescription>Someone to talk to, now.</DialogDescription>
        </DialogHeader>
        <CrisisCard text={CRISIS_TEXT} helplines={HELPLINES} role="region" />
      </DialogContent>
    </Dialog>
  )
}
