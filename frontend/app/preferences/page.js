'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { api, removeToken } from '@/lib/api'
import ButtonSelector from '@/components/ButtonSelector'
import { useRequireAuth } from '@/hooks/useAuth'

export default function PreferencesPage() {
  const router = useRouter()
  const { mounted, isAuthenticated } = useRequireAuth()
  const [preferences, setPreferences] = useState(null)
  const [isEditing, setIsEditing] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)
  const [formData, setFormData] = useState({
    goals: '',
    exercise_types: '',
    activity_level: '',
    location: '',
    dietary_restrictions: '',
  })

  useEffect(() => {
    if (!mounted || !isAuthenticated) return

    // Load preferences
    loadPreferences()
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

  const loadPreferences = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await api.getUserPreferences()
      setPreferences(data)
      setFormData({
        goals: data.goals || '',
        exercise_types: data.exercise_types || '',
        activity_level: data.activity_level || '',
        location: data.location || '',
        dietary_restrictions: data.dietary_restrictions || '',
      })
    } catch (err) {
      if (err.message && err.message.includes('404')) {
        setPreferences(null)
      } else {
        setError(err.message || 'Failed to load preferences')
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
    loadPreferences()
  }

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    
    // Validate preferences
    const validationErrors = {}
    
    // Location validation (if provided, should be reasonable length)
    if (formData.location && formData.location.length > 100) {
      validationErrors.location = 'Location must be less than 100 characters'
    }
    
    // Dietary restrictions validation (if provided, should be reasonable length)
    if (formData.dietary_restrictions && formData.dietary_restrictions.length > 200) {
      validationErrors.dietary_restrictions = 'Dietary restrictions must be less than 200 characters'
    }
    
    if (Object.keys(validationErrors).length > 0) {
      setError(Object.values(validationErrors)[0])
      setSaving(false)
      return
    }
    
    try {
      const updated = await api.updateUserPreferences(formData)
      setPreferences(updated)
      setIsEditing(false)
    } catch (err) {
      setError(err.message || 'Failed to update preferences')
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
        <div style={{ textAlign: 'center' }}>Loading...</div>
      </div>
    )
  }

  return (
    <div style={{ minHeight: '100vh', background: '#f5f5f5' }}>
      {/* Header */}
      <header className="header">
        <div className="header-content">
          <h1 style={{ margin: 0, fontSize: '1.25rem' }}>User Preferences</h1>
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
              <h2 style={{ margin: 0, fontSize: '1.75rem', fontWeight: '600' }}>Your Fitness Preferences</h2>
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
            <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-md)' }}>
              <ButtonSelector
                label="Fitness Goals"
                options={[
                  'Build Muscle',
                  'Lose Weight',
                  'Lose Fat',
                  'Gain Strength',
                  'Improve Flexibility',
                  'Increase Endurance',
                  'Cardiovascular Health',
                  'Athletic Performance',
                  'General Fitness',
                  'Rehabilitation',
                  'Mental Wellness',
                  'Inner Peace'
                ]}
                value={formData.goals}
                onChange={(value) => setFormData({ ...formData, goals: value })}
                placeholder="Type other goals (comma-separated)..."
              />
              
              <ButtonSelector
                label="Preferred Exercise Types"
                options={[
                  'Calisthenics',
                  'Weight Lifting',
                  'Cardio',
                  'High-Intensity Interval Training',
                  'Yoga',
                  'Pilates',
                  'Running',
                  'Cycling',
                  'Swimming',
                  'Powerlifting',
                  'CrossFit',
                  'Boxing',
                  'Martial Arts',
                  'Dancing',
                  'Stretching'
                ]}
                value={formData.exercise_types}
                onChange={(value) => setFormData({ ...formData, exercise_types: value })}
                placeholder="Type other exercise types (comma-separated)..."
              />
              <div className="form-group">
                <label htmlFor="activity_level" className="form-label">
                  Activity Level
                </label>
                <select
                  id="activity_level"
                  name="activity_level"
                  value={formData.activity_level}
                  onChange={handleChange}
                  className="form-select"
                >
                  <option value="">Select activity level</option>
                  <option value="sedentary">Sedentary</option>
                  <option value="light">Light</option>
                  <option value="moderate">Moderate</option>
                  <option value="active">Active</option>
                  <option value="very_active">Very Active</option>
                </select>
              </div>
              <div className="form-group">
                <label htmlFor="location" className="form-label">
                  Location
                </label>
                <input
                  id="location"
                  name="location"
                  type="text"
                  value={formData.location}
                  onChange={handleChange}
                  placeholder="City or location"
                  maxLength={100}
                  className="form-input"
                />
              </div>
              <ButtonSelector
                label="Dietary Restrictions"
                options={[
                  'Vegetarian',
                  'Vegan',
                  'Gluten-Free',
                  'Dairy-Free',
                  'Nut-Free',
                  'Pescatarian',
                  'Keto',
                  'Paleo',
                  'Low-Carb',
                  'Low-Fat',
                  'Halal',
                  'Kosher',
                  'No Red Meat',
                  'No Pork',
                  'Sugar-Free'
                ]}
                value={formData.dietary_restrictions}
                onChange={(value) => setFormData({ ...formData, dietary_restrictions: value })}
                placeholder="Type other dietary restrictions (comma-separated)..."
              />
              <div style={{ display: 'flex', gap: 'var(--spacing-md)', marginTop: 'var(--spacing-lg)' }}>
                <button
                  type="submit"
                  disabled={saving}
                  className="btn btn-primary"
                >
                  {saving ? 'Saving...' : 'Save Changes'}
                </button>
                <button
                  type="button"
                  onClick={handleCancel}
                  disabled={saving}
                  className="btn btn-secondary"
                >
                  Cancel
                </button>
              </div>
            </form>
          ) : (
            <div>
              {preferences ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-md)' }}>
                  {preferences.goals && (
                    <div>
                      <h3 style={{ marginBottom: 'var(--spacing-sm)', color: 'var(--text-secondary)', fontSize: '0.875rem', textTransform: 'uppercase', fontWeight: '600', letterSpacing: '0.5px' }}>
                        Fitness Goals
                      </h3>
                      <p style={{ margin: 0, padding: 'var(--spacing-md)', background: 'var(--bg-secondary)', borderRadius: 'var(--border-radius)', whiteSpace: 'pre-wrap', border: '1px solid var(--border-color)' }}>
                        {preferences.goals}
                      </p>
                    </div>
                  )}

                  {preferences.exercise_types && (
                    <div>
                      <h3 style={{ marginBottom: 'var(--spacing-sm)', color: 'var(--text-secondary)', fontSize: '0.875rem', textTransform: 'uppercase', fontWeight: '600', letterSpacing: '0.5px' }}>
                        Preferred Exercise Types
                      </h3>
                      <p style={{ margin: 0, padding: 'var(--spacing-md)', background: 'var(--bg-secondary)', borderRadius: 'var(--border-radius)', border: '1px solid var(--border-color)' }}>
                        {preferences.exercise_types}
                      </p>
                    </div>
                  )}

                  {preferences.activity_level && (
                    <div>
                      <h3 style={{ marginBottom: 'var(--spacing-sm)', color: 'var(--text-secondary)', fontSize: '0.875rem', textTransform: 'uppercase', fontWeight: '600', letterSpacing: '0.5px' }}>
                        Activity Level
                      </h3>
                      <p style={{ margin: 0, padding: 'var(--spacing-md)', background: 'var(--bg-secondary)', borderRadius: 'var(--border-radius)', border: '1px solid var(--border-color)' }}>
                        {preferences.activity_level}
                      </p>
                    </div>
                  )}

                  {preferences.location && (
                    <div>
                      <h3 style={{ marginBottom: 'var(--spacing-sm)', color: 'var(--text-secondary)', fontSize: '0.875rem', textTransform: 'uppercase', fontWeight: '600', letterSpacing: '0.5px' }}>
                        Location
                      </h3>
                      <p style={{ margin: 0, padding: 'var(--spacing-md)', background: 'var(--bg-secondary)', borderRadius: 'var(--border-radius)', border: '1px solid var(--border-color)' }}>
                        {preferences.location}
                      </p>
                    </div>
                  )}

                  {preferences.dietary_restrictions && (
                    <div>
                      <h3 style={{ marginBottom: 'var(--spacing-sm)', color: 'var(--text-secondary)', fontSize: '0.875rem', textTransform: 'uppercase', fontWeight: '600', letterSpacing: '0.5px' }}>
                        Dietary Restrictions
                      </h3>
                      <p style={{ margin: 0, padding: 'var(--spacing-md)', background: 'var(--bg-secondary)', borderRadius: 'var(--border-radius)', border: '1px solid var(--border-color)' }}>
                        {preferences.dietary_restrictions}
                      </p>
                    </div>
                  )}

                  {!preferences.goals && !preferences.exercise_types && !preferences.activity_level && !preferences.location && !preferences.dietary_restrictions && (
                    <div style={{ textAlign: 'center', padding: 'var(--spacing-2xl)', color: 'var(--text-secondary)' }}>
                      <p style={{ marginBottom: 'var(--spacing-md)' }}>No preferences recorded yet.</p>
                      <button
                        onClick={handleEdit}
                        className="btn btn-primary"
                      >
                        Add Preferences
                      </button>
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ textAlign: 'center', padding: 'var(--spacing-2xl)', color: 'var(--text-secondary)' }}>
                  <p style={{ marginBottom: 'var(--spacing-md)' }}>No preferences recorded yet.</p>
                  <button
                    onClick={handleEdit}
                    className="btn btn-primary"
                  >
                    Add Preferences
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

