'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { api, setToken } from '@/lib/api'
import { useRedirectIfAuthenticated } from '@/hooks/useAuth'
import Silk from '@/components/Silk'

export default function LoginPage() {
  const router = useRouter()
  const { mounted } = useRedirectIfAuthenticated()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [validationErrors, setValidationErrors] = useState({})

  // Don't render until mounted (redirect will happen if authenticated)
  if (!mounted) {
    return null
  }

  // Validation functions
  const validateEmail = (email) => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    return emailRegex.test(email)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setValidationErrors({})

    // Validate fields
    const errors = {}
    if (!email.trim()) {
      errors.email = 'Email is required'
    } else if (!validateEmail(email)) {
      errors.email = 'Please enter a valid email address'
    }
    if (!password.trim()) {
      errors.password = 'Password is required'
    }

    if (Object.keys(errors).length > 0) {
      setValidationErrors(errors)
      return
    }

    setLoading(true)

    try {
      const response = await api.login(email, password)
      setToken(response.access_token)
      router.push('/dashboard')
    } catch (err) {
      setError(err.message || 'Login failed. Please check your credentials.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ 
      minHeight: '100vh', 
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'center', 
      padding: '2rem',
      position: 'relative',
      overflow: 'hidden'
    }}>
      {/* Holos Logo */}
      <div style={{
        position: 'absolute',
        top: '2rem',
        left: '2rem',
        zIndex: 10
      }}>
        <h1 style={{ 
          color: 'white',
          fontSize: '2rem',
          fontWeight: '700',
          textShadow: '0 2px 4px rgba(0, 0, 0, 0.3)',
          margin: 0
        }}>
          Holos
        </h1>
      </div>
      <Silk
        speed={5}
        scale={1}
        color="#295eff"
        noiseIntensity={1.5}
        rotation={0}
      />
      <div className="card container-sm glassmorphism" style={{ 
        maxWidth: '400px', 
        width: '100%'
      }}>
        <h1 style={{ textAlign: 'center', marginBottom: '2rem', color: 'var(--text-light)', textShadow: '0 2px 4px rgba(0, 0, 0, 0.3)' }}>Login</h1>
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-md)' }}>
          <div className="form-group">
            <label htmlFor="email" className="form-label">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value)
                if (validationErrors.email) {
                  setValidationErrors({ ...validationErrors, email: '' })
                }
              }}
              required
              className={`form-input ${validationErrors.email ? 'form-input-error' : ''}`}
            />
            {validationErrors.email && (
              <div className="text-error" style={{ fontSize: '0.875rem', marginTop: '0.0625rem', color: 'var(--danger-color)' }}>
                {validationErrors.email}
              </div>
            )}
          </div>
          <div className="form-group">
            <label htmlFor="password" className="form-label">
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value)
                if (validationErrors.password) {
                  setValidationErrors({ ...validationErrors, password: '' })
                }
              }}
              required
              className={`form-input ${validationErrors.password ? 'form-input-error' : ''}`}
            />
            {validationErrors.password && (
              <div className="text-error" style={{ fontSize: '0.875rem', marginTop: '0.0625rem', color: 'var(--danger-color)' }}>
                {validationErrors.password}
              </div>
            )}
          </div>
          {error && (
            <div className="alert alert-error">
              {error}
            </div>
          )}
          <button
            type="submit"
            disabled={loading}
            className="btn btn-primary"
            style={{ width: '100%' }}
          >
            {loading ? 'Logging in...' : 'Login'}
          </button>
        </form>
        <p style={{ marginTop: '1.5rem', textAlign: 'center', color: 'rgba(255, 255, 255, 0.9)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
          Don&apos;t have an account? <a href="/register" style={{ color: '#00d4ff', textDecoration: 'none', fontWeight: '600', textShadow: '0 0 8px rgba(0, 212, 255, 0.5), 0 1px 2px rgba(0, 0, 0, 0.3)' }}>Register here</a>
        </p>
      </div>
    </div>
  )
}

