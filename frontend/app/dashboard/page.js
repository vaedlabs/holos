'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, getToken, removeToken } from '@/lib/api'
import MedicalWarning from '@/components/MedicalWarning'

export default function DashboardPage() {
  const router = useRouter()
  const [messages, setMessages] = useState([])
  const [inputMessage, setInputMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [mounted, setMounted] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [workoutLogsOpen, setWorkoutLogsOpen] = useState(false)
  const [workoutLogs, setWorkoutLogs] = useState([])
  const [loadingLogs, setLoadingLogs] = useState(false)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    if (!mounted) return
    
    // Check if user is authenticated
    const token = getToken()
    if (!token) {
      console.log('No token found, redirecting to login')
      router.push('/login')
      return
    }

    console.log('Token found, user authenticated')
    
    // Load conversation history
    const loadConversation = async () => {
      try {
        const history = await api.getConversationHistory()
        if (history.messages && history.messages.length > 0) {
          // Convert API messages to component format
          const loadedMessages = history.messages.map(msg => ({
            role: msg.role,
            content: msg.content,
            warnings: msg.warnings || null
          }))
          setMessages(loadedMessages)
        } else {
          // No history, add welcome message
          setMessages([{
            role: 'assistant',
            content: 'Hello! I\'m your Physical Fitness Coach. How can I help you today?'
          }])
        }
      } catch (err) {
        console.error('Error loading conversation:', err)
        // On error, start with welcome message
        setMessages([{
          role: 'assistant',
          content: 'Hello! I\'m your Physical Fitness Coach. How can I help you today?'
        }])
      }
    }
    
    loadConversation()
    loadWorkoutLogs()
  }, [mounted, router])

  const loadWorkoutLogs = async () => {
    setLoadingLogs(true)
    try {
      const data = await api.getWorkoutLogs(10, 0) // Get 10 most recent logs
      setWorkoutLogs(data.logs || [])
    } catch (err) {
      console.error('Error loading workout logs:', err)
      // Don't show error to user, just log it
    } finally {
      setLoadingLogs(false)
    }
  }

  const handleWorkoutLogsClick = () => {
    setWorkoutLogsOpen(!workoutLogsOpen)
    if (!workoutLogsOpen) {
      loadWorkoutLogs()
    }
  }

  useEffect(() => {
    // Scroll to bottom when messages change
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    // Close menu when clicking outside
    const handleClickOutside = (event) => {
      if (menuOpen && !event.target.closest('[aria-label="Menu"]') && !event.target.closest('div[style*="position: absolute"]')) {
        setMenuOpen(false)
      }
      if (workoutLogsOpen && !event.target.closest('[aria-label="Workout Logs"]') && !event.target.closest('div[style*="workout-logs-modal"]')) {
        setWorkoutLogsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [menuOpen, workoutLogsOpen])

  const handleSend = async (e) => {
    e.preventDefault()
    if (!inputMessage.trim() || loading) return

    const userMessage = {
      role: 'user',
      content: inputMessage
    }

    setMessages(prev => [...prev, userMessage])
    setInputMessage('')
    setLoading(true)
    setError('')

    try {
      // Save user message to database
      try {
        await api.saveMessage('user', inputMessage)
      } catch (saveErr) {
        console.warn('Failed to save user message:', saveErr)
        // Continue even if save fails
      }

      const response = await api.chatWithAgent(inputMessage)
      
      const assistantMessage = {
        role: 'assistant',
        content: response.response,
        warnings: response.warnings
      }

      setMessages(prev => [...prev, assistantMessage])
      
      // Save assistant message to database
      try {
        await api.saveMessage('assistant', response.response, response.warnings)
      } catch (saveErr) {
        console.warn('Failed to save assistant message:', saveErr)
        // Continue even if save fails
      }
    } catch (err) {
      console.error('Chat error:', err);
      const errorMessage = err.message || 'Failed to get response from agent';
      setError(errorMessage);
      
      // If it's an auth error, redirect to login after showing error
      if (errorMessage.includes('Authentication failed') || errorMessage.includes('401') || errorMessage.includes('Not authenticated')) {
        setTimeout(() => {
          removeToken();
          router.push('/login');
        }, 2000); // Give user time to see the error
      }
      
      // Remove the user message if there was an error
      setMessages(prev => prev.slice(0, -1))
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = () => {
    removeToken()
    router.push('/login')
  }

  // Don't render until mounted to avoid hydration mismatch
  if (!mounted) {
    return null
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--bg-secondary)' }}>
      {/* Header */}
      <header className="header">
        <div className="header-content">
          <h1 style={{ margin: 0, fontSize: '1.25rem' }}>Holos - Physical Fitness Coach</h1>
          <div style={{ display: 'flex', gap: 'var(--spacing-sm)', alignItems: 'center' }}>
            {/* Workout Logs Button */}
            <div style={{ position: 'relative' }}>
              <button
                onClick={handleWorkoutLogsClick}
                style={{
                  padding: '0.5rem 0.75rem',
                  background: workoutLogsOpen ? 'rgba(255,255,255,0.3)' : 'rgba(255,255,255,0.2)',
                  color: 'white',
                  border: '1px solid rgba(255,255,255,0.4)',
                  borderRadius: 'var(--border-radius)',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                  fontWeight: '500',
                  whiteSpace: 'nowrap',
                  transition: 'all 0.2s ease'
                }}
                aria-label="Workout Logs"
                onMouseEnter={(e) => {
                  if (!workoutLogsOpen) {
                    e.target.style.background = 'rgba(255,255,255,0.25)'
                  }
                }}
                onMouseLeave={(e) => {
                  if (!workoutLogsOpen) {
                    e.target.style.background = 'rgba(255,255,255,0.2)'
                  }
                }}
              >
                Workouts
              </button>
              
              {/* Workout Logs Modal */}
              {workoutLogsOpen && (
                <div 
                  className="workout-logs-modal"
                  style={{
                    position: 'absolute',
                    top: '100%',
                    right: 0,
                    marginTop: '0.5rem',
                    background: 'white',
                    borderRadius: '8px',
                    boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                    minWidth: '400px',
                    maxWidth: '500px',
                    maxHeight: '500px',
                    zIndex: 1000,
                    overflow: 'hidden',
                    display: 'flex',
                    flexDirection: 'column'
                  }}
                >
                  <div style={{
                    padding: 'var(--spacing-md)',
                    borderBottom: '1px solid var(--border-color)',
                    background: 'var(--bg-primary)'
                  }}>
                    <h3 style={{ 
                      margin: 0, 
                      fontSize: '1rem',
                      fontWeight: '600',
                      color: 'var(--text-primary)'
                    }}>
                      Workout Logs
                    </h3>
                  </div>
                  
                  <div style={{
                    flex: 1,
                    overflowY: 'auto',
                    padding: 'var(--spacing-md)'
                  }}>
                    {loadingLogs ? (
                      <div style={{ 
                        padding: 'var(--spacing-lg)', 
                        textAlign: 'center', 
                        color: 'var(--text-secondary)',
                        fontSize: '0.875rem'
                      }}>
                        Loading workouts...
                      </div>
                    ) : workoutLogs.length > 0 ? (
                      <div style={{ 
                        display: 'flex', 
                        flexDirection: 'column', 
                        gap: 'var(--spacing-sm)'
                      }}>
                        {workoutLogs.map((log) => {
                          const workoutDate = new Date(log.workout_date)
                          const formattedDate = workoutDate.toLocaleDateString('en-US', { 
                            month: 'short', 
                            day: 'numeric', 
                            year: 'numeric' 
                          })
                          const formattedTime = workoutDate.toLocaleTimeString('en-US', { 
                            hour: 'numeric', 
                            minute: '2-digit' 
                          })
                          
                          return (
                            <div
                              key={log.id}
                              style={{
                                padding: 'var(--spacing-md)',
                                margin: 0,
                                background: 'var(--bg-secondary)',
                                border: '1px solid var(--border-color)',
                                borderRadius: 'var(--border-radius)',
                                transition: 'all 0.2s ease'
                              }}
                              onMouseEnter={(e) => {
                                e.currentTarget.style.boxShadow = 'var(--shadow-sm)'
                                e.currentTarget.style.transform = 'translateY(-1px)'
                              }}
                              onMouseLeave={(e) => {
                                e.currentTarget.style.boxShadow = 'none'
                                e.currentTarget.style.transform = 'translateY(0)'
                              }}
                            >
                              <div style={{ 
                                display: 'flex', 
                                justifyContent: 'space-between', 
                                alignItems: 'flex-start',
                                marginBottom: 'var(--spacing-xs)'
                              }}>
                                <div style={{ flex: 1 }}>
                                  <div style={{ 
                                    fontWeight: '600', 
                                    color: 'var(--text-primary)',
                                    marginBottom: '0.25rem'
                                  }}>
                                    {log.exercise_type || 'Workout'}
                                  </div>
                                  {log.exercises && (
                                    <div style={{ 
                                      fontSize: '0.875rem', 
                                      color: 'var(--text-secondary)',
                                      marginTop: '0.25rem',
                                      whiteSpace: 'pre-wrap'
                                    }}>
                                      {log.exercises}
                                    </div>
                                  )}
                                </div>
                                <div style={{ 
                                  fontSize: '0.75rem', 
                                  color: 'var(--text-secondary)',
                                  textAlign: 'right',
                                  marginLeft: 'var(--spacing-md)'
                                }}>
                                  <div>{formattedDate}</div>
                                  <div>{formattedTime}</div>
                                  {log.duration_minutes && (
                                    <div style={{ marginTop: '0.25rem', fontWeight: '500' }}>
                                      {Math.round(log.duration_minutes)} min
                                    </div>
                                  )}
                                </div>
                              </div>
                              {log.notes && (
                                <div style={{ 
                                  fontSize: '0.875rem', 
                                  color: 'var(--text-secondary)',
                                  marginTop: 'var(--spacing-xs)',
                                  fontStyle: 'italic',
                                  paddingTop: 'var(--spacing-xs)',
                                  borderTop: '1px solid var(--border-color)'
                                }}>
                                  {log.notes}
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    ) : (
                      <div style={{ 
                        padding: 'var(--spacing-xl)', 
                        textAlign: 'center', 
                        color: 'var(--text-secondary)',
                        fontSize: '0.875rem'
                      }}>
                        No workouts logged yet. Your workouts will appear here once you complete them or when the agent logs them for you.
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Burger Menu */}
            <div style={{ position: 'relative' }}>
              <button
                onClick={() => setMenuOpen(!menuOpen)}
                style={{
                  padding: '0.5rem',
                  background: menuOpen ? 'rgba(255,255,255,0.3)' : 'rgba(255,255,255,0.2)',
                  color: 'white',
                  border: '1px solid rgba(255,255,255,0.4)',
                  borderRadius: 'var(--border-radius)',
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '4px',
                  width: '32px',
                  height: '32px',
                  justifyContent: 'center',
                  alignItems: 'center',
                  transition: 'all 0.2s ease'
                }}
                aria-label="Menu"
                onMouseEnter={(e) => {
                  if (!menuOpen) {
                    e.target.style.background = 'rgba(255,255,255,0.25)'
                  }
                }}
                onMouseLeave={(e) => {
                  if (!menuOpen) {
                    e.target.style.background = 'rgba(255,255,255,0.2)'
                  }
                }}
              >
                <span style={{ width: '20px', height: '2px', background: 'white', display: 'block' }}></span>
                <span style={{ width: '20px', height: '2px', background: 'white', display: 'block' }}></span>
                <span style={{ width: '20px', height: '2px', background: 'white', display: 'block' }}></span>
              </button>
            
            {menuOpen && (
              <div style={{
                position: 'absolute',
                top: '100%',
                right: 0,
                marginTop: '0.5rem',
                background: 'white',
                borderRadius: '4px',
                boxShadow: '0 4px 6px rgba(0,0,0,0.1)',
                minWidth: '180px',
                zIndex: 1000,
                overflow: 'hidden'
              }}>
                <button
                  onClick={() => {
                    router.push('/medical')
                    setMenuOpen(false)
                  }}
                  style={{
                    width: '100%',
                    padding: '0.75rem 1rem',
                    background: 'white',
                    color: '#333',
                    border: 'none',
                    textAlign: 'left',
                    cursor: 'pointer',
                    fontSize: '0.95rem'
                  }}
                  onMouseEnter={(e) => e.target.style.background = '#f5f5f5'}
                  onMouseLeave={(e) => e.target.style.background = 'white'}
                >
                  Medical History
                </button>
                <button
                  onClick={() => {
                    router.push('/preferences')
                    setMenuOpen(false)
                  }}
                  style={{
                    width: '100%',
                    padding: '0.75rem 1rem',
                    background: 'white',
                    color: '#333',
                    border: 'none',
                    textAlign: 'left',
                    cursor: 'pointer',
                    fontSize: '0.95rem',
                    borderTop: '1px solid #e0e0e0'
                  }}
                  onMouseEnter={(e) => e.target.style.background = '#f5f5f5'}
                  onMouseLeave={(e) => e.target.style.background = 'white'}
                >
                  User Preferences
                </button>
                <button
                  onClick={() => {
                    handleLogout()
                    setMenuOpen(false)
                  }}
                  style={{
                    width: '100%',
                    padding: '0.75rem 1rem',
                    background: 'white',
                    color: '#d32f2f',
                    border: 'none',
                    textAlign: 'left',
                    cursor: 'pointer',
                    fontSize: '0.95rem',
                    borderTop: '1px solid #e0e0e0'
                  }}
                  onMouseEnter={(e) => e.target.style.background = '#f5f5f5'}
                  onMouseLeave={(e) => e.target.style.background = 'white'}
                >
                  Logout
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
      </header>

      {/* Messages */}
      <div style={{ 
        flex: 1, 
        overflowY: 'auto', 
        padding: 'var(--spacing-lg)', 
        background: 'var(--bg-secondary)',
        maxWidth: '1200px',
        margin: '0 auto',
        width: '100%'
      }}>
        {messages.map((msg, idx) => (
          <div
            key={idx}
            style={{
              marginBottom: '1.25rem',
              display: 'flex',
              justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
              alignItems: 'flex-start'
            }}
          >
            <div
              style={{
                maxWidth: '75%',
                padding: 'var(--spacing-md) var(--spacing-lg)',
                borderRadius: msg.role === 'user' 
                  ? 'var(--border-radius-lg) var(--border-radius-lg) var(--border-radius-lg) 4px'
                  : 'var(--border-radius-lg) var(--border-radius-lg) 4px var(--border-radius-lg)',
                background: msg.role === 'user' 
                  ? 'linear-gradient(135deg, var(--primary-color) 0%, var(--primary-hover) 100%)'
                  : 'var(--bg-primary)',
                color: msg.role === 'user' ? 'var(--text-light)' : 'var(--text-primary)',
                boxShadow: msg.role === 'user' 
                  ? '0 2px 8px rgba(0, 112, 243, 0.2)'
                  : 'var(--shadow-sm)',
                wordWrap: 'break-word',
                border: msg.role === 'user' ? 'none' : '1px solid var(--border-color)'
              }}
            >
              {msg.role === 'user' ? (
                <div style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div>
              ) : (
                <div style={{
                  lineHeight: '1.6',
                  fontSize: '0.95rem'
                }}>
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      h1: ({node, ...props}) => <h1 style={{ fontSize: '1.5rem', marginTop: '1rem', marginBottom: '0.5rem', fontWeight: 'bold' }} {...props} />,
                      h2: ({node, ...props}) => <h2 style={{ fontSize: '1.3rem', marginTop: '0.8rem', marginBottom: '0.4rem', fontWeight: 'bold' }} {...props} />,
                      h3: ({node, ...props}) => <h3 style={{ fontSize: '1.1rem', marginTop: '0.6rem', marginBottom: '0.3rem', fontWeight: 'bold' }} {...props} />,
                      p: ({node, ...props}) => <p style={{ marginBottom: '0.75rem' }} {...props} />,
                      ul: ({node, ...props}) => <ul style={{ marginBottom: '0.75rem', paddingLeft: '1.5rem' }} {...props} />,
                      ol: ({node, ...props}) => <ol style={{ marginBottom: '0.75rem', paddingLeft: '1.5rem' }} {...props} />,
                      li: ({node, ...props}) => <li style={{ marginBottom: '0.25rem' }} {...props} />,
                      table: ({node, ...props}) => (
                        <table style={{
                          width: '100%',
                          borderCollapse: 'collapse',
                          marginTop: '0.75rem',
                          marginBottom: '0.75rem'
                        }} {...props} />
                      ),
                      thead: ({node, ...props}) => <thead style={{ background: '#f5f5f5' }} {...props} />,
                      tbody: ({node, ...props}) => <tbody {...props} />,
                      tr: ({node, ...props}) => <tr style={{ borderBottom: '1px solid #e0e0e0' }} {...props} />,
                      th: ({node, ...props}) => (
                        <th style={{
                          padding: '0.5rem',
                          textAlign: 'left',
                          fontWeight: 'bold',
                          border: '1px solid #e0e0e0'
                        }} {...props} />
                      ),
                      td: ({node, ...props}) => (
                        <td style={{
                          padding: '0.5rem',
                          border: '1px solid #e0e0e0'
                        }} {...props} />
                      ),
                      code: ({node, inline, ...props}) => (
                        <code style={{
                          background: inline ? '#f5f5f5' : 'transparent',
                          padding: inline ? '0.2rem 0.4rem' : '0',
                          borderRadius: '3px',
                          fontFamily: 'monospace',
                          fontSize: '0.9em'
                        }} {...props} />
                      ),
                      pre: ({node, ...props}) => (
                        <pre style={{
                          background: '#f5f5f5',
                          padding: '0.75rem',
                          borderRadius: '4px',
                          overflow: 'auto',
                          marginBottom: '0.75rem'
                        }} {...props} />
                      ),
                      strong: ({node, ...props}) => <strong style={{ fontWeight: 'bold' }} {...props} />,
                      em: ({node, ...props}) => <em style={{ fontStyle: 'italic' }} {...props} />,
                      hr: ({node, ...props}) => <hr style={{ border: 'none', borderTop: '1px solid #e0e0e0', margin: '1rem 0' }} {...props} />,
                      blockquote: ({node, ...props}) => (
                        <blockquote style={{
                          borderLeft: '3px solid #0070f3',
                          paddingLeft: '1rem',
                          marginLeft: '0',
                          marginBottom: '0.75rem',
                          color: '#666'
                        }} {...props} />
                      )
                    }}
                  >
                    {msg.content}
                  </ReactMarkdown>
                </div>
              )}
              {msg.warnings && msg.warnings.length > 0 && (
                <MedicalWarning 
                  warnings={msg.warnings}
                />
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: '1.25rem' }}>
            <div style={{ 
              padding: 'var(--spacing-md) var(--spacing-lg)', 
              background: 'var(--bg-primary)', 
              borderRadius: 'var(--border-radius-lg)', 
              boxShadow: 'var(--shadow-sm)',
              border: '1px solid var(--border-color)',
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--spacing-sm)'
            }}>
              <div style={{
                width: '12px',
                height: '12px',
                border: '2px solid var(--text-secondary)',
                borderTopColor: 'transparent',
                borderRadius: '50%',
                animation: 'spin 0.8s linear infinite'
              }}></div>
              <span style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Thinking...</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div style={{ 
        background: 'var(--bg-primary)', 
        borderTop: '1px solid var(--border-color)',
        boxShadow: '0 -2px 8px rgba(0,0,0,0.05)'
      }}>
        {error && (
          <div className="alert alert-error" style={{ margin: '0 var(--spacing-lg) var(--spacing-md) 0', borderRadius: 0 }}>
            {error}
          </div>
        )}
        <form onSubmit={handleSend} style={{ 
          padding: 'var(--spacing-lg)', 
          display: 'flex', 
          gap: 'var(--spacing-md)',
          maxWidth: '1200px',
          margin: '0 auto'
        }}>
          <input
            type="text"
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            placeholder="Ask me about workouts, exercises, or fitness advice..."
            disabled={loading}
            className="form-input"
            style={{ 
              flex: 1,
              padding: '0.875rem 1rem',
              fontSize: '0.95rem'
            }}
          />
          <button
            type="submit"
            disabled={loading || !inputMessage.trim()}
            className="btn btn-primary"
            style={{ 
              padding: '0.875rem 2rem',
              minWidth: '100px'
            }}
          >
            {loading ? 'Sending...' : 'Send'}
          </button>
        </form>
      </div>
    </div>
  )
}

