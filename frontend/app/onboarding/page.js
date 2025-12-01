'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import MedicalHistoryForm from '@/components/MedicalHistoryForm'
import ButtonSelector from '@/components/ButtonSelector'

export default function OnboardingPage() {
  const router = useRouter()
  const [step, setStep] = useState(1) // 1: medical, 2: preferences
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

      // Save user preferences (even if empty, create the record)
      await api.updateUserPreferences(preferencesData)

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
    <div style={{ minHeight: '100vh', background: 'var(--bg-secondary)', padding: 'var(--spacing-xl) 0' }}>
      <div className="container-sm">
        <div className="card">
          <h1 style={{ textAlign: 'center', marginBottom: 'var(--spacing-xl)' }}>Welcome! Let&apos;s set up your profile</h1>
          <div style={{ marginBottom: 'var(--spacing-xl)' }}>
            <div style={{ display: 'flex', gap: 'var(--spacing-sm)', marginBottom: 'var(--spacing-xl)' }}>
              <div
                style={{
                  flex: 1,
                  padding: 'var(--spacing-md)',
                  background: step >= 1 
                    ? 'linear-gradient(135deg, var(--primary-color) 0%, var(--primary-hover) 100%)'
                    : 'var(--bg-tertiary)',
                  color: step >= 1 ? 'white' : 'var(--text-secondary)',
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
                  color: step >= 2 ? 'white' : 'var(--text-secondary)',
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

          {step === 1 && (
            <div>
              <h2>Medical History</h2>
              <p className="text-muted" style={{ marginBottom: 'var(--spacing-lg)' }}>
                This information helps us recommend safe exercises for you.
              </p>
              <MedicalHistoryForm onSubmit={handleMedicalSubmit} />
            </div>
          )}

          {step === 2 && (
            <div>
              <h2>Fitness Preferences</h2>
              <p className="text-muted" style={{ marginBottom: 'var(--spacing-lg)' }}>
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
              <label htmlFor="activity_level" style={{ display: 'block', marginBottom: '0.5rem' }}>
                Activity Level
              </label>
              <select
                id="activity_level"
                name="activity_level"
                value={preferencesData.activity_level}
                onChange={handlePreferencesChange}
                style={{ width: '100%', padding: '0.5rem', border: '1px solid #ccc', borderRadius: '4px' }}
              >
                <option value="">Select activity level</option>
                <option value="sedentary">Sedentary</option>
                <option value="light">Light</option>
                <option value="moderate">Moderate</option>
                <option value="active">Active</option>
                <option value="very_active">Very Active</option>
              </select>
            </div>
            <div>
              <label htmlFor="location" style={{ display: 'block', marginBottom: '0.5rem' }}>
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
                style={{ width: '100%', padding: '0.5rem', border: '1px solid #ccc', borderRadius: '4px' }}
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
            />
              {error && (
                <div className="alert alert-error">
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

