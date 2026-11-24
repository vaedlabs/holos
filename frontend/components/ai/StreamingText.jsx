'use client'

// Adapted from beautifului.dev "Streaming Text" (MIT, Copyright (c) 2026 Shane Levine; see LICENSE
// here): new words settle up out of a light blur. Holos releases a reply part by part after the
// safety gate, so each part fades in as it arrives; a saved answer shows at once. Its caret, source
// chips, action icons and follow-ups are left out: the loading line already says more is coming,
// model prose is never a link (E058, E059), and a crisis reply never uses this (P5.4).

/** One part of a reply: fades in when it arrives during a live answer, plain otherwise. */
export function StreamingBlock({ live, children }) {
  return <div className={live ? 'animate-fade-up' : undefined}>{children}</div>
}
