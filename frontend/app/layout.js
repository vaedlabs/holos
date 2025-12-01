import './globals.css'

export const metadata = {
  title: 'Holos - AI Fitness Application',
  description: 'AI-powered fitness application with specialized agents',
}

export default function RootLayout({ children }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  )
}

