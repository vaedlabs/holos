'use client'

import { useEffect, useRef } from 'react'

/**
 * Cloudflare Turnstile (Plan C.6): the managed widget starts a guest session; the
 * interactive one is for a network the server has asked to check harder (C.12,
 * `turnstile_interactive`). `onToken` gets each token; a token is single-use, so a
 * failed start resets the widget through `resetRef`.
 */

const SCRIPT = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
let loading = null

function loadTurnstile() {
  if (typeof window === 'undefined') return Promise.reject(new Error('no browser'))
  if (window.turnstile) return Promise.resolve(window.turnstile)
  loading ??= new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = SCRIPT
    script.async = true
    script.onload = () => resolve(window.turnstile)
    script.onerror = () => {
      loading = null
      reject(new Error('Turnstile did not load'))
    }
    document.head.appendChild(script)
  })
  return loading
}

export default function Turnstile({ siteKey, onToken, onError, resetRef }) {
  const box = useRef(null)

  useEffect(() => {
    let widget = null
    let live = true
    loadTurnstile()
      .then((turnstile) => {
        if (!live || !box.current) return
        widget = turnstile.render(box.current, {
          sitekey: siteKey,
          callback: (token) => onToken(token),
          'error-callback': () => onError?.("The check couldn't run. Please reload the page."),
        })
        if (resetRef) resetRef.current = () => turnstile.reset(widget)
      })
      .catch(() => onError?.("The check couldn't load. Please check your connection."))
    return () => {
      live = false
      if (widget !== null) window.turnstile?.remove(widget)
    }
  }, [siteKey, onToken, onError, resetRef])

  return <div ref={box} />
}
