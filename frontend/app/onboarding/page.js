'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import MedicalHistoryForm from '@/components/MedicalHistoryForm'
import ButtonSelector from '@/components/ButtonSelector'
import { useRequireAuth } from '@/hooks/useAuth'

export default function OnboardingPage() {
  const router = useRouter()
  const { mounted, isAuthenticated } = useRequireAuth()
  const [step, setStep] = useState(0) // 0: demographics, 1: medical, 2: preferences
  const [demographicsData, setDemographicsData] = useState({
    age: '',
    gender: '',
    lifestyle: '',
  })
  const [medicalData, setMedicalData] = useState({})
  const [preferencesData, setPreferencesData] = useState({
    goals: '',
    exercise_types: '',
    activity_level: '',
    location: '',
    dietary_restrictions: '',
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  // Don't render until mounted and authenticated
  if (!mounted || !isAuthenticated) {
    return null
  }

  const handleDemographicsSubmit = (e) => {
    e.preventDefault()
    setError('')
    
    // Validate demographics (all fields are optional, but if age is provided, it must be valid)
    const validationErrors = {}
    
    if (demographicsData.age !== '' && demographicsData.age !== null && (demographicsData.age < 13 || demographicsData.age > 120)) {
      validationErrors.age = 'Age must be between 13 and 120'
    }
    
    if (Object.keys(validationErrors).length > 0) {
      setError(Object.values(validationErrors)[0])
      return
    }
    
    setStep(1)
  }

  const handleDemographicsChange = (e) => {
    const { name, value } = e.target
    setDemographicsData({
      ...demographicsData,
      [name]: name === 'age' ? (value === '' ? '' : parseInt(value) || '') : value,
    })
  }

  const handleMedicalSubmit = (data) => {
    setMedicalData(data)
    setStep(2)
  }

  const handlePreferencesSubmit = async (e) => {
    e.preventDefault()
    setError('')
    
    // Validate preferences
    const validationErrors = {}
    
    // Location validation (if provided, should be reasonable length)
    if (preferencesData.location && preferencesData.location.length > 100) {
      validationErrors.location = 'Location must be less than 100 characters'
    }
    
    // Dietary restrictions validation (if provided, should be reasonable length)
    if (preferencesData.dietary_restrictions && preferencesData.dietary_restrictions.length > 200) {
      validationErrors.dietary_restrictions = 'Dietary restrictions must be less than 200 characters'
    }
    
    if (Object.keys(validationErrors).length > 0) {
      setError(Object.values(validationErrors)[0])
      return
    }

    setLoading(true)

    try {
      // Save medical history (even if empty, create the record)
      await api.updateMedicalHistory(medicalData)

      // Save user preferences (including demographics)
      await api.updateUserPreferences({
        ...preferencesData,
        ...demographicsData,
      })

      router.push('/dashboard')
    } catch (err) {
      setError(err.message || 'Failed to save information. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handlePreferencesChange = (e) => {
    setPreferencesData({
      ...preferencesData,
      [e.target.name]: e.target.value,
    })
  }

  return (
    <div style={{ minHeight: '100vh', background: 'linear-gradient(180deg, #0a0e27 0%, #1a1f3a 30%, #1e40af 60%, #0f172a 100%)', padding: 'var(--spacing-xl) 0' }}>
      <div className="container-sm">
        <div className="card">
          <h1 style={{ textAlign: 'center', marginBottom: 'var(--spacing-xl)', color: 'var(--text-light)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>Welcome! Let&apos;s set up your profile</h1>
          <div style={{ marginBottom: 'var(--spacing-xl)' }}>
            <div style={{ display: 'flex', gap: 'var(--spacing-sm)', marginBottom: 'var(--spacing-xl)' }}>
              <div
                style={{
                  flex: 1,
                  padding: 'var(--spacing-md)',
                  background: step >= 0 
                    ? 'linear-gradient(135deg, var(--primary-color) 0%, var(--primary-hover) 100%)'
                    : 'var(--bg-tertiary)',
                  color: step >= 0 ? 'white' : 'rgba(255, 255, 255, 0.7)',
                  textShadow: step >= 0 ? '0 1px 2px rgba(0, 0, 0, 0.3)' : 'none',
                  textAlign: 'center',
                  borderRadius: 'var(--border-radius)',
                  fontWeight: '600',
                  transition: 'all 0.3s ease',
                  boxShadow: step >= 0 ? 'var(--shadow-sm)' : 'none',
                  border: step >= 0 ? 'none' : '1px solid var(--border-color)'
                }}
              >
                Step 0: Demographics
              </div>
              <div
                style={{
                  flex: 1,
                  padding: 'var(--spacing-md)',
                  background: step >= 1 
                    ? 'linear-gradient(135deg, var(--primary-color) 0%, var(--primary-hover) 100%)'
                    : 'var(--bg-tertiary)',
                  color: step >= 1 ? 'white' : 'rgba(255, 255, 255, 0.7)',
                  textShadow: step >= 1 ? '0 1px 2px rgba(0, 0, 0, 0.3)' : 'none',
                  textAlign: 'center',
                  borderRadius: 'var(--border-radius)',
                  fontWeight: '600',
                  transition: 'all 0.3s ease',
                  boxShadow: step >= 1 ? 'var(--shadow-sm)' : 'none',
                  border: step >= 1 ? 'none' : '1px solid var(--border-color)'
                }}
              >
                Step 1: Medical History
              </div>
              <div
                style={{
                  flex: 1,
                  padding: 'var(--spacing-md)',
                  background: step >= 2 
                    ? 'linear-gradient(135deg, var(--primary-color) 0%, var(--primary-hover) 100%)'
                    : 'var(--bg-tertiary)',
                  color: step >= 2 ? 'white' : 'rgba(255, 255, 255, 0.7)',
                  textShadow: step >= 2 ? '0 1px 2px rgba(0, 0, 0, 0.3)' : 'none',
                  textAlign: 'center',
                  borderRadius: 'var(--border-radius)',
                  fontWeight: '600',
                  transition: 'all 0.3s ease',
                  boxShadow: step >= 2 ? 'var(--shadow-sm)' : 'none',
                  border: step >= 2 ? 'none' : '1px solid var(--border-color)'
                }}
              >
                Step 2: Preferences
              </div>
            </div>
          </div>

          {step === 0 && (
            <div>
              <h2 style={{ color: 'var(--text-light)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>Demographics</h2>
              <p style={{ marginBottom: 'var(--spacing-lg)', color: 'rgba(255, 255, 255, 0.9)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                Tell us a bit about yourself to personalize your experience.
              </p>
              <form onSubmit={handleDemographicsSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-md)' }}>
                <div>
                  <label htmlFor="age" className="form-label" style={{ display: 'block', marginBottom: '0.5rem' }}>
                    Age <span style={{ color: 'rgba(255, 255, 255, 0.6)' }}>(optional)</span>
                  </label>
                  <input
                    id="age"
                    name="age"
                    type="number"
                    min="13"
                    max="120"
                    value={demographicsData.age}
                    onChange={handleDemographicsChange}
                    placeholder="Enter your age"
                    className="form-input"
                  />
                  {demographicsData.age && (demographicsData.age < 13 || demographicsData.age > 120) && (
                    <small style={{ color: 'rgba(255, 68, 68, 0.9)', display: 'block', marginTop: '0.25rem' }}>
                      Age must be between 13 and 120
                    </small>
                  )}
                </div>
                <div>
                  <label htmlFor="gender" className="form-label" style={{ display: 'block', marginBottom: '0.5rem' }}>
                    Gender/Sex <span style={{ color: 'rgba(255, 255, 255, 0.6)' }}>(optional)</span>
                  </label>
                  <select
                    id="gender"
                    name="gender"
                    value={demographicsData.gender}
                    onChange={handleDemographicsChange}
                    className="form-select"
                  >
                    <option value="">Select gender/sex</option>
                    <option value="XX">XX (Biological Female)</option>
                    <option value="XY">XY (Biological Male)</option>
                    <option value="other">Other</option>
                    <option value="">Prefer not to say</option>
                  </select>
                </div>
                <div>
                  <label htmlFor="lifestyle" className="form-label" style={{ display: 'block', marginBottom: '0.5rem' }}>
                    Lifestyle <span style={{ color: 'rgba(255, 255, 255, 0.6)' }}>(optional)</span>
                  </label>
                  <small style={{ display: 'block', marginBottom: '0.5rem', color: 'rgba(255, 255, 255, 0.7)', fontSize: '0.875rem', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                    Your daily lifestyle and activity patterns
                  </small>
                  <select
                    id="lifestyle"
                    name="lifestyle"
                    value={demographicsData.lifestyle}
                    onChange={handleDemographicsChange}
                    className="form-select"
                  >
                    <option value="">Select lifestyle</option>
                    <option value="sedentary">Sedentary</option>
                    <option value="active">Active</option>
                    <option value="very_active">Very Active</option>
                    <option value="athlete">Athlete</option>
                  </select>
                </div>
                {error && (
                  <div className="alert alert-error" style={{ 
                    backgroundColor: 'rgba(255, 68, 68, 0.2)', 
                    color: 'rgba(255, 255, 255, 0.95)', 
                    border: '1px solid rgba(255, 68, 68, 0.5)',
                    textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)',
                    backdropFilter: 'blur(10px) saturate(150%)',
                    WebkitBackdropFilter: 'blur(10px) saturate(150%)'
                  }}>
                    {error}
                  </div>
                )}
                <div style={{ display: 'flex', gap: 'var(--spacing-md)', marginTop: 'var(--spacing-lg)' }}>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    style={{ flex: 1 }}
                  >
                    Next
                  </button>
                </div>
              </form>
            </div>
          )}

          {step === 1 && (
            <div>
              <h2 style={{ color: 'var(--text-light)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>Medical History</h2>
              <p style={{ marginBottom: 'var(--spacing-lg)', color: 'rgba(255, 255, 255, 0.9)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                This information helps us recommend safe exercises for you.
              </p>
              <MedicalHistoryForm onSubmit={handleMedicalSubmit} />
            </div>
          )}

          {step === 2 && (
            <div>
              <h2 style={{ color: 'var(--text-light)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>Fitness Preferences</h2>
              <p style={{ marginBottom: 'var(--spacing-lg)', color: 'rgba(255, 255, 255, 0.9)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                Tell us about your fitness goals and preferences.
              </p>
          <form onSubmit={handlePreferencesSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-md)' }}>
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
              value={preferencesData.goals}
              onChange={(value) => setPreferencesData({ ...preferencesData, goals: value })}
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
              value={preferencesData.exercise_types}
              onChange={(value) => setPreferencesData({ ...preferencesData, exercise_types: value })}
              placeholder="Type other exercise types (comma-separated)..."
            />
            <div>
              <label htmlFor="activity_level" className="form-label" style={{ display: 'block', marginBottom: '0.5rem' }}>
                Activity Level
              </label>
              <small style={{ display: 'block', marginBottom: '0.5rem', color: 'rgba(255, 255, 255, 0.7)', fontSize: '0.875rem', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                The level of fitness activity you want to do
              </small>
              <select
                id="activity_level"
                name="activity_level"
                value={preferencesData.activity_level}
                onChange={handlePreferencesChange}
                className="form-select"
              >
                <option value="">Select activity level</option>
                <option value="light">Light</option>
                <option value="moderate">Moderate</option>
                <option value="high">High</option>
                <option value="very_high">Very High</option>
              </select>
            </div>
            <div>
              <label htmlFor="location" className="form-label" style={{ display: 'block', marginBottom: '0.5rem' }}>
                Location (optional)
              </label>
              <input
                id="location"
                name="location"
                type="text"
                value={preferencesData.location}
                onChange={handlePreferencesChange}
                placeholder="City or address"
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
              value={preferencesData.dietary_restrictions}
              onChange={(value) => setPreferencesData({ ...preferencesData, dietary_restrictions: value })}
              placeholder="Type other dietary restrictions (comma-separated)..."
              conflicts={{
                'Vegan': ['Non-vegetarian', 'Pescatarian', 'Vegetarian'],
                'Vegetarian': ['Non-vegetarian', 'Pescatarian'],
                'Pescatarian': ['Vegan', 'Vegetarian', 'Non-vegetarian'],
                'Non-vegetarian': ['Vegan', 'Vegetarian', 'Pescatarian']
              }}
            />
              {error && (
                <div className="alert alert-error" style={{ 
                  backgroundColor: 'rgba(255, 68, 68, 0.2)', 
                  color: 'rgba(255, 255, 255, 0.95)', 
                  border: '1px solid rgba(255, 68, 68, 0.5)',
                  textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)',
                  backdropFilter: 'blur(10px) saturate(150%)',
                  WebkitBackdropFilter: 'blur(10px) saturate(150%)'
                }}>
                  {error}
                </div>
              )}
              <div style={{ display: 'flex', gap: 'var(--spacing-md)', marginTop: 'var(--spacing-lg)' }}>
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  className="btn btn-secondary"
                  style={{ flex: 1 }}
                >
                  Back
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="btn btn-primary"
                  style={{ flex: 1 }}
                >
                  {loading ? 'Saving...' : 'Complete Setup'}
                </button>
              </div>
            </form>
          </div>
        )}
        </div>
      </div>
    </div>
  )
}

