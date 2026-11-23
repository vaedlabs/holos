// The app's three typefaces, self-hosted by next/font at build time so the CSP needs no font host.
// To change a typeface, change its import here; theme.css names the roles, so no component changes (E072).
import { IBM_Plex_Mono, Inter, Manrope } from 'next/font/google'

// Body text, labels, controls
const body = Inter({ subsets: ['latin'], variable: '--font-body-face', display: 'swap' })

// Headings and the wordmark
const heading = Manrope({ subsets: ['latin'], variable: '--font-heading-face', display: 'swap' })

// Numbers and data: calories, durations, times
const mono = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
  variable: '--font-mono-face',
  display: 'swap',
})

export const fontVariables = [body, heading, mono].map((face) => face.variable).join(' ')
