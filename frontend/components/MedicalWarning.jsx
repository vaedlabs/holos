'use client'

/**
 * MedicalWarning Component
 * Displays medical conflict warnings with appropriate severity styling
 */
export default function MedicalWarning({ warnings, severity }) {
  if (!warnings || warnings.length === 0) {
    return null
  }

  // Detect severity from warning messages if not provided
  // Look for "BLOCKED:" in messages to determine if it's a block/critical warning
  const hasBlocked = warnings.some(w => w.toUpperCase().includes('BLOCKED'))
  const detectedSeverity = severity || (hasBlocked ? 'critical' : 'warning')

  // Determine severity styling
  const severityStyles = {
    critical: {
      background: '#fee',
      borderColor: '#dc3545',
      icon: '🚨',
      title: 'BLOCKED - Medical Safety Alert',
      textColor: '#721c24',
      introText: 'The following exercises should be AVOIDED due to your medical conditions:'
    },
    block: {
      background: '#fee',
      borderColor: '#dc3545',
      icon: '🚨',
      title: 'BLOCKED - Medical Safety Alert',
      textColor: '#721c24',
      introText: 'The following exercises should be AVOIDED due to your medical conditions:'
    },
    warning: {
      background: '#fff3cd',
      borderColor: '#ffc107',
      icon: '⚠️',
      title: 'Medical Warning',
      textColor: '#856404',
      introText: 'The following exercises may conflict with your medical conditions:'
    },
    info: {
      background: '#d1ecf1',
      borderColor: '#17a2b8',
      icon: 'ℹ️',
      title: 'Medical Note',
      textColor: '#0c5460',
      introText: 'Please note the following regarding your medical conditions:'
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
            {style.title}
          </strong>
          <p style={{
            color: style.textColor,
            fontSize: '0.875rem',
            margin: '0 0 var(--spacing-xs) 0',
            lineHeight: '1.5'
          }}>
            {style.introText}
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
                ⚠️ Please consult with your healthcare provider before attempting these exercises.
              </strong>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

