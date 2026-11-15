'use client'

import { useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Silk from '@/components/Silk'
import { acceptInvite } from '@/lib/api'

// DRAFT: the owner approves the privacy wording in P7.5 (CONSENT_VERSION "2026-10-draft")
const CONSENT = 'I agree that Holos keeps what I enter (my profile, chats and logs) to answer ' +
                'me, and that I can delete all of it at any time.'

/** An invite link (Plan C.18): the person picks their email and password and agrees. */
export default function InvitePage() {
  const router = useRouter()
  const { token } = useParams()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [consent, setConsent] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (!consent) {
      setError('Please agree to the privacy note to continue.')
      return
    }
    setLoading(true)
    try {
      await acceptInvite(token, email.trim(), password, true)
      router.push('/onboarding')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center',
                  justifyContent: 'center', padding: '2rem', position: 'relative',
                  overflow: 'hidden' }}>
      <Silk speed={5} scale={1} color="#295eff" noiseIntensity={1.5} rotation={0} />
      <div className="card container-sm glassmorphism" style={{ maxWidth: '420px', width: '100%' }}>
        <h1 style={{ textAlign: 'center', marginBottom: '2rem', color: 'var(--text-light)',
                     textShadow: '0 2px 4px rgba(0, 0, 0, 0.3)' }}>
          Join Holos
        </h1>
        <form onSubmit={handleSubmit}
              style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-md)' }}>
          <div className="form-group">
            <label htmlFor="email" className="form-label">Email</label>
            <input id="email" type="email" autoComplete="email" required className="form-input"
                   value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="form-group">
            <label htmlFor="password" className="form-label">Password</label>
            <input id="password" type="password" autoComplete="new-password" required
                   className="form-input" value={password}
                   onChange={(e) => setPassword(e.target.value)} />
          </div>
          <label style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-start',
                          color: 'rgba(255, 255, 255, 0.9)', fontSize: '0.9rem' }}>
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)}
                   style={{ marginTop: '0.2rem' }} />
            <span>{CONSENT}</span>
          </label>
          {error && <div className="alert alert-error">{error}</div>}
          <button type="submit" disabled={loading} className="btn btn-primary" style={{ width: '100%' }}>
            {loading ? 'Creating your account...' : 'Create account'}
          </button>
        </form>
      </div>
    </div>
  )
}
