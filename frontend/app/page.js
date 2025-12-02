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
      <div className="card glassmorphism" style={{ 
        maxWidth: '600px', 
        width: '100%', 
        textAlign: 'center',
        animation: 'fadeIn 0.5s ease-in'
      }}>
        <h1 style={{ 
          marginBottom: 'var(--spacing-md)', 
          color: 'white',
          fontSize: '2.5rem',
          fontWeight: '700',
          textShadow: '0 2px 4px rgba(0, 0, 0, 0.3)'
        }}>
          Holos
        </h1>
        <p style={{ 
          fontSize: '1.125rem', 
          color: 'rgba(255, 255, 255, 0.9)', 
          marginBottom: 'var(--spacing-2xl)',
          lineHeight: '1.6',
          textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)'
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

