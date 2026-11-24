import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

import { notFound } from 'next/navigation'

import Styleguide from '@/components/styleguide/Styleguide'

export const metadata = { title: 'Styleguide · Holos', robots: { index: false } }

// The contract's sample streams, for the chat preview: the server reads them, since they sit
// outside the app (contracts/streams)
function sampleStreams() {
  const dir = join(process.cwd(), '..', 'contracts', 'streams')
  return Object.fromEntries(readdirSync(dir).filter((f) => f.endsWith('.jsonl')).sort().map((f) => [
    f.replace('.jsonl', ''),
    readFileSync(join(dir, f), 'utf8').split('\n').filter(Boolean).map((line) => {
      const { event, data } = JSON.parse(line)
      return { name: event, data }
    }),
  ]))
}

// A tool for checking theme edits, not part of the product: absent from production builds (R7)
export default function StyleguidePage() {
  if (process.env.NODE_ENV === 'production') notFound()
  return <Styleguide streams={sampleStreams()} />
}
