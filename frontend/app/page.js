'use client'

import { useCallback, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import Silk from '@/components/Silk'
import Turnstile from '@/components/Turnstile'
import { startGuest } from '@/lib/api'

// The managed widget first; the interactive one when the server asks for it (C.12)
const SITE_KEYS = {
  managed: process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY,
  interactive: process.env.NEXT_PUBLIC_TURNSTILE_INTERACTIVE_SITE_KEY,
}

export default function Home() {
  const router = useRouter()
  const [checking, setChecking] = useState(null) // null, 'managed' or 'interactive'
  const [error, setError] = useState('')
  const reset = useRef(null)

  const onToken = useCallback(async (token) => {
    setError('')
    try {
      await startGuest(token)
      router.push('/dashboard')
    } catch (err) {
      if (err.code === 'turnstile_interactive') {
        setChecking('interactive')
      } else {
        reset.current?.() // a token is used once: a new check for the next try
      }
      setError(err.message)
    }
  }, [router])

  return (
    <div style={{ 
      minHeight: '100vh', 
      display: 'flex', 
      flexDirection: 'column', 
      alignItems: 'center', 
      justifyContent: 'center', 
      padding: '2rem',
      position: 'relative',
      overflow: 'hidden'
    }}>
      <Silk
        speed={5}
        scale={1}
        color="#295eff"
        noiseIntensity={1.5}
        rotation={0}
      />
      <div className="card glassmorphism" style={{ 
        maxWidth: '600px', 
        width: '100%', 
        textAlign: 'center',
        animation: 'fadeIn 0.5s ease-in'
      }}>
        <h1 style={{ 
          marginBottom: 'var(--spacing-md)', 
          color: 'white',
          fontSize: '8rem',
          fontWeight: '700',
          textShadow: '0 2px 4px rgba(0, 0, 0, 0.3)'
        }}>
          Holos
        </h1>
        <p style={{ 
          fontSize: '1.125rem', 
          color: 'rgba(255, 255, 255, 0.9)', 
          marginBottom: 'var(--spacing-2xl)',
          lineHeight: '1.6',
          textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)'
        }}>
          AI-powered fitness application with specialized agents for physical fitness, nutrition, and mental wellness.
        </p>
        <div style={{ 
          display: 'flex', 
          gap: 'var(--spacing-md)', 
          justifyContent: 'center', 
          flexWrap: 'wrap' 
        }}>
          <button type="button" className="btn btn-primary" style={{ minWidth: '120px' }}
                  onClick={() => setChecking((now) => now || 'managed')}>
            Try Holos as a guest
          </button>
          <a href="/login" className="btn btn-outline" style={{ textDecoration: 'none', minWidth: '120px' }}>
            Sign in
          </a>
        </div>
        {checking && (
          <div style={{ marginTop: 'var(--spacing-lg)', display: 'flex', justifyContent: 'center' }}>
            <Turnstile key={checking} siteKey={SITE_KEYS[checking]} onToken={onToken}
                       onError={setError} resetRef={reset} />
          </div>
        )}
        {error && (
          <div className="alert alert-error" style={{ marginTop: 'var(--spacing-md)' }}>{error}</div>
        )}
      </div>
    </div>
  )
}

