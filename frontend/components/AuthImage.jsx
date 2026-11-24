'use client'
import { useState, useEffect, useRef } from 'react'
import { API_URL } from '@/lib/api'

/**
 * One of the account's photos (Plan C.8): fetched with the session cookie, shown from a
 * blob URL that is revoked when the component unmounts.
 *
 * Props:
 *   imagePath  - the history's `photo` ("/conversation/images/{name}"), or an old
 *                stored path ("images/{name}")
 *   className  - classes for the <img>
 *   alt        - alt text
 */
export default function AuthImage({ imagePath, className, alt = 'Uploaded image' }) {
  const [src, setSrc] = useState(null)
  const blobUrlRef = useRef(null)

  useEffect(() => {
    if (!imagePath) return

    const name = imagePath.split('/').pop()

    let cancelled = false
    fetch(`${API_URL}/conversation/images/${encodeURIComponent(name)}`, {
      credentials: 'include',
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
  // A blob: URL fetched with the session cookie, which next/image can't optimise
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={src} className={className} alt={alt} />
}
