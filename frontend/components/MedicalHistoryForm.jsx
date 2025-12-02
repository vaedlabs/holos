'use client'

import { useState } from 'react'

export default function MedicalHistoryForm({ onSubmit, initialData = {} }) {
  const [formData, setFormData] = useState({
    conditions: initialData.conditions || '',
    limitations: initialData.limitations || '',
    medications: initialData.medications || '',
    notes: initialData.notes || '',
  })
  const [validationErrors, setValidationErrors] = useState({})

  const MAX_LENGTH = {
    conditions: 500,
    limitations: 1000,
    medications: 500,
    notes: 1000
  }

  const handleChange = (e) => {
    const { name, value } = e.target
    const maxLength = MAX_LENGTH[name]
    
    // Clear error when user starts typing
    if (validationErrors[name]) {
      setValidationErrors({ ...validationErrors, [name]: '' })
    }

    // Enforce max length
    if (maxLength && value.length > maxLength) {
      return // Don't update if exceeds max length
    }

    setFormData({
      ...formData,
      [name]: value,
    })
  }

  const validateForm = () => {
    const errors = {}
    
    if (formData.conditions && formData.conditions.length > MAX_LENGTH.conditions) {
      errors.conditions = `Conditions must be less than ${MAX_LENGTH.conditions} characters`
    }
    if (formData.limitations && formData.limitations.length > MAX_LENGTH.limitations) {
      errors.limitations = `Limitations must be less than ${MAX_LENGTH.limitations} characters`
    }
    if (formData.medications && formData.medications.length > MAX_LENGTH.medications) {
      errors.medications = `Medications must be less than ${MAX_LENGTH.medications} characters`
    }
    if (formData.notes && formData.notes.length > MAX_LENGTH.notes) {
      errors.notes = `Notes must be less than ${MAX_LENGTH.notes} characters`
    }

    if (Object.keys(errors).length > 0) {
      setValidationErrors(errors)
      return false
    }

    return true
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (validateForm()) {
      onSubmit(formData)
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-md)' }}>
      <div className="form-group">
        <label htmlFor="conditions" className="form-label">
          Medical Conditions (comma-separated, e.g., &quot;knee injury, back pain&quot;)
        </label>
        <input
          id="conditions"
          name="conditions"
          type="text"
          value={formData.conditions}
          onChange={handleChange}
          placeholder="e.g., knee injury, back pain"
          maxLength={MAX_LENGTH.conditions}
          className={`form-input ${validationErrors.conditions ? 'form-input-error' : ''}`}
          style={{ color: 'var(--text-light)' }}
        />
        {validationErrors.conditions && (
          <div className="text-error" style={{ fontSize: '0.875rem', marginTop: '0.0625rem', color: 'var(--danger-color)' }}>
            {validationErrors.conditions}
          </div>
        )}
        <small className="text-muted" style={{ display: 'block', marginTop: '0.0625rem', fontSize: '0.875rem', color: 'rgba(255, 255, 255, 0.7)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
          {formData.conditions.length}/{MAX_LENGTH.conditions} characters
        </small>
      </div>
      <div className="form-group">
        <label htmlFor="limitations" className="form-label">
          Physical Limitations
        </label>
        <textarea
          id="limitations"
          name="limitations"
          value={formData.limitations}
          onChange={handleChange}
          rows={3}
          placeholder="Describe any physical limitations..."
          maxLength={MAX_LENGTH.limitations}
          className={`form-textarea ${validationErrors.limitations ? 'form-input-error' : ''}`}
          style={{ color: 'var(--text-light)' }}
        />
        {validationErrors.limitations && (
          <div className="text-error" style={{ fontSize: '0.875rem', marginTop: '0.0625rem', color: 'var(--danger-color)' }}>
            {validationErrors.limitations}
          </div>
        )}
        <small className="text-muted" style={{ display: 'block', marginTop: '0.0625rem', fontSize: '0.875rem', color: 'rgba(255, 255, 255, 0.7)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
          {formData.limitations.length}/{MAX_LENGTH.limitations} characters
        </small>
      </div>
      <div className="form-group">
        <label htmlFor="medications" className="form-label">
          Current Medications
        </label>
        <input
          id="medications"
          name="medications"
          type="text"
          value={formData.medications}
          onChange={handleChange}
          placeholder="List any current medications"
          maxLength={MAX_LENGTH.medications}
          className={`form-input ${validationErrors.medications ? 'form-input-error' : ''}`}
          style={{ color: 'var(--text-light)' }}
        />
        {validationErrors.medications && (
          <div className="text-error" style={{ fontSize: '0.875rem', marginTop: '0.0625rem', color: 'var(--danger-color)' }}>
            {validationErrors.medications}
          </div>
        )}
        <small className="text-muted" style={{ display: 'block', marginTop: '0.0625rem', fontSize: '0.875rem', color: 'rgba(255, 255, 255, 0.7)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
          {formData.medications.length}/{MAX_LENGTH.medications} characters
        </small>
      </div>
      <div className="form-group">
        <label htmlFor="notes" className="form-label">
          Additional Notes
        </label>
        <textarea
          id="notes"
          name="notes"
          value={formData.notes}
          onChange={handleChange}
          rows={3}
          placeholder="Any additional medical information..."
          maxLength={MAX_LENGTH.notes}
          className={`form-textarea ${validationErrors.notes ? 'form-input-error' : ''}`}
          style={{ color: 'var(--text-light)' }}
        />
        {validationErrors.notes && (
          <div className="text-error" style={{ fontSize: '0.875rem', marginTop: '0.0625rem', color: 'var(--danger-color)' }}>
            {validationErrors.notes}
          </div>
        )}
        <small className="text-muted" style={{ display: 'block', marginTop: '0.0625rem', fontSize: '0.875rem', color: 'rgba(255, 255, 255, 0.7)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
          {formData.notes.length}/{MAX_LENGTH.notes} characters
        </small>
      </div>
      <button
        type="submit"
        className="btn btn-primary"
        style={{ width: '100%' }}
      >
        {initialData && (initialData.conditions || initialData.limitations || initialData.medications || initialData.notes) ? 'Save Changes' : 'Continue'}
      </button>
    </form>
  )
}

