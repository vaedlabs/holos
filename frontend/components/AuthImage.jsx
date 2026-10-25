'use client'
import { useState, useEffect, useRef } from 'react'
import { getToken, API_URL } from '@/lib/api'

/**
 * Renders an authenticated image from the conversation images endpoint.
 * Uses fetch() with the Bearer token to get the image data, converts it
 * to a blob URL, and renders a standard <img>. The blob URL is revoked
 * when the component unmounts.
 *
 * Props:
 *   imagePath  - relative path stored in DB, e.g. "images/{user_id}_{uuid}.jpg"
 *   style      - optional inline styles forwarded to <img>
 *   alt        - alt text
 */
export default function AuthImage({ imagePath, style, alt = 'Uploaded image' }) {
  const [src, setSrc] = useState(null)
  const blobUrlRef = useRef(null)

  useEffect(() => {
    if (!imagePath) return

    const token = getToken()
    if (!token) return

    // imagePath is like "images/{filename}" — the endpoint expects just the filename
    const filename = imagePath.replace(/^images\//, '')

    let cancelled = false
    fetch(`${API_URL}/conversation/images/${encodeURIComponent(filename)}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => (r.ok ? r.blob() : null))
      .then(blob => {
        if (cancelled || !blob) return
        const url = URL.createObjectURL(blob)
        blobUrlRef.current = url
        setSrc(url)
      })
      .catch(() => {})

    return () => {
      cancelled = true
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current)
        blobUrlRef.current = null
      }
    }
  }, [imagePath])

  if (!src) return null
  return <img src={src} style={style} alt={alt} />
}
