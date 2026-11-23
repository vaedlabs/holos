import { notFound } from 'next/navigation'

import Styleguide from '@/components/styleguide/Styleguide'

export const metadata = { title: 'Styleguide · Holos', robots: { index: false } }

// A tool for checking theme edits, not part of the product: absent from production builds (R7)
export default function StyleguidePage() {
  if (process.env.NODE_ENV === 'production') notFound()
  return <Styleguide />
}
