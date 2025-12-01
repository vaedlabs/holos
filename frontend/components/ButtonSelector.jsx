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
      <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>
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
              style={{
                padding: '0.625rem 1.25rem',
                background: isSelected 
                  ? 'linear-gradient(135deg, var(--primary-color) 0%, var(--primary-hover) 100%)'
                  : 'var(--bg-primary)',
                color: isSelected ? 'var(--text-light)' : 'var(--text-primary)',
                border: isSelected 
                  ? '1px solid var(--primary-color)' 
                  : '1px solid var(--border-color)',
                borderRadius: 'var(--border-radius-lg)',
                cursor: 'pointer',
                fontSize: '0.9rem',
                fontWeight: isSelected ? '500' : '400',
                transition: 'all 0.2s ease',
                whiteSpace: 'nowrap',
                boxShadow: isSelected ? 'var(--shadow-sm)' : 'none'
              }}
              onMouseEnter={(e) => {
                if (!isSelected) {
                  e.target.style.background = 'var(--bg-tertiary)'
                  e.target.style.borderColor = 'var(--primary-color)'
                }
              }}
              onMouseLeave={(e) => {
                if (!isSelected) {
                  e.target.style.background = 'var(--bg-primary)'
                  e.target.style.borderColor = 'var(--border-color)'
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
          style={{
            padding: '0.625rem 1.25rem',
            background: showOther 
              ? 'linear-gradient(135deg, var(--primary-color) 0%, var(--primary-hover) 100%)'
              : 'var(--bg-primary)',
            color: showOther ? 'var(--text-light)' : 'var(--text-primary)',
            border: showOther 
              ? '1px solid var(--primary-color)' 
              : '1px solid var(--border-color)',
            borderRadius: 'var(--border-radius-lg)',
            cursor: 'pointer',
            fontSize: '0.9rem',
            fontWeight: showOther ? '500' : '400',
            marginBottom: showOther ? 'var(--spacing-sm)' : '0',
            transition: 'all 0.2s ease',
            boxShadow: showOther ? 'var(--shadow-sm)' : 'none'
          }}
          onMouseEnter={(e) => {
            if (!showOther) {
              e.target.style.background = 'var(--bg-tertiary)'
              e.target.style.borderColor = 'var(--primary-color)'
            }
          }}
          onMouseLeave={(e) => {
            if (!showOther) {
              e.target.style.background = 'var(--bg-primary)'
              e.target.style.borderColor = 'var(--border-color)'
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

