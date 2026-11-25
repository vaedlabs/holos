'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { LogOut, Menu } from 'lucide-react'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { signOut } from '@/lib/api'
import { guestStore } from '@/lib/guestStore'

/**
 * The header's menu, the same on the chat, the health profile and the preferences (owner, 25 Nov
 * 2026): Health profile, then for an account Preferences and Sign out (the one item with an
 * icon: it leaves, the others go to a page); for a guest, Clear my data, asked first.
 */
export default function HeaderMenu({ guest }) {
  const router = useRouter()
  const [confirmClear, setConfirmClear] = useState(false)

  const leave = async () => {
    if (guest) await guestStore().clearMyData()
    else await signOut()
    router.push('/')
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button type="button" variant="ghost" size="icon" aria-label="Menu"><Menu /></Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuItem asChild><Link href="/profile">Health profile</Link></DropdownMenuItem>
          {!guest && <DropdownMenuItem asChild><Link href="/preferences">Preferences</Link></DropdownMenuItem>}
          {guest ? (
            <DropdownMenuItem variant="destructive" onSelect={() => setConfirmClear(true)}>
              Clear my data
            </DropdownMenuItem>
          ) : (
            <DropdownMenuItem onSelect={leave}><LogOut /> Sign out</DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      <AlertDialog open={confirmClear} onOpenChange={setConfirmClear}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Clear your data from this browser?</AlertDialogTitle>
            <AlertDialogDescription>
              Your chat, logs and health profile are kept only here. Clearing them can&apos;t be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep them</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={leave}>Clear my data</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
