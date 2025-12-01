'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { api, getToken, removeToken } from '@/lib/api'
import MedicalHistoryForm from '@/components/MedicalHistoryForm'

export default function MedicalHistoryPage() {
  const router = useRouter()
  const [medicalHistory, setMedicalHistory] = useState(null)
  const [isEditing, setIsEditing] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [mounted, setMounted] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    if (!mounted) return
    
    // Check authentication
    const token = getToken()
    if (!token) {
      router.push('/login')
      return
    }

    // Load medical history
    loadMedicalHistory()
  }, [mounted, router])

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

  if (!mounted) {
    return null
  }

  if (loading) {
    return (
      <div style={{ maxWidth: '800px', margin: '2rem auto', padding: '2rem' }}>
        <div style={{ textAlign: 'center' }}>Loading...</div>
      </div>
    )
  }

  return (
    <div style={{ minHeight: '100vh', background: '#f5f5f5' }}>
      {/* Header */}
      <header className="header">
        <div className="header-content">
          <h1 style={{ margin: 0, fontSize: '1.25rem' }}>Medical History</h1>
          <div style={{ position: 'relative' }}>
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            style={{
              padding: '0.5rem',
              background: 'rgba(255,255,255,0.2)',
              color: 'white',
              border: '1px solid white',
              borderRadius: '4px',
              cursor: 'pointer',
              display: 'flex',
              flexDirection: 'column',
              gap: '4px',
              width: '32px',
              height: '32px',
              justifyContent: 'center',
              alignItems: 'center'
            }}
            aria-label="Menu"
          >
            <span style={{ width: '20px', height: '2px', background: 'white', display: 'block' }}></span>
            <span style={{ width: '20px', height: '2px', background: 'white', display: 'block' }}></span>
            <span style={{ width: '20px', height: '2px', background: 'white', display: 'block' }}></span>
          </button>
          
          {menuOpen && (
            <div style={{
              position: 'absolute',
              top: '100%',
              right: 0,
              marginTop: '0.5rem',
              background: 'white',
              borderRadius: '4px',
              boxShadow: '0 4px 6px rgba(0,0,0,0.1)',
              minWidth: '180px',
              zIndex: 1000,
              overflow: 'hidden'
            }}>
              <button
                onClick={() => {
                  router.push('/dashboard')
                  setMenuOpen(false)
                }}
                style={{
                  width: '100%',
                  padding: '0.75rem 1rem',
                  background: 'white',
                  color: '#333',
                  border: 'none',
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontSize: '0.95rem'
                }}
                onMouseEnter={(e) => e.target.style.background = '#f5f5f5'}
                onMouseLeave={(e) => e.target.style.background = 'white'}
              >
                Dashboard
              </button>
              <button
                onClick={() => {
                  router.push('/medical')
                  setMenuOpen(false)
                }}
                style={{
                  width: '100%',
                  padding: '0.75rem 1rem',
                  background: 'white',
                  color: '#333',
                  border: 'none',
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontSize: '0.95rem',
                  borderTop: '1px solid #e0e0e0'
                }}
                onMouseEnter={(e) => e.target.style.background = '#f5f5f5'}
                onMouseLeave={(e) => e.target.style.background = 'white'}
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
                  background: 'white',
                  color: '#333',
                  border: 'none',
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontSize: '0.95rem',
                  borderTop: '1px solid #e0e0e0'
                }}
                onMouseEnter={(e) => e.target.style.background = '#f5f5f5'}
                onMouseLeave={(e) => e.target.style.background = 'white'}
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
                  background: 'white',
                  color: '#d32f2f',
                  border: 'none',
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontSize: '0.95rem',
                  borderTop: '1px solid #e0e0e0'
                }}
                onMouseEnter={(e) => e.target.style.background = '#f5f5f5'}
                onMouseLeave={(e) => e.target.style.background = 'white'}
              >
                Logout
              </button>
            </div>
          )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div style={{ minHeight: 'calc(100vh - 80px)', background: 'var(--bg-secondary)', padding: 'var(--spacing-xl) 0' }}>
        <div className="container">
          <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--spacing-xl)' }}>
            <h2 style={{ margin: 0, fontSize: '1.75rem', fontWeight: '600' }}>Your Medical History</h2>
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
                      <h3 style={{ marginBottom: 'var(--spacing-sm)', color: 'var(--text-secondary)', fontSize: '0.875rem', textTransform: 'uppercase', fontWeight: '600', letterSpacing: '0.5px' }}>
                        Medical Conditions
                      </h3>
                      <p style={{ margin: 0, padding: 'var(--spacing-md)', background: 'var(--bg-secondary)', borderRadius: 'var(--border-radius)', border: '1px solid var(--border-color)' }}>
                        {medicalHistory.conditions}
                      </p>
                    </div>
                  )}

                  {medicalHistory.limitations && (
                    <div>
                      <h3 style={{ marginBottom: 'var(--spacing-sm)', color: 'var(--text-secondary)', fontSize: '0.875rem', textTransform: 'uppercase', fontWeight: '600', letterSpacing: '0.5px' }}>
                        Physical Limitations
                      </h3>
                      <p style={{ margin: 0, padding: 'var(--spacing-md)', background: 'var(--bg-secondary)', borderRadius: 'var(--border-radius)', whiteSpace: 'pre-wrap', border: '1px solid var(--border-color)' }}>
                        {medicalHistory.limitations}
                      </p>
                    </div>
                  )}

                  {medicalHistory.medications && (
                    <div>
                      <h3 style={{ marginBottom: 'var(--spacing-sm)', color: 'var(--text-secondary)', fontSize: '0.875rem', textTransform: 'uppercase', fontWeight: '600', letterSpacing: '0.5px' }}>
                        Current Medications
                      </h3>
                      <p style={{ margin: 0, padding: 'var(--spacing-md)', background: 'var(--bg-secondary)', borderRadius: 'var(--border-radius)', border: '1px solid var(--border-color)' }}>
                        {medicalHistory.medications}
                      </p>
                    </div>
                  )}

                  {medicalHistory.notes && (
                    <div>
                      <h3 style={{ marginBottom: 'var(--spacing-sm)', color: 'var(--text-secondary)', fontSize: '0.875rem', textTransform: 'uppercase', fontWeight: '600', letterSpacing: '0.5px' }}>
                        Additional Notes
                      </h3>
                      <p style={{ margin: 0, padding: 'var(--spacing-md)', background: 'var(--bg-secondary)', borderRadius: 'var(--border-radius)', whiteSpace: 'pre-wrap', border: '1px solid var(--border-color)' }}>
                        {medicalHistory.notes}
                      </p>
                    </div>
                  )}

                  {!medicalHistory.conditions && !medicalHistory.limitations && !medicalHistory.medications && !medicalHistory.notes && (
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

