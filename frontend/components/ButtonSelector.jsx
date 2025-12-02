'use client'

import { useState, useEffect } from 'react'

export default function ButtonSelector({ 
  label, 
  options, 
  value, 
  onChange, 
  placeholder = "Type comma-separated values..." 
}) {
  const [selectedOptions, setSelectedOptions] = useState(new Set())
  const [otherValue, setOtherValue] = useState('')
  const [showOther, setShowOther] = useState(false)
  const [isInitialized, setIsInitialized] = useState(false)

  // Parse initial value on mount or when value changes
  useEffect(() => {
    if (value) {
      const values = value.split(',').map(v => v.trim()).filter(v => v)
      const selected = new Set()
      const other = []
      
      values.forEach(val => {
        const found = options.find(opt => opt.toLowerCase() === val.toLowerCase())
        if (found) {
          selected.add(found)
        } else {
          other.push(val)
        }
      })
      
      setSelectedOptions(selected)
      setOtherValue(other.join(', '))
      setShowOther(other.length > 0)
    } else {
      setSelectedOptions(new Set())
      setOtherValue('')
      setShowOther(false)
    }
    setIsInitialized(true)
  }, [value, options])

  // Update parent when selection changes (but not on initial load)
  useEffect(() => {
    if (!isInitialized) return
    
    const selectedArray = Array.from(selectedOptions)
    const otherValues = otherValue 
      ? otherValue.split(',').map(v => v.trim()).filter(v => v)
      : []
    const allValues = showOther && otherValues.length > 0
      ? [...selectedArray, ...otherValues]
      : selectedArray
    
    const newValue = allValues.length > 0 ? allValues.join(', ') : ''
    // Only update if value actually changed to avoid loops
    if (newValue !== value) {
      onChange(newValue)
    }
  }, [selectedOptions, otherValue, showOther, isInitialized, value, onChange])

  const toggleOption = (option) => {
    const newSelected = new Set(selectedOptions)
    if (newSelected.has(option)) {
      newSelected.delete(option)
    } else {
      newSelected.add(option)
    }
    setSelectedOptions(newSelected)
  }

  const handleOtherToggle = () => {
    setShowOther(!showOther)
    if (!showOther) {
      setOtherValue('')
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      <label className="form-label" style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>
        {label}
      </label>
      
      {/* Button options */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
        {options.map((option) => {
          const isSelected = selectedOptions.has(option)
          return (
            <button
              key={option}
              type="button"
              onClick={() => toggleOption(option)}
              className={!isSelected ? 'glassmorphism' : ''}
              style={{
                padding: '0.625rem 1.25rem',
                background: isSelected 
                  ? 'linear-gradient(135deg, var(--primary-color) 0%, var(--primary-hover) 100%)'
                  : undefined,
                color: isSelected ? 'var(--text-light)' : 'var(--text-light)',
                border: isSelected 
                  ? '1px solid var(--primary-color)' 
                  : undefined,
                borderRadius: 'var(--border-radius-lg)',
                cursor: 'pointer',
                fontSize: '0.9rem',
                fontWeight: isSelected ? '500' : '400',
                transition: 'all 0.2s ease',
                whiteSpace: 'nowrap',
                boxShadow: isSelected ? 'var(--shadow-sm)' : undefined,
                textShadow: !isSelected ? '0 1px 2px rgba(0, 0, 0, 0.3)' : undefined
              }}
              onMouseEnter={(e) => {
                if (!isSelected) {
                  e.target.style.background = 'rgba(255, 255, 255, 0.1)'
                  e.target.style.borderColor = 'rgba(255, 255, 255, 0.4)'
                }
              }}
              onMouseLeave={(e) => {
                if (!isSelected) {
                  e.target.style.background = 'rgba(23, 23, 23, 0.05)'
                  e.target.style.borderColor = 'rgba(82, 82, 82, 0.2)'
                }
              }}
            >
              {option}
            </button>
          )
        })}
      </div>

      {/* Other option */}
      <div>
        <button
          type="button"
          onClick={handleOtherToggle}
          className={!showOther ? 'glassmorphism' : ''}
          style={{
            padding: '0.625rem 1.25rem',
            background: showOther 
              ? 'linear-gradient(135deg, var(--primary-color) 0%, var(--primary-hover) 100%)'
              : undefined,
            color: showOther ? 'var(--text-light)' : 'var(--text-light)',
            border: showOther 
              ? '1px solid var(--primary-color)' 
              : undefined,
            borderRadius: 'var(--border-radius-lg)',
            cursor: 'pointer',
            fontSize: '0.9rem',
            fontWeight: showOther ? '500' : '400',
            marginBottom: showOther ? 'var(--spacing-sm)' : '0',
            transition: 'all 0.2s ease',
            boxShadow: showOther ? 'var(--shadow-sm)' : undefined,
            textShadow: !showOther ? '0 1px 2px rgba(0, 0, 0, 0.3)' : undefined
          }}
          onMouseEnter={(e) => {
            if (!showOther) {
              e.target.style.background = 'rgba(255, 255, 255, 0.1)'
              e.target.style.borderColor = 'rgba(255, 255, 255, 0.4)'
            }
          }}
          onMouseLeave={(e) => {
            if (!showOther) {
              e.target.style.background = 'rgba(23, 23, 23, 0.05)'
              e.target.style.borderColor = 'rgba(82, 82, 82, 0.2)'
            }
          }}
        >
          Other
        </button>
        
        {showOther && (
          <input
            type="text"
            value={otherValue}
            onChange={(e) => setOtherValue(e.target.value)}
            placeholder={placeholder}
            className="form-input"
            style={{ marginTop: 'var(--spacing-sm)' }}
          />
        )}
      </div>
    </div>
  )
}

