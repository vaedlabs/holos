'use client'

import { useSyncExternalStore } from 'react'

/** Whether a CSS media query matches now, kept up to date as the window changes. False on the
 * server, where there is no window. */
export function useMediaQuery(query) {
  return useSyncExternalStore(
    (onChange) => {
      const list = window.matchMedia(query)
      list.addEventListener('change', onChange)
      return () => list.removeEventListener('change', onChange)
    },
    () => window.matchMedia(query).matches,
    () => false,
  )
}
