export default function Home() {
  return (
    <div style={{ 
      minHeight: '100vh', 
      display: 'flex', 
      flexDirection: 'column', 
      alignItems: 'center', 
      justifyContent: 'center', 
      padding: '2rem',
      position: 'relative',
      overflow: 'hidden'
    }}>
      <div className="lava-lamp-bg">
        <div className="lava-blob blob-1"></div>
        <div className="lava-blob blob-2"></div>
        <div className="lava-blob blob-3"></div>
      </div>
      <div className="card lava-lamp-overlay" style={{ 
        maxWidth: '600px', 
        width: '100%', 
        textAlign: 'center',
        animation: 'fadeIn 0.5s ease-in',
        background: 'rgba(255, 255, 255, 0.95)',
        border: '1px solid rgba(255, 255, 255, 0.3)'
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

