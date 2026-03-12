'use client'

import Silk from '@/components/Silk'

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
      <Silk
        speed={5}
        scale={1}
        color="#295eff"
        noiseIntensity={1.5}
        rotation={0}
      />
      <div className="card glassmorphism" style={{ 
        maxWidth: '600px', 
        width: '100%', 
        textAlign: 'center',
        animation: 'fadeIn 0.5s ease-in'
      }}>
        <h1 style={{ 
          marginBottom: 'var(--spacing-md)', 
          color: 'white',
          fontSize: '8rem',
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

