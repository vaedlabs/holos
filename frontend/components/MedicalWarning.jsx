'use client'

/**
 * MedicalWarning Component
 * Displays medical conflict warnings with appropriate severity styling
 * Context-aware: detects exercise, dietary, or other conflicts
 */
export default function MedicalWarning({ warnings, severity }) {
  if (!warnings || warnings.length === 0) {
    return null
  }

  // Detect severity from warning messages if not provided
  // Look for "BLOCKED:" in messages to determine if it's a block/critical warning
  const hasBlocked = warnings.some(w => w.toUpperCase().includes('BLOCKED'))
  const detectedSeverity = severity || (hasBlocked ? 'critical' : 'warning')

  // Detect context from warning messages
  const allWarningsText = warnings.join(' ').toLowerCase()
  const isDietaryConflict = allWarningsText.includes('dietary restriction') || 
                           allWarningsText.includes('meal') || 
                           allWarningsText.includes('food') ||
                           allWarningsText.includes('contains') && (allWarningsText.includes('vegan') || allWarningsText.includes('vegetarian') || allWarningsText.includes('dairy') || allWarningsText.includes('gluten'))
  
  const isExerciseConflict = allWarningsText.includes('exercise') || 
                             allWarningsText.includes('workout') ||
                             allWarningsText.includes('squat') ||
                             allWarningsText.includes('deadlift') ||
                             allWarningsText.includes('running')

  // Determine context-specific messages
  const getContextMessages = () => {
    if (isDietaryConflict) {
      return {
        critical: {
          title: 'BLOCKED - Dietary Restriction Alert',
          introText: 'The following items conflict with your dietary restrictions:',
          footerText: '⚠️ This meal contains items that conflict with your dietary preferences. Please choose alternatives that align with your restrictions.'
        },
        block: {
          title: 'BLOCKED - Dietary Restriction Alert',
          introText: 'The following items conflict with your dietary restrictions:',
          footerText: '⚠️ This meal contains items that conflict with your dietary preferences. Please choose alternatives that align with your restrictions.'
        },
        warning: {
          title: 'Dietary Restriction Warning',
          introText: 'The following items may conflict with your dietary preferences:',
          footerText: '⚠️ Consider alternatives that better align with your dietary preferences.'
        }
      }
    } else if (isExerciseConflict) {
      return {
        critical: {
          title: 'BLOCKED - Medical Safety Alert',
          introText: 'The following exercises should be AVOIDED due to your medical conditions:',
          footerText: '⚠️ Please consult with your healthcare provider before attempting these exercises.'
        },
        block: {
          title: 'BLOCKED - Medical Safety Alert',
          introText: 'The following exercises should be AVOIDED due to your medical conditions:',
          footerText: '⚠️ Please consult with your healthcare provider before attempting these exercises.'
        },
        warning: {
          title: 'Medical Warning',
          introText: 'The following exercises may conflict with your medical conditions:',
          footerText: '⚠️ Please consult with your healthcare provider and consider modifications.'
        }
      }
    } else {
      // Generic/other conflicts
      return {
        critical: {
          title: 'BLOCKED - Safety Alert',
          introText: 'The following should be AVOIDED due to your conditions or preferences:',
          footerText: '⚠️ Please review this carefully and consult with your healthcare provider if needed.'
        },
        block: {
          title: 'BLOCKED - Safety Alert',
          introText: 'The following should be AVOIDED due to your conditions or preferences:',
          footerText: '⚠️ Please review this carefully and consult with your healthcare provider if needed.'
        },
        warning: {
          title: 'Safety Warning',
          introText: 'The following may conflict with your conditions or preferences:',
          footerText: '⚠️ Please review this carefully.'
        }
      }
    }
  }

  const contextMessages = getContextMessages()
  const contextStyle = contextMessages[detectedSeverity] || contextMessages.warning

  // Determine severity styling
  const severityStyles = {
    critical: {
      background: '#fee',
      borderColor: '#dc3545',
      icon: '🚨',
      textColor: '#721c24'
    },
    block: {
      background: '#fee',
      borderColor: '#dc3545',
      icon: '🚨',
      textColor: '#721c24'
    },
    warning: {
      background: '#fff3cd',
      borderColor: '#ffc107',
      icon: '⚠️',
      textColor: '#856404'
    },
    info: {
      background: '#d1ecf1',
      borderColor: '#17a2b8',
      icon: 'ℹ️',
      textColor: '#0c5460'
    }
  }

  const style = severityStyles[detectedSeverity] || severityStyles.warning

  return (
    <div
      style={{
        marginTop: 'var(--spacing-md)',
        padding: 'var(--spacing-md)',
        background: style.background,
        border: `2px solid ${style.borderColor}`,
        borderRadius: 'var(--border-radius)',
        boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
      }}
    >
      <div style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 'var(--spacing-sm)',
        marginBottom: 'var(--spacing-sm)'
      }}>
        <span style={{ fontSize: '1.25rem', lineHeight: '1' }}>{style.icon}</span>
        <div style={{ flex: 1 }}>
          <strong style={{
            display: 'block',
            color: style.textColor,
            fontSize: '0.95rem',
            fontWeight: '600',
            marginBottom: 'var(--spacing-xs)'
          }}>
            {contextStyle.title}
          </strong>
          <p style={{
            color: style.textColor,
            fontSize: '0.875rem',
            margin: '0 0 var(--spacing-xs) 0',
            lineHeight: '1.5'
          }}>
            {contextStyle.introText}
          </p>
          <ul style={{
            margin: 'var(--spacing-xs) 0 0 0',
            paddingLeft: '1.5rem',
            color: style.textColor,
            fontSize: '0.875rem',
            lineHeight: '1.6'
          }}>
            {warnings.map((warning, i) => (
              <li key={i} style={{ marginBottom: '0.25rem' }}>
                {warning}
              </li>
            ))}
          </ul>
          {(detectedSeverity === 'critical' || detectedSeverity === 'block') && (
            <div style={{
              marginTop: 'var(--spacing-sm)',
              padding: 'var(--spacing-sm)',
              background: 'rgba(220, 53, 69, 0.1)',
              borderRadius: 'var(--border-radius-sm)',
              border: '1px solid rgba(220, 53, 69, 0.3)'
            }}>
              <strong style={{ color: style.textColor, fontSize: '0.875rem' }}>
                {contextStyle.footerText}
              </strong>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

