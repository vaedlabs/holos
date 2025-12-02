'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { api, removeToken } from '@/lib/api'
import ButtonSelector from '@/components/ButtonSelector'
import { useRequireAuth } from '@/hooks/useAuth'

const CONVERSATION_CLEAR_CONFIRM = 'Are you sure you want to clear all conversation history? This action cannot be undone.'
const ACCOUNT_DELETE_CONFIRM = 'Are you sure you want to delete your account? This will permanently delete all your data including conversation history, logs, medical history, and preferences. This action cannot be undone. Type "DELETE" to confirm.'

export default function PreferencesPage() {
  const router = useRouter()
  const { mounted, isAuthenticated } = useRequireAuth()
  const [preferences, setPreferences] = useState(null)
  const [isEditing, setIsEditing] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)
  const [clearingConversation, setClearingConversation] = useState(false)
  const [deletingAccount, setDeletingAccount] = useState(false)
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

  const handleClearConversation = async () => {
    if (!window.confirm(CONVERSATION_CLEAR_CONFIRM)) {
      return
    }

    setClearingConversation(true)
    setError('')
    try {
      await api.clearConversationHistory()
      alert('Conversation history cleared successfully.')
    } catch (err) {
      setError(err.message || 'Failed to clear conversation history')
    } finally {
      setClearingConversation(false)
    }
  }

  const handleDeleteAccount = async () => {
    const confirmation = window.prompt(ACCOUNT_DELETE_CONFIRM)
    if (confirmation !== 'DELETE') {
      return
    }

    setDeletingAccount(true)
    setError('')
    try {
      await api.deleteAccount()
      removeToken()
      alert('Account deleted successfully.')
      router.push('/login')
    } catch (err) {
      setError(err.message || 'Failed to delete account')
      setDeletingAccount(false)
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
            <h1 style={{ margin: 0, fontSize: '1.25rem', color: 'var(--text-light)' }}>User Preferences</h1>
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
              <h2 style={{ margin: 0, fontSize: '1.75rem', fontWeight: '600', color: 'var(--text-light)', textShadow: '0 2px 4px rgba(0, 0, 0, 0.3)' }}>Your Fitness Preferences</h2>
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
                      <h3 style={{ marginBottom: 'var(--spacing-sm)', color: 'rgba(255, 255, 255, 0.8)', fontSize: '0.875rem', textTransform: 'uppercase', fontWeight: '600', letterSpacing: '0.5px', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                        Fitness Goals
                      </h3>
                      <p className="glassmorphism" style={{ margin: 0, padding: 'var(--spacing-md)', borderRadius: 'var(--border-radius)', whiteSpace: 'pre-wrap', color: 'var(--text-light)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                        {preferences.goals}
                      </p>
                    </div>
                  )}

                  {preferences.exercise_types && (
                    <div>
                      <h3 style={{ marginBottom: 'var(--spacing-sm)', color: 'rgba(255, 255, 255, 0.8)', fontSize: '0.875rem', textTransform: 'uppercase', fontWeight: '600', letterSpacing: '0.5px', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                        Preferred Exercise Types
                      </h3>
                      <p className="glassmorphism" style={{ margin: 0, padding: 'var(--spacing-md)', borderRadius: 'var(--border-radius)', color: 'var(--text-light)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                        {preferences.exercise_types}
                      </p>
                    </div>
                  )}

                  {preferences.activity_level && (
                    <div>
                      <h3 style={{ marginBottom: 'var(--spacing-sm)', color: 'rgba(255, 255, 255, 0.8)', fontSize: '0.875rem', textTransform: 'uppercase', fontWeight: '600', letterSpacing: '0.5px', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                        Activity Level
                      </h3>
                      <p className="glassmorphism" style={{ margin: 0, padding: 'var(--spacing-md)', borderRadius: 'var(--border-radius)', color: 'var(--text-light)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                        {preferences.activity_level}
                      </p>
                    </div>
                  )}

                  {preferences.location && (
                    <div>
                      <h3 style={{ marginBottom: 'var(--spacing-sm)', color: 'rgba(255, 255, 255, 0.8)', fontSize: '0.875rem', textTransform: 'uppercase', fontWeight: '600', letterSpacing: '0.5px', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                        Location
                      </h3>
                      <p className="glassmorphism" style={{ margin: 0, padding: 'var(--spacing-md)', borderRadius: 'var(--border-radius)', color: 'var(--text-light)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                        {preferences.location}
                      </p>
                    </div>
                  )}

                  {preferences.dietary_restrictions && (
                    <div>
                      <h3 style={{ marginBottom: 'var(--spacing-sm)', color: 'rgba(255, 255, 255, 0.8)', fontSize: '0.875rem', textTransform: 'uppercase', fontWeight: '600', letterSpacing: '0.5px', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                        Dietary Restrictions
                      </h3>
                      <p className="glassmorphism" style={{ margin: 0, padding: 'var(--spacing-md)', borderRadius: 'var(--border-radius)', color: 'var(--text-light)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                        {preferences.dietary_restrictions}
                      </p>
                    </div>
                  )}

                  {!preferences.goals && !preferences.exercise_types && !preferences.activity_level && !preferences.location && !preferences.dietary_restrictions && (
                    <div style={{ textAlign: 'center', padding: 'var(--spacing-2xl)', color: 'rgba(255, 255, 255, 0.9)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
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

          {/* Clear Conversation History and Delete Account Buttons */}
          <div style={{ marginTop: 'var(--spacing-2xl)', paddingTop: 'var(--spacing-2xl)', borderTop: '1px solid rgba(82, 82, 82, 0.2)' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-md)' }}>
              <button
                onClick={handleClearConversation}
                disabled={clearingConversation}
                style={{
                  padding: 'var(--spacing-md) var(--spacing-lg)',
                  background: clearingConversation 
                    ? 'rgba(108, 117, 125, 0.7)' 
                    : 'rgba(255, 152, 0, 0.8)',
                  backdropFilter: 'blur(20px) saturate(150%)',
                  WebkitBackdropFilter: 'blur(20px) saturate(150%)',
                  color: 'white',
                  border: '1px solid rgba(255, 255, 255, 0.3)',
                  borderRadius: 'var(--border-radius)',
                  cursor: clearingConversation ? 'not-allowed' : 'pointer',
                  fontWeight: '600',
                  fontSize: '1rem',
                  opacity: clearingConversation ? 0.6 : 1,
                  boxShadow: '0px 4px 15px 0 rgba(255, 152, 0, 0.3), inset 0px 0px 2px 1px rgba(255, 255, 255, 0.2)',
                  textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)',
                  transition: 'all 0.2s ease',
                  position: 'relative'
                }}
                onMouseEnter={(e) => {
                  if (!clearingConversation) {
                    e.target.style.background = 'rgba(255, 152, 0, 0.9)'
                    e.target.style.boxShadow = '0px 6px 20px 0 rgba(255, 152, 0, 0.4), inset 0px 0px 2px 1px rgba(255, 255, 255, 0.3)'
                  }
                }}
                onMouseLeave={(e) => {
                  if (!clearingConversation) {
                    e.target.style.background = 'rgba(255, 152, 0, 0.8)'
                    e.target.style.boxShadow = '0px 4px 15px 0 rgba(255, 152, 0, 0.3), inset 0px 0px 2px 1px rgba(255, 255, 255, 0.2)'
                  }
                }}
              >
                {clearingConversation ? 'Clearing...' : 'Clear Conversation History'}
              </button>

              <button
                onClick={handleDeleteAccount}
                disabled={deletingAccount}
                style={{
                  padding: 'var(--spacing-md) var(--spacing-lg)',
                  background: deletingAccount 
                    ? 'rgba(108, 117, 125, 0.7)' 
                    : 'rgba(255, 68, 68, 0.8)',
                  backdropFilter: 'blur(20px) saturate(150%)',
                  WebkitBackdropFilter: 'blur(20px) saturate(150%)',
                  color: 'white',
                  border: '1px solid rgba(255, 255, 255, 0.3)',
                  borderRadius: 'var(--border-radius)',
                  cursor: deletingAccount ? 'not-allowed' : 'pointer',
                  fontWeight: '600',
                  fontSize: '1rem',
                  opacity: deletingAccount ? 0.6 : 1,
                  boxShadow: '0px 4px 15px 0 rgba(255, 68, 68, 0.3), inset 0px 0px 2px 1px rgba(255, 255, 255, 0.2)',
                  textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)',
                  transition: 'all 0.2s ease',
                  position: 'relative'
                }}
                onMouseEnter={(e) => {
                  if (!deletingAccount) {
                    e.target.style.background = 'rgba(255, 68, 68, 0.9)'
                    e.target.style.boxShadow = '0px 6px 20px 0 rgba(255, 68, 68, 0.4), inset 0px 0px 2px 1px rgba(255, 255, 255, 0.3)'
                  }
                }}
                onMouseLeave={(e) => {
                  if (!deletingAccount) {
                    e.target.style.background = 'rgba(255, 68, 68, 0.8)'
                    e.target.style.boxShadow = '0px 4px 15px 0 rgba(255, 68, 68, 0.3), inset 0px 0px 2px 1px rgba(255, 255, 255, 0.2)'
                  }
                }}
              >
                {deletingAccount ? 'Deleting...' : 'Delete Account'}
              </button>
            </div>
          </div>
        </div>
      </div>
      </div>
    </div>
  )
}

