export default function Home() {
  return (
    <div style={{ 
      minHeight: '100vh', 
      display: 'flex', 
      flexDirection: 'column', 
      alignItems: 'center', 
      justifyContent: 'center', 
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', 
      padding: '2rem' 
    }}>
      <div className="card" style={{ 
        maxWidth: '600px', 
        width: '100%', 
        textAlign: 'center',
        animation: 'fadeIn 0.5s ease-in'
      }}>
        <h1 style={{ 
          marginBottom: 'var(--spacing-md)', 
          color: 'var(--text-primary)',
          fontSize: '2.5rem',
          fontWeight: '700',
          background: 'linear-gradient(135deg, var(--primary-color) 0%, #764ba2 100%)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          backgroundClip: 'text'
        }}>
          Holos
        </h1>
        <p style={{ 
          fontSize: '1.125rem', 
          color: 'var(--text-secondary)', 
          marginBottom: 'var(--spacing-2xl)',
          lineHeight: '1.6'
        }}>
          AI-powered fitness application with specialized agents for physical fitness, nutrition, and mental wellness.
        </p>
        <div style={{ 
          display: 'flex', 
          gap: 'var(--spacing-md)', 
          justifyContent: 'center', 
          flexWrap: 'wrap' 
        }}>
          <a href="/login" className="btn btn-primary" style={{ textDecoration: 'none', minWidth: '120px' }}>
            Login
          </a>
          <a href="/register" className="btn btn-outline" style={{ textDecoration: 'none', minWidth: '120px' }}>
            Register
          </a>
        </div>
      </div>
    </div>
  )
}

