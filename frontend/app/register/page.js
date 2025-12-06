'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { api, setToken } from '@/lib/api'
import { useRedirectIfAuthenticated } from '@/hooks/useAuth'

export default function RegisterPage() {
  const router = useRouter()
  const { mounted } = useRedirectIfAuthenticated()
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
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

  const validatePassword = (password) => {
    const errors = []
    if (password.length < 8) {
      errors.push('Password must be at least 8 characters')
    }
    if (!/[A-Z]/.test(password)) {
      errors.push('Password must contain at least one uppercase letter')
    }
    if (!/[a-z]/.test(password)) {
      errors.push('Password must contain at least one lowercase letter')
    }
    if (!/[0-9]/.test(password)) {
      errors.push('Password must contain at least one number')
    }
    return errors
  }

  const validateUsername = (username) => {
    const errors = []
    if (username.length < 3) {
      errors.push('Username must be at least 3 characters')
    }
    if (username.length > 20) {
      errors.push('Username must be less than 20 characters')
    }
    if (!/^[a-zA-Z0-9_-]+$/.test(username)) {
      errors.push('Username can only contain letters, numbers, underscores, and hyphens')
    }
    return errors
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setValidationErrors({})

    // Validate all fields
    const errors = {}
    
    // Email validation
    if (!email.trim()) {
      errors.email = 'Email is required'
    } else if (!validateEmail(email)) {
      errors.email = 'Please enter a valid email address'
    }

    // Username validation
    const usernameErrors = validateUsername(username)
    if (usernameErrors.length > 0) {
      errors.username = usernameErrors[0]
    }

    // Password validation
    const passwordErrors = validatePassword(password)
    if (passwordErrors.length > 0) {
      errors.password = passwordErrors[0]
    } else if (password !== confirmPassword) {
      errors.confirmPassword = 'Passwords do not match'
    }

    if (Object.keys(errors).length > 0) {
      setValidationErrors(errors)
      return
    }

    setLoading(true)

    try {
      const response = await api.register(email, username, password)
      // After registration, automatically log in
      const loginResponse = await api.login(email, password)
      setToken(loginResponse.access_token)
      router.push('/onboarding')
    } catch (err) {
      // Provide more helpful error messages
      if (err.message.includes('Cannot connect')) {
        setError('Cannot connect to backend server. Please make sure the backend is running at http://localhost:8000')
      } else {
        setError(err.message || 'Registration failed. Please try again.')
      }
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
      <div className="lava-lamp-bg">
        <div className="lava-blob blob-1"></div>
        <div className="lava-blob blob-2"></div>
        <div className="lava-blob blob-3"></div>
      </div>
      <div className="card container-sm glassmorphism" style={{ 
        maxWidth: '500px', 
        width: '100%'
      }}>
        <h1 style={{ textAlign: 'center', marginBottom: '2rem', color: 'var(--text-light)', textShadow: '0 2px 4px rgba(0, 0, 0, 0.3)' }}>Register</h1>
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
            <label htmlFor="username" className="form-label">
              Username
            </label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => {
                setUsername(e.target.value)
                if (validationErrors.username) {
                  setValidationErrors({ ...validationErrors, username: '' })
                }
              }}
              required
              minLength={3}
              maxLength={20}
              className={`form-input ${validationErrors.username ? 'form-input-error' : ''}`}
            />
            {validationErrors.username && (
              <div className="text-error" style={{ fontSize: '0.875rem', marginTop: '0.0625rem', color: 'var(--danger-color)' }}>
                {validationErrors.username}
              </div>
            )}
            <small className="text-muted" style={{ display: 'block', marginTop: '0.0625rem', fontSize: '0.875rem', color: 'rgba(255, 255, 255, 0.7)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
              3-20 characters, letters, numbers, underscores, and hyphens only
            </small>
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
              minLength={8}
              className={`form-input ${validationErrors.password ? 'form-input-error' : ''}`}
            />
            {validationErrors.password && (
              <div className="text-error" style={{ fontSize: '0.875rem', marginTop: '0.0625rem', color: 'var(--danger-color)' }}>
                {validationErrors.password}
              </div>
            )}
            <small className="text-muted" style={{ display: 'block', marginTop: '0.0625rem', fontSize: '0.875rem', color: 'rgba(255, 255, 255, 0.7)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
              At least 8 characters with uppercase, lowercase, and number
            </small>
          </div>
          <div className="form-group">
            <label htmlFor="confirmPassword" className="form-label">
              Confirm Password
            </label>
            <input
              id="confirmPassword"
              type="password"
              value={confirmPassword}
              onChange={(e) => {
                setConfirmPassword(e.target.value)
                if (validationErrors.confirmPassword) {
                  setValidationErrors({ ...validationErrors, confirmPassword: '' })
                }
              }}
              required
              minLength={8}
              className={`form-input ${validationErrors.confirmPassword ? 'form-input-error' : ''}`}
            />
            {validationErrors.confirmPassword && (
              <div className="text-error" style={{ fontSize: '0.875rem', marginTop: '0.0625rem', color: 'var(--danger-color)' }}>
                {validationErrors.confirmPassword}
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
            {loading ? 'Registering...' : 'Register'}
          </button>
        </form>
        <p style={{ marginTop: '1.5rem', textAlign: 'center', color: 'rgba(255, 255, 255, 0.9)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
          Already have an account? <a href="/login" style={{ color: '#00d4ff', textDecoration: 'none', fontWeight: '600', textShadow: '0 0 8px rgba(0, 212, 255, 0.5), 0 1px 2px rgba(0, 0, 0, 0.3)' }}>Login here</a>
        </p>
      </div>
    </div>
  )
}

