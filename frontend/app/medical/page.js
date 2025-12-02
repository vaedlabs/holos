'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { api, removeToken } from '@/lib/api'
import MedicalHistoryForm from '@/components/MedicalHistoryForm'
import { useRequireAuth } from '@/hooks/useAuth'

export default function MedicalHistoryPage() {
  const router = useRouter()
  const { mounted, isAuthenticated } = useRequireAuth()
  const [medicalHistory, setMedicalHistory] = useState(null)
  const [isEditing, setIsEditing] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    if (!mounted || !isAuthenticated) return

    // Load medical history
    loadMedicalHistory()
  }, [mounted, isAuthenticated])

  useEffect(() => {
    // Close menu when clicking outside
    const handleClickOutside = (event) => {
      if (menuOpen && !event.target.closest('[aria-label="Menu"]') && !event.target.closest('div[style*="position: absolute"]')) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [menuOpen])

  const loadMedicalHistory = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await api.getMedicalHistory()
      setMedicalHistory(data)
    } catch (err) {
      if (err.message && err.message.includes('404')) {
        // No medical history exists yet
        setMedicalHistory(null)
      } else {
        setError(err.message || 'Failed to load medical history')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleEdit = () => {
    setIsEditing(true)
  }

  const handleCancel = () => {
    setIsEditing(false)
    // Reload to reset any changes
    loadMedicalHistory()
  }

  const handleSubmit = async (formData) => {
    setSaving(true)
    setError('')
    try {
      const updated = await api.updateMedicalHistory(formData)
      setMedicalHistory(updated)
      setIsEditing(false)
    } catch (err) {
      setError(err.message || 'Failed to update medical history')
    } finally {
      setSaving(false)
    }
  }

  const handleLogout = () => {
    removeToken()
    router.push('/login')
  }

  if (!mounted || !isAuthenticated) {
    return null
  }

  if (loading) {
    return (
      <div style={{ maxWidth: '800px', margin: '2rem auto', padding: '2rem' }}>
        <div style={{ textAlign: 'center', color: 'rgba(255, 255, 255, 0.9)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>Loading...</div>
      </div>
    )
  }

  return (
    <div style={{ minHeight: '100vh', background: 'linear-gradient(180deg, #0a0e27 0%, #1a1f3a 30%, #1e40af 60%, #0f172a 100%)' }}>
      {/* Header */}
      <header className="header">
        <div className="header-content">
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--spacing-md)' }}>
            {/* Home Button */}
            <button
              onClick={() => router.push('/dashboard')}
              style={{
                padding: '0.75rem',
                background: 'rgba(255,255,255,0.2)',
                color: 'white',
                border: '1px solid rgba(255,255,255,0.4)',
                borderRadius: 'var(--border-radius)',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '44px',
                height: '44px',
                transition: 'all 0.2s ease'
              }}
              aria-label="Home"
              onMouseEnter={(e) => e.target.style.background = 'rgba(255,255,255,0.25)'}
              onMouseLeave={(e) => e.target.style.background = 'rgba(255,255,255,0.2)'}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
                <polyline points="9 22 9 12 15 12 15 22"></polyline>
              </svg>
            </button>
            <h1 style={{ margin: 0, fontSize: '1.25rem', color: 'var(--text-light)' }}>Medical History</h1>
          </div>
          <div style={{ display: 'flex', gap: 'var(--spacing-sm)', alignItems: 'center' }}>
            {/* Burger Menu */}
            <div style={{ position: 'relative' }}>
              <button
                onClick={() => setMenuOpen(!menuOpen)}
                style={{
                  padding: '0.5rem',
                  background: menuOpen ? 'rgba(255,255,255,0.3)' : 'rgba(255,255,255,0.2)',
                  color: 'white',
                  border: '1px solid rgba(255,255,255,0.4)',
                  borderRadius: 'var(--border-radius)',
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '4px',
                  width: '44px',
                  height: '44px',
                  justifyContent: 'center',
                  alignItems: 'center',
                  transition: 'all 0.2s ease'
                }}
                aria-label="Menu"
                onMouseEnter={(e) => {
                  if (!menuOpen) {
                    e.target.style.background = 'rgba(255,255,255,0.25)'
                  }
                }}
                onMouseLeave={(e) => {
                  if (!menuOpen) {
                    e.target.style.background = 'rgba(255,255,255,0.2)'
                  }
                }}
              >
                <span style={{ width: '20px', height: '2px', background: 'white', display: 'block' }}></span>
                <span style={{ width: '20px', height: '2px', background: 'white', display: 'block' }}></span>
                <span style={{ width: '20px', height: '2px', background: 'white', display: 'block' }}></span>
              </button>
            
            {menuOpen && (
              <div className="glassmorphism" style={{
                position: 'absolute',
                top: '100%',
                right: 0,
                marginTop: '0.5rem',
                minWidth: '180px',
                zIndex: 1000,
                overflow: 'hidden',
                backdropFilter: 'blur(50px) saturate(180%)',
                WebkitBackdropFilter: 'blur(50px) saturate(180%)',
                background: 'rgba(15, 23, 42, 0.9)'
              }}>
              <button
                onClick={() => {
                  router.push('/medical')
                  setMenuOpen(false)
                }}
                style={{
                  width: '100%',
                  padding: '0.75rem 1rem',
                  background: 'transparent',
                  color: 'var(--text-light)',
                  border: 'none',
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontSize: '0.95rem',
                  fontWeight: '500',
                  textShadow: '0 1px 3px rgba(0, 0, 0, 0.5)',
                  transition: 'all 0.2s ease'
                }}
                onMouseEnter={(e) => {
                  e.target.style.background = 'rgba(255, 255, 255, 0.12)'
                  e.target.style.backdropFilter = 'blur(10px) saturate(150%)'
                  e.target.style.WebkitBackdropFilter = 'blur(10px) saturate(150%)'
                }}
                onMouseLeave={(e) => {
                  e.target.style.background = 'transparent'
                  e.target.style.backdropFilter = 'none'
                  e.target.style.WebkitBackdropFilter = 'none'
                }}
              >
                Medical History
              </button>
              <button
                onClick={() => {
                  router.push('/preferences')
                  setMenuOpen(false)
                }}
                style={{
                  width: '100%',
                  padding: '0.75rem 1rem',
                  background: 'transparent',
                  color: 'var(--text-light)',
                  border: 'none',
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontSize: '0.95rem',
                  fontWeight: '500',
                  borderTop: '1px solid rgba(82, 82, 82, 0.2)',
                  textShadow: '0 1px 3px rgba(0, 0, 0, 0.5)',
                  transition: 'all 0.2s ease'
                }}
                onMouseEnter={(e) => {
                  e.target.style.background = 'rgba(255, 255, 255, 0.12)'
                  e.target.style.backdropFilter = 'blur(10px) saturate(150%)'
                  e.target.style.WebkitBackdropFilter = 'blur(10px) saturate(150%)'
                }}
                onMouseLeave={(e) => {
                  e.target.style.background = 'transparent'
                  e.target.style.backdropFilter = 'none'
                  e.target.style.WebkitBackdropFilter = 'none'
                }}
              >
                User Preferences
              </button>
              <button
                onClick={() => {
                  handleLogout()
                  setMenuOpen(false)
                }}
                style={{
                  width: '100%',
                  padding: '0.75rem 1rem',
                  background: 'transparent',
                  color: '#ff4444',
                  border: 'none',
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontSize: '0.95rem',
                  fontWeight: '500',
                  borderTop: '1px solid rgba(82, 82, 82, 0.2)',
                  textShadow: '0 1px 3px rgba(0, 0, 0, 0.5)',
                  transition: 'all 0.2s ease'
                }}
                onMouseEnter={(e) => {
                  e.target.style.background = 'rgba(255, 68, 68, 0.15)'
                  e.target.style.backdropFilter = 'blur(10px) saturate(150%)'
                  e.target.style.WebkitBackdropFilter = 'blur(10px) saturate(150%)'
                }}
                onMouseLeave={(e) => {
                  e.target.style.background = 'transparent'
                  e.target.style.backdropFilter = 'none'
                  e.target.style.WebkitBackdropFilter = 'none'
                }}
              >
                Logout
              </button>
            </div>
          )}
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div style={{ minHeight: 'calc(100vh - 80px)', background: 'transparent', padding: 'var(--spacing-xl) 0' }}>
        <div className="container">
          <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--spacing-xl)' }}>
            <h2 style={{ margin: 0, fontSize: '1.75rem', fontWeight: '600', color: 'var(--text-light)', textShadow: '0 2px 4px rgba(0, 0, 0, 0.3)' }}>Your Medical History</h2>
            {!isEditing && (
              <button
                onClick={handleEdit}
                className="btn btn-primary"
              >
                Edit
              </button>
            )}
          </div>

          {error && (
            <div className="alert alert-error">
              {error}
            </div>
          )}

          {isEditing ? (
            <div>
              <MedicalHistoryForm
                onSubmit={handleSubmit}
                initialData={medicalHistory || {}}
              />
              <div style={{ display: 'flex', gap: 'var(--spacing-md)', marginTop: 'var(--spacing-lg)' }}>
                <button
                  onClick={handleCancel}
                  disabled={saving}
                  className="btn btn-secondary"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div>
              {medicalHistory ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-md)' }}>
                  {medicalHistory.conditions && (
                    <div>
                      <h3 style={{ marginBottom: 'var(--spacing-sm)', color: 'rgba(255, 255, 255, 0.8)', fontSize: '0.875rem', textTransform: 'uppercase', fontWeight: '600', letterSpacing: '0.5px', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                        Medical Conditions
                      </h3>
                      <p className="glassmorphism" style={{ margin: 0, padding: 'var(--spacing-md)', borderRadius: 'var(--border-radius)', color: 'var(--text-light)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                        {medicalHistory.conditions}
                      </p>
                    </div>
                  )}

                  {medicalHistory.limitations && (
                    <div>
                      <h3 style={{ marginBottom: 'var(--spacing-sm)', color: 'rgba(255, 255, 255, 0.8)', fontSize: '0.875rem', textTransform: 'uppercase', fontWeight: '600', letterSpacing: '0.5px', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                        Physical Limitations
                      </h3>
                      <p className="glassmorphism" style={{ margin: 0, padding: 'var(--spacing-md)', borderRadius: 'var(--border-radius)', whiteSpace: 'pre-wrap', color: 'var(--text-light)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                        {medicalHistory.limitations}
                      </p>
                    </div>
                  )}

                  {medicalHistory.medications && (
                    <div>
                      <h3 style={{ marginBottom: 'var(--spacing-sm)', color: 'rgba(255, 255, 255, 0.8)', fontSize: '0.875rem', textTransform: 'uppercase', fontWeight: '600', letterSpacing: '0.5px', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                        Current Medications
                      </h3>
                      <p className="glassmorphism" style={{ margin: 0, padding: 'var(--spacing-md)', borderRadius: 'var(--border-radius)', color: 'var(--text-light)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                        {medicalHistory.medications}
                      </p>
                    </div>
                  )}

                  {medicalHistory.notes && (
                    <div>
                      <h3 style={{ marginBottom: 'var(--spacing-sm)', color: 'rgba(255, 255, 255, 0.8)', fontSize: '0.875rem', textTransform: 'uppercase', fontWeight: '600', letterSpacing: '0.5px', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                        Additional Notes
                      </h3>
                      <p className="glassmorphism" style={{ margin: 0, padding: 'var(--spacing-md)', borderRadius: 'var(--border-radius)', whiteSpace: 'pre-wrap', color: 'var(--text-light)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                        {medicalHistory.notes}
                      </p>
                    </div>
                  )}

                  {!medicalHistory.conditions && !medicalHistory.limitations && !medicalHistory.medications && !medicalHistory.notes && (
                    <div style={{ textAlign: 'center', padding: 'var(--spacing-2xl)', color: 'rgba(255, 255, 255, 0.9)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                      <p style={{ marginBottom: 'var(--spacing-md)' }}>No medical history recorded yet.</p>
                      <button
                        onClick={handleEdit}
                        className="btn btn-primary"
                      >
                        Add Medical History
                      </button>
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ textAlign: 'center', padding: 'var(--spacing-2xl)', color: 'var(--text-secondary)' }}>
                  <p style={{ marginBottom: 'var(--spacing-md)' }}>No medical history recorded yet.</p>
                  <button
                    onClick={handleEdit}
                    className="btn btn-primary"
                  >
                    Add Medical History
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      </div>
    </div>
  )
}

