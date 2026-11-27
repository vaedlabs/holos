import './globals.css'

import { connection } from 'next/server'

import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'

import { fontVariables } from './fonts'

export const metadata = {
  title: 'Holos - AI Fitness Application',
  description: 'AI-powered fitness application with specialized agents',
  icons: {
    icon: 'data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>💪</text></svg>',
  },
}

// Every page is rendered when it's asked for, so each gets the nonce proxy.js made for it: a page
// built ahead of time has no request to take one from (Next's CSP guide; P5.5)
export default async function RootLayout({ children }) {
  await connection()
  return (
    <html lang="en" className={fontVariables} suppressHydrationWarning>
      <body suppressHydrationWarning>
        <TooltipProvider>{children}</TooltipProvider>
        <Toaster />
      </body>
    </html>
  )
}
