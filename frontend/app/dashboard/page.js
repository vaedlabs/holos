'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, removeToken, API_URL } from '@/lib/api'
import MedicalWarning from '@/components/MedicalWarning'
import { useRequireAuth } from '@/hooks/useAuth'

export default function DashboardPage() {
  const router = useRouter()
  const { mounted, isAuthenticated } = useRequireAuth()
  const [messages, setMessages] = useState([])
  const [inputMessage, setInputMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)
  const [workoutLogsOpen, setWorkoutLogsOpen] = useState(false)
  const [workoutLogs, setWorkoutLogs] = useState([])
  const [nutritionLogs, setNutritionLogs] = useState([])
  const [mentalFitnessLogs, setMentalFitnessLogs] = useState([])
  const [loadingLogs, setLoadingLogs] = useState(false)
  const [activeLogTab, setActiveLogTab] = useState('workouts') // 'workouts', 'nutrition', 'mental-fitness'
  const [selectedAgent, setSelectedAgent] = useState('coordinator')
  const [selectedImage, setSelectedImage] = useState(null)
  const [imagePreview, setImagePreview] = useState(null)
  const [fileInputKey, setFileInputKey] = useState(0) // Key to force file input remount
  const fileInputRef = useRef(null)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    if (!mounted || !isAuthenticated) return

    console.log('Token found, user authenticated')
    
    // Load conversation history
    const loadConversation = async () => {
      try {
        console.log('Loading conversation history...')
        const history = await api.getConversationHistory()
        console.log('Conversation history response:', history)
        console.log('Response type:', typeof history)
        console.log('Has messages property:', history && 'messages' in history)
        
        // Handle different response formats
        const messages = history?.messages || history || []
        console.log('Messages array:', messages)
        console.log('Messages length:', Array.isArray(messages) ? messages.length : 'Not an array')
        
        if (Array.isArray(messages) && messages.length > 0) {
          console.log(`Loaded ${messages.length} messages from history`)
          // Convert API messages to component format
          const loadedMessages = messages.map(msg => {
            const messageObj = {
              role: msg.role || 'assistant',
              content: msg.content || '',
              warnings: msg.warnings || null,
            }
            // If message has an image path, construct the image URL
            if (msg.image_path) {
              const imageUrl = `${API_URL}/uploads/${msg.image_path}`
              messageObj.imagePreview = imageUrl
            }
            return messageObj
          })
          console.log('Formatted messages:', loadedMessages)
          setMessages(loadedMessages)
        } else {
          console.log('No conversation history found, showing welcome message')
          // No history, add welcome message
          setMessages([{
            role: 'assistant',
            content: 'Hello! I\'m your Holos Coordinator. I can help you with fitness, nutrition, mental wellness, or create a holistic plan. How can I assist you today?'
          }])
        }
      } catch (err) {
        console.error('Error loading conversation:', err)
        console.error('Error details:', err.message, err.stack)
        // On error, start with welcome message
        setMessages([{
          role: 'assistant',
          content: 'Hello! I\'m your Physical Fitness Coach. How can I help you today?'
        }])
      }
    }
    
    loadConversation()
  }, [mounted, isAuthenticated])
  
  useEffect(() => {
    if (workoutLogsOpen) {
      loadAllLogs()
    }
  }, [workoutLogsOpen])

  const loadAllLogs = useCallback(async () => {
    setLoadingLogs(true)
    try {
      // Load all log types in parallel
      const [workoutData, nutritionData, mentalData] = await Promise.all([
        api.getWorkoutLogs(10, 0).catch(() => ({ logs: [] })),
        api.getNutritionLogs(10, 0).catch(() => ({ logs: [] })),
        api.getMentalFitnessLogs(10, 0).catch(() => ({ logs: [] }))
      ])
      setWorkoutLogs(workoutData.logs || [])
      setNutritionLogs(nutritionData.logs || [])
      setMentalFitnessLogs(mentalData.logs || [])
    } catch (err) {
      console.error('Error loading logs:', err)
    } finally {
      setLoadingLogs(false)
    }
  }, [])

  const handleWorkoutLogsClick = () => {
    setWorkoutLogsOpen(!workoutLogsOpen)
    if (!workoutLogsOpen) {
      loadAllLogs()
    }
  }
  
  useEffect(() => {
    if (workoutLogsOpen) {
      loadAllLogs()
    }
  }, [workoutLogsOpen, loadAllLogs])

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
      // Check if click is outside the logs modal - exclude the button and the modal itself
      if (workoutLogsOpen) {
        const logsButton = event.target.closest('[aria-label="Logs"]')
        const logsModal = event.target.closest('.workout-logs-modal')
        // Only close if click is outside both the button and the modal
        if (!logsButton && !logsModal) {
          setWorkoutLogsOpen(false)
        }
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [menuOpen, workoutLogsOpen])

  const handleSend = async (e) => {
    e.preventDefault()
    // Allow sending with just image (for Nutrition Agent) or with text
    if ((!inputMessage.trim() && !selectedImage) || loading) return

    // Convert image to base64 if present (before clearing state)
    let imageBase64 = null
    let imagePreviewUrl = null
    if (selectedImage && (selectedAgent === 'nutrition' || selectedAgent === 'coordinator')) {
      const reader = new FileReader()
      imageBase64 = await new Promise((resolve, reject) => {
        reader.onload = () => {
          // Keep the full data URL for display
          imagePreviewUrl = reader.result
          // Remove data:image/...;base64, prefix for API
          const base64String = reader.result.split(',')[1]
          resolve(base64String)
        }
        reader.onerror = reject
        reader.readAsDataURL(selectedImage)
      })
    }

    const userMessage = {
      role: 'user',
      content: inputMessage,
      imagePreview: imagePreviewUrl  // Store image preview for display
    }

    setMessages(prev => [...prev, userMessage])
    setInputMessage('')
    setLoading(true)
    setError('')

    // Clear image and reset file input after storing preview
    if (selectedImage) {
      setSelectedImage(null)
      setImagePreview(null)
      // Force file input to remount by changing key
      // This ensures the input is completely fresh and can accept new files
      setFileInputKey(prev => prev + 1)
    }

    try {
      // Upload image first if present
      let imagePath = null
      if (imageBase64) {
        try {
          const uploadResult = await api.uploadImage(imageBase64)
          imagePath = uploadResult.image_path
          console.log('Image uploaded, path:', imagePath)
        } catch (uploadErr) {
          console.warn('Failed to upload image:', uploadErr)
          // Continue without image path
        }
      }

      // Save user message to database (use placeholder if only image)
      const messageContent = inputMessage.trim() || (imagePreviewUrl ? 'Image uploaded' : '')
      try {
        await api.saveMessage('user', messageContent, null, imagePath)
      } catch (saveErr) {
        console.warn('Failed to save user message:', saveErr)
        // Continue even if save fails
      }

      const response = await api.chatWithAgent(inputMessage, selectedAgent, imageBase64)
      
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
          <h1 style={{ margin: 0, fontSize: '1.25rem' }}>
            Holos - {selectedAgent === 'physical-fitness' ? 'Physical Fitness' : 
                     selectedAgent === 'nutrition' ? 'Nutrition' : 
                     selectedAgent === 'mental-fitness' ? 'Mental Fitness' :
                     'Coordinator'} Coach
          </h1>
          <div style={{ display: 'flex', gap: 'var(--spacing-sm)', alignItems: 'center' }}>
            {/* Agent Selector */}
            <select
              value={selectedAgent}
              onChange={(e) => {
                setSelectedAgent(e.target.value)
                setSelectedImage(null)
                setImagePreview(null)
              }}
              style={{
                padding: '0.5rem 0.75rem',
                background: 'rgba(255,255,255,0.2)',
                color: 'white',
                border: '1px solid rgba(255,255,255,0.4)',
                borderRadius: 'var(--border-radius)',
                cursor: 'pointer',
                fontSize: '0.875rem',
                fontWeight: '500'
              }}
            >
              <option value="physical-fitness" style={{ color: '#000' }}>Physical Fitness</option>
              <option value="nutrition" style={{ color: '#000' }}>Nutrition</option>
              <option value="mental-fitness" style={{ color: '#000' }}>Mental Fitness</option>
              <option value="coordinator" style={{ color: '#000' }}>Coordinator (All-in-One)</option>
            </select>
            
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
                aria-label="Logs"
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
                Logs
              </button>
              
              {/* Logs Modal with Tabs */}
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
                    minWidth: '450px',
                    maxWidth: '550px',
                    maxHeight: '600px',
                    zIndex: 1000,
                    overflow: 'hidden',
                    display: 'flex',
                    flexDirection: 'column'
                  }}
                >
                  {/* Tabs */}
                  <div style={{
                    display: 'flex',
                    borderBottom: '1px solid var(--border-color)',
                    background: 'var(--bg-primary)'
                  }}>
                    {['workouts', 'nutrition', 'mental-fitness'].map((tab) => (
                      <button
                        key={tab}
                        onClick={(e) => {
                          e.stopPropagation() // Prevent event from bubbling up
                          setActiveLogTab(tab)
                        }}
                        style={{
                          flex: 1,
                          padding: 'var(--spacing-md)',
                          background: activeLogTab === tab ? 'white' : 'transparent',
                          border: 'none',
                          borderBottom: activeLogTab === tab ? '2px solid var(--primary-color)' : '2px solid transparent',
                          cursor: 'pointer',
                          fontSize: '0.875rem',
                          fontWeight: activeLogTab === tab ? '600' : '500',
                          color: activeLogTab === tab ? 'var(--primary-color)' : 'var(--text-secondary)',
                          transition: 'all 0.2s ease'
                        }}
                      >
                        {tab === 'workouts' ? 'Workouts' : tab === 'nutrition' ? 'Nutrition' : 'Mental'}
                      </button>
                    ))}
                  </div>
                  
                  {/* Tab Content */}
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
                        Loading {activeLogTab}...
                      </div>
                    ) : (
                      <>
                        {/* Workouts Tab */}
                        {activeLogTab === 'workouts' && (
                          workoutLogs.length > 0 ? (
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
                          )
                        )}

                        {/* Nutrition Tab */}
                        {activeLogTab === 'nutrition' && (
                          nutritionLogs.length > 0 ? (
                            <div style={{ 
                              display: 'flex', 
                              flexDirection: 'column', 
                              gap: 'var(--spacing-sm)'
                            }}>
                              {nutritionLogs.map((log) => {
                                const mealDate = new Date(log.meal_date)
                                const formattedDate = mealDate.toLocaleDateString('en-US', { 
                                  month: 'short', 
                                  day: 'numeric', 
                                  year: 'numeric' 
                                })
                                const formattedTime = mealDate.toLocaleTimeString('en-US', { 
                                  hour: 'numeric', 
                                  minute: '2-digit' 
                                })
                                
                                // Parse macros if it's a JSON string
                                let macros = null
                                try {
                                  macros = log.macros ? JSON.parse(log.macros) : null
                                } catch {
                                  macros = null
                                }
                                
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
                                          {log.meal_type ? log.meal_type.charAt(0).toUpperCase() + log.meal_type.slice(1) : 'Meal'}
                                        </div>
                                        {log.foods && (
                                          <div style={{ 
                                            fontSize: '0.875rem', 
                                            color: 'var(--text-secondary)',
                                            marginTop: '0.25rem'
                                          }}>
                                            {typeof log.foods === 'string' ? (log.foods.length > 100 ? log.foods.substring(0, 100) + '...' : log.foods) : 'Food logged'}
                                          </div>
                                        )}
                                        <div style={{ 
                                          display: 'flex', 
                                          gap: 'var(--spacing-md)',
                                          marginTop: '0.5rem',
                                          fontSize: '0.875rem'
                                        }}>
                                          {log.calories && (
                                            <span style={{ color: 'var(--text-primary)', fontWeight: '500' }}>
                                              {Math.round(log.calories)} cal
                                            </span>
                                          )}
                                          {macros && (
                                            <>
                                              {macros.protein && (
                                                <span style={{ color: 'var(--text-secondary)' }}>
                                                  P: {Math.round(macros.protein)}g
                                                </span>
                                              )}
                                              {macros.carbs && (
                                                <span style={{ color: 'var(--text-secondary)' }}>
                                                  C: {Math.round(macros.carbs)}g
                                                </span>
                                              )}
                                              {macros.fats && (
                                                <span style={{ color: 'var(--text-secondary)' }}>
                                                  F: {Math.round(macros.fats)}g
                                                </span>
                                              )}
                                            </>
                                          )}
                                        </div>
                                      </div>
                                      <div style={{ 
                                        fontSize: '0.75rem', 
                                        color: 'var(--text-secondary)',
                                        textAlign: 'right',
                                        marginLeft: 'var(--spacing-md)'
                                      }}>
                                        <div>{formattedDate}</div>
                                        <div>{formattedTime}</div>
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
                              No nutrition logs yet. Your meals will appear here once you log them or when the agent logs them for you.
                            </div>
                          )
                        )}

                        {/* Mental Fitness Tab */}
                        {activeLogTab === 'mental-fitness' && (
                          mentalFitnessLogs.length > 0 ? (
                            <div style={{ 
                              display: 'flex', 
                              flexDirection: 'column', 
                              gap: 'var(--spacing-sm)'
                            }}>
                              {mentalFitnessLogs.map((log) => {
                                const activityDate = new Date(log.activity_date)
                                const formattedDate = activityDate.toLocaleDateString('en-US', { 
                                  month: 'short', 
                                  day: 'numeric', 
                                  year: 'numeric' 
                                })
                                const formattedTime = activityDate.toLocaleTimeString('en-US', { 
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
                                          {log.activity_type ? log.activity_type.charAt(0).toUpperCase() + log.activity_type.slice(1) : 'Activity'}
                                        </div>
                                        <div style={{ 
                                          display: 'flex', 
                                          gap: 'var(--spacing-md)',
                                          marginTop: '0.5rem',
                                          fontSize: '0.875rem'
                                        }}>
                                          {log.duration_minutes && (
                                            <span style={{ color: 'var(--text-primary)', fontWeight: '500' }}>
                                              {Math.round(log.duration_minutes)} min
                                            </span>
                                          )}
                                          {log.mood_before && log.mood_after && (
                                            <span style={{ color: 'var(--text-secondary)' }}>
                                              Mood: {log.mood_before} → {log.mood_after}
                                            </span>
                                          )}
                                        </div>
                                      </div>
                                      <div style={{ 
                                        fontSize: '0.75rem', 
                                        color: 'var(--text-secondary)',
                                        textAlign: 'right',
                                        marginLeft: 'var(--spacing-md)'
                                      }}>
                                        <div>{formattedDate}</div>
                                        <div>{formattedTime}</div>
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
                              No mental fitness logs yet. Your activities will appear here once you log them or when the agent logs them for you.
                            </div>
                          )
                        )}
                      </>
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
                <div>
                  {/* Show image if present */}
                  {msg.imagePreview && (
                    <div style={{ marginBottom: '0.75rem' }}>
                      <img 
                        src={msg.imagePreview} 
                        alt="Uploaded food" 
                        style={{
                          maxWidth: '300px',
                          maxHeight: '300px',
                          borderRadius: 'var(--border-radius)',
                          objectFit: 'cover',
                          border: '1px solid rgba(255,255,255,0.2)'
                        }}
                      />
                    </div>
                  )}
                  <div style={{ whiteSpace: 'pre-wrap' }}>{msg.content || (msg.imagePreview ? '' : '')}</div>
                </div>
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
          flexDirection: 'column',
          gap: 'var(--spacing-md)',
          maxWidth: '1200px',
          margin: '0 auto'
        }}>
          {/* Image Preview (for Nutrition and Coordinator Agents) */}
          {imagePreview && (selectedAgent === 'nutrition' || selectedAgent === 'coordinator') && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--spacing-sm)',
              padding: 'var(--spacing-sm)',
              background: 'var(--bg-secondary)',
              borderRadius: 'var(--border-radius)',
              border: '1px solid var(--border-color)'
            }}>
              <img 
                src={imagePreview} 
                alt="Preview" 
                style={{
                  maxWidth: '100px',
                  maxHeight: '100px',
                  borderRadius: 'var(--border-radius)',
                  objectFit: 'cover'
                }}
              />
              <span style={{ flex: 1, fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                {selectedImage?.name || 'Image selected'}
              </span>
              <button
                type="button"
                onClick={() => {
                  setSelectedImage(null)
                  setImagePreview(null)
                }}
                style={{
                  padding: '0.25rem 0.5rem',
                  background: 'var(--error-color)',
                  color: 'white',
                  border: 'none',
                  borderRadius: 'var(--border-radius)',
                  cursor: 'pointer',
                  fontSize: '0.75rem'
                }}
              >
                Remove
              </button>
            </div>
          )}
          
          <div style={{ display: 'flex', gap: 'var(--spacing-md)', alignItems: 'flex-end' }}>
            {/* Image Upload (for Nutrition and Coordinator Agents) */}
            {(selectedAgent === 'nutrition' || selectedAgent === 'coordinator') && (
              <label
                style={{
                  padding: '0.75rem',
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--border-radius)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '44px',
                  height: '44px',
                  transition: 'all 0.2s ease'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'var(--bg-tertiary)'
                  e.currentTarget.style.borderColor = 'var(--primary-color)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'var(--bg-secondary)'
                  e.currentTarget.style.borderColor = 'var(--border-color)'
                }}
              >
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                  <circle cx="12" cy="13" r="4" />
                </svg>
                <input
                  key={fileInputKey}
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  onChange={(e) => {
                    const file = e.target.files?.[0]
                    if (file) {
                      setSelectedImage(file)
                      const reader = new FileReader()
                      reader.onload = (event) => {
                        setImagePreview(event.target.result)
                      }
                      reader.readAsDataURL(file)
                    } else {
                      // Reset if no file selected
                      setSelectedImage(null)
                      setImagePreview(null)
                    }
                  }}
                  onClick={(e) => {
                    // Reset value on click to allow selecting same file again
                    // This ensures onChange fires even if the same file is selected
                    e.currentTarget.value = ''
                  }}
                  style={{ display: 'none' }}
                  disabled={loading}
                />
              </label>
            )}
            
            <input
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              placeholder={
                selectedAgent === 'physical-fitness' 
                  ? 'Ask me about workouts, exercises, or fitness advice...'
                  : selectedAgent === 'nutrition'
                  ? 'Ask me about nutrition or upload a food image...'
                  : selectedAgent === 'mental-fitness'
                  ? 'Ask me about mental wellness...'
                  : 'Ask me anything - I\'ll route to the right expert or create a holistic plan...'
                  ? 'Ask about nutrition, meal planning, or upload a food image...'
                  : 'Ask about mindfulness, stress management, or mental wellness...'
              }
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
              disabled={loading || (!inputMessage.trim() && !selectedImage && !imagePreview)}
              style={{ 
                padding: '0.75rem',
                width: '44px',
                height: '44px',
                background: loading || (!inputMessage.trim() && !selectedImage && !imagePreview)
                  ? '#ccc'
                  : 'linear-gradient(135deg, var(--primary-color) 0%, var(--primary-hover) 100%)',
                border: 'none',
                borderRadius: 'var(--border-radius)',
                cursor: loading || (!inputMessage.trim() && !selectedImage && !imagePreview)
                  ? 'not-allowed'
                  : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'all 0.2s ease',
                boxShadow: loading || (!inputMessage.trim() && !selectedImage && !imagePreview)
                  ? 'none'
                  : 'var(--shadow-sm)',
                opacity: loading || (!inputMessage.trim() && !selectedImage && !imagePreview) ? 0.6 : 1
              }}
              onMouseEnter={(e) => {
                if (!loading && (inputMessage.trim() || selectedImage || imagePreview)) {
                  e.currentTarget.style.transform = 'translateY(-1px)'
                  e.currentTarget.style.boxShadow = 'var(--shadow-md)'
                }
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = 'translateY(0)'
                e.currentTarget.style.boxShadow = loading || (!inputMessage.trim() && !selectedImage && !imagePreview)
                  ? 'none'
                  : 'var(--shadow-sm)'
              }}
            >
              {loading ? (
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  style={{ animation: 'spin 1s linear infinite' }}
                >
                  <path d="M21 12a9 9 0 1 1-6.219-8.56" />
                </svg>
              ) : (
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="white"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <line x1="12" y1="19" x2="12" y2="5" />
                  <polyline points="5 12 12 5 19 12" />
                </svg>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

