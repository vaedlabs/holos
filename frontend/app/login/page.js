'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { api, setToken } from '@/lib/api'
import { useRedirectIfAuthenticated } from '@/hooks/useAuth'

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
      <div className="lava-lamp-bg">
        <div className="lava-blob blob-1"></div>
        <div className="lava-blob blob-2"></div>
        <div className="lava-blob blob-3"></div>
      </div>
      <div className="card container-sm lava-lamp-overlay" style={{ 
        maxWidth: '400px', 
        width: '100%',
        background: 'rgba(255, 255, 255, 0.95)',
        border: '1px solid rgba(255, 255, 255, 0.3)'
      }}>
        <h1 style={{ textAlign: 'center', marginBottom: '2rem', color: 'var(--text-primary)' }}>Login</h1>
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
        <p style={{ marginTop: '1.5rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
          Don&apos;t have an account? <a href="/register" style={{ color: 'var(--primary-color)', textDecoration: 'none', fontWeight: '500' }}>Register here</a>
        </p>
      </div>
    </div>
  )
}

