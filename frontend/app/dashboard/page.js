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
  const [steps, setSteps] = useState([]) // Steps from coordinator agent
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
  const [expandedLogs, setExpandedLogs] = useState({}) // Track which logs are expanded
  const [visitedLinks, setVisitedLinks] = useState(() => {
    // Load visited links from localStorage on mount
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('visitedLinks')
      return stored ? JSON.parse(stored) : []
    }
    return []
  })

  // Track when a link is clicked
  const handleLinkClick = useCallback((url) => {
    if (!visitedLinks.includes(url)) {
      const updated = [...visitedLinks, url]
      setVisitedLinks(updated)
      if (typeof window !== 'undefined') {
        localStorage.setItem('visitedLinks', JSON.stringify(updated))
      }
    }
  }, [visitedLinks])

  useEffect(() => {
    if (!mounted || !isAuthenticated) return

    console.log('Token found, user authenticated')
    
    // Load conversation history
    const loadConversation = async () => {
      try {
        console.log('Loading conversation history for agent:', selectedAgent)
        const history = await api.getConversationHistory(selectedAgent)
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
  }, [mounted, isAuthenticated, selectedAgent])
  
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

  const handleDeleteLog = async (logId, logType) => {
    if (!confirm(`Are you sure you want to delete this ${logType} log?`)) {
      return
    }

    try {
      if (logType === 'workout') {
        await api.deleteWorkoutLog(logId)
        setWorkoutLogs(prev => prev.filter(log => log.id !== logId))
      } else if (logType === 'nutrition') {
        await api.deleteNutritionLog(logId)
        setNutritionLogs(prev => prev.filter(log => log.id !== logId))
      } else if (logType === 'mental-fitness') {
        await api.deleteMentalFitnessLog(logId)
        setMentalFitnessLogs(prev => prev.filter(log => log.id !== logId))
      }
    } catch (error) {
      console.error(`Error deleting ${logType} log:`, error)
      alert(`Failed to delete ${logType} log. Please try again.`)
    }
  }

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
    setSteps([]) // Reset steps

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
        await api.saveMessage('user', messageContent, null, imagePath, selectedAgent)
      } catch (saveErr) {
        console.warn('Failed to save user message:', saveErr)
        // Continue even if save fails
      }

      // Use streaming for coordinator agent, regular API for others
      if (selectedAgent === 'coordinator') {
        // Use streaming API for coordinator agent
        await api.chatWithCoordinatorAgentStream(
          inputMessage,
          imageBase64,
          // onStep callback - called when a step update arrives
          (stepText) => {
            setSteps(prev => {
              // Add new step if it's not already in the list
              if (!prev.includes(stepText)) {
                return [...prev, stepText]
              }
              return prev
            })
          },
          // onResponse callback - called when final response arrives
          async (response) => {
            const assistantMessage = {
              role: 'assistant',
              content: response.response,
              warnings: response.warnings
            }
            
            // Keep steps visible briefly before showing final response
            await new Promise(resolve => setTimeout(resolve, 800))
            
            setMessages(prev => [...prev, assistantMessage])
            
            // Save assistant message to database
            try {
              await api.saveMessage('assistant', response.response, response.warnings, null, selectedAgent)
            } catch (saveErr) {
              console.warn('Failed to save assistant message:', saveErr)
              // Continue even if save fails
            }
            
            // Clear steps after showing response
            setTimeout(() => setSteps([]), 500)
          },
          // onError callback
          (error) => {
            const errorMessage = error || 'Failed to get response from agent'
            setError(errorMessage)
            
            // If it's an auth error, redirect to login after showing error
            if (errorMessage.includes('Authentication failed') || errorMessage.includes('401') || errorMessage.includes('Not authenticated')) {
              setTimeout(() => {
                removeToken()
                router.push('/login')
              }, 2000)
            }
            
            // Remove the user message if there was an error
            setMessages(prev => prev.slice(0, -1))
            setSteps([])
          }
        )
      } else {
        // Use regular API for non-coordinator agents
        const response = await api.chatWithAgent(inputMessage, selectedAgent, imageBase64)
        
        const assistantMessage = {
          role: 'assistant',
          content: response.response,
          warnings: response.warnings
        }
        
        setMessages(prev => [...prev, assistantMessage])
        
        // Save assistant message to database
        try {
          await api.saveMessage('assistant', response.response, response.warnings, null, selectedAgent)
        } catch (saveErr) {
          console.warn('Failed to save assistant message:', saveErr)
          // Continue even if save fails
        }
      }
    } catch (err) {
      console.error('Chat error:', err)
      const errorMessage = err.message || 'Failed to get response from agent'
      setError(errorMessage)
      
      // If it's an auth error, redirect to login after showing error
      if (errorMessage.includes('Authentication failed') || errorMessage.includes('401') || errorMessage.includes('Not authenticated')) {
        setTimeout(() => {
          removeToken()
          router.push('/login')
        }, 2000) // Give user time to see the error
      }
      
      // Remove the user message if there was an error
      setMessages(prev => prev.slice(0, -1))
      setSteps([]) // Clear steps on error
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
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'linear-gradient(180deg, #0a0e27 0%, #1a1f3a 30%, #1e3a8a 60%, #0f172a 100%)' }}>
      {/* SVG Filter for Liquid Glass Effect */}
      <svg width="0" height="0" style={{ position: 'absolute' }}>
        <defs>
          <filter id="glass-distortion" x="0%" y="0%" width="100%" height="100%">
            <feTurbulence 
              type="fractalNoise" 
              baseFrequency="0.008 0.008"
              numOctaves="2" 
              seed="92" 
              result="noise" 
            />
            <feGaussianBlur 
              in="noise" 
              stdDeviation="2" 
              result="blurred" 
            />
            <feDisplacementMap 
              in="SourceGraphic" 
              in2="blurred" 
              scale="150"
              xChannelSelector="R" 
              yChannelSelector="G" 
            />
          </filter>
        </defs>
      </svg>
      {/* Header */}
      <header className="header">
        <div className="header-content">
          <h1 style={{ margin: 0, fontSize: '1.25rem', color: 'var(--text-light)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
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
                fontSize: '1rem',
                fontWeight: '500',
                height: '44px',
                display: 'flex',
                alignItems: 'center'
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
                  fontSize: '1rem',
                  fontWeight: '500',
                  whiteSpace: 'nowrap',
                  transition: 'all 0.2s ease',
                  height: '44px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
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
                  className="workout-logs-modal glassmorphism"
                  style={{
                    position: 'absolute',
                    top: '100%',
                    right: 0,
                    marginTop: '0.5rem',
                    minWidth: '450px',
                    maxWidth: '550px',
                    maxHeight: '600px',
                    zIndex: 1000,
                    overflow: 'hidden',
                    display: 'flex',
                    flexDirection: 'column',
                    backdropFilter: 'blur(50px) saturate(180%)',
                    WebkitBackdropFilter: 'blur(50px) saturate(180%)',
                    background: 'rgba(15, 23, 42, 0.9)'
                  }}
                >
                  {/* Tabs */}
                  <div style={{
                    display: 'flex',
                    borderBottom: '1px solid rgba(82, 82, 82, 0.2)',
                    background: 'transparent'
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
                          background: activeLogTab === tab 
                            ? 'rgba(255, 255, 255, 0.15)' 
                            : 'transparent',
                          backdropFilter: activeLogTab === tab ? 'blur(10px) saturate(150%)' : 'none',
                          WebkitBackdropFilter: activeLogTab === tab ? 'blur(10px) saturate(150%)' : 'none',
                          border: 'none',
                          borderBottom: activeLogTab === tab 
                            ? '2px solid var(--primary-color)' 
                            : '2px solid transparent',
                          cursor: 'pointer',
                          fontSize: '0.875rem',
                          fontWeight: activeLogTab === tab ? '600' : '500',
                          color: activeLogTab === tab 
                            ? 'var(--text-light)' 
                            : 'rgba(255, 255, 255, 0.85)',
                          transition: 'all 0.2s ease',
                          textShadow: '0 1px 3px rgba(0, 0, 0, 0.5)',
                          borderRadius: activeLogTab === tab ? '8px 8px 0 0' : '0'
                        }}
                        onMouseEnter={(e) => {
                          if (activeLogTab !== tab) {
                            e.target.style.background = 'rgba(255, 255, 255, 0.08)'
                            e.target.style.color = 'rgba(255, 255, 255, 0.95)'
                          }
                        }}
                        onMouseLeave={(e) => {
                          if (activeLogTab !== tab) {
                            e.target.style.background = 'transparent'
                            e.target.style.color = 'rgba(255, 255, 255, 0.85)'
                          }
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
                        color: 'rgba(255, 255, 255, 0.9)',
                        fontSize: '0.875rem',
                        textShadow: '0 1px 3px rgba(0, 0, 0, 0.5)'
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
                                    className="glassmorphism"
                                    style={{
                                      padding: 'var(--spacing-md)',
                                      margin: 0,
                                      transition: 'all 0.2s ease',
                                      position: 'relative'
                                    }}
                                    onMouseEnter={(e) => {
                                      e.currentTarget.style.transform = 'translateY(-1px)'
                                    }}
                                    onMouseLeave={(e) => {
                                      e.currentTarget.style.transform = 'translateY(0)'
                                    }}
                                  >
                                    <div style={{ 
                                      display: 'flex', 
                                      justifyContent: 'space-between', 
                                      alignItems: 'flex-start',
                                      marginBottom: 'var(--spacing-xs)',
                                      paddingRight: '32px' // Space for delete button
                                    }}>
                                      <div style={{ flex: 1 }}>
                                        <div style={{ 
                                          fontWeight: '600', 
                                          color: 'var(--text-light)',
                                          marginBottom: '0.25rem',
                                          textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)'
                                        }}>
                                          {log.exercise_type || 'Workout'}
                                        </div>
                                        {log.exercises && (
                                          <div style={{ 
                                            fontSize: '0.875rem', 
                                            color: 'rgba(255, 255, 255, 0.8)',
                                            marginTop: '0.25rem',
                                            whiteSpace: 'pre-wrap',
                                            textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)'
                                          }}>
                                            {log.exercises}
                                          </div>
                                        )}
                                      </div>
                                      <div style={{ 
                                        fontSize: '0.75rem', 
                                        color: 'rgba(255, 255, 255, 0.7)',
                                        textAlign: 'right',
                                        marginLeft: 'var(--spacing-md)',
                                        textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)'
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
                                        color: 'rgba(255, 255, 255, 0.7)',
                                        marginTop: 'var(--spacing-xs)',
                                        fontStyle: 'italic',
                                        paddingTop: 'var(--spacing-xs)',
                                        borderTop: '1px solid rgba(82, 82, 82, 0.2)',
                                        textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)',
                                        paddingRight: '32px',
                                        position: 'relative'
                                      }}>
                                        {log.notes}
                                        {/* Delete button - aligned with notes text */}
                                        <button
                                          onClick={() => handleDeleteLog(log.id, 'workout')}
                                          style={{
                                            position: 'absolute',
                                            right: 0,
                                            top: 'var(--spacing-xs)',
                                            background: 'rgba(255, 255, 255, 0.05)',
                                            border: '1px solid rgba(82, 82, 82, 0.2)',
                                            borderRadius: '50%',
                                            width: '24px',
                                            height: '24px',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            cursor: 'pointer',
                                            color: 'rgba(255, 255, 255, 0.5)',
                                            fontSize: '0.875rem',
                                            fontWeight: 'bold',
                                            transition: 'all 0.2s ease',
                                            padding: 0,
                                            lineHeight: '1'
                                          }}
                                          onMouseEnter={(e) => {
                                            e.target.style.background = 'rgba(220, 53, 69, 0.3)'
                                            e.target.style.borderColor = 'rgba(220, 53, 69, 0.6)'
                                            e.target.style.color = '#dc3545'
                                          }}
                                          onMouseLeave={(e) => {
                                            e.target.style.background = 'rgba(255, 255, 255, 0.05)'
                                            e.target.style.borderColor = 'rgba(82, 82, 82, 0.2)'
                                            e.target.style.color = 'rgba(255, 255, 255, 0.5)'
                                          }}
                                          title="Delete log"
                                        >
                                          ×
                                        </button>
                                      </div>
                                    )}
                                    {!log.notes && (
                                      <div style={{ position: 'relative', height: '0.875rem' }}>
                                        {/* Delete button - when no notes, position at bottom */}
                                        <button
                                          onClick={() => handleDeleteLog(log.id, 'workout')}
                                          style={{
                                            position: 'absolute',
                                            right: 'var(--spacing-xs)',
                                            bottom: 0,
                                            background: 'rgba(255, 255, 255, 0.05)',
                                            border: '1px solid rgba(82, 82, 82, 0.2)',
                                            borderRadius: '50%',
                                            width: '24px',
                                            height: '24px',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            cursor: 'pointer',
                                            color: 'rgba(255, 255, 255, 0.5)',
                                            fontSize: '0.875rem',
                                            fontWeight: 'bold',
                                            transition: 'all 0.2s ease',
                                            padding: 0,
                                            lineHeight: '1'
                                          }}
                                          onMouseEnter={(e) => {
                                            e.target.style.background = 'rgba(220, 53, 69, 0.3)'
                                            e.target.style.borderColor = 'rgba(220, 53, 69, 0.6)'
                                            e.target.style.color = '#dc3545'
                                          }}
                                          onMouseLeave={(e) => {
                                            e.target.style.background = 'rgba(255, 255, 255, 0.05)'
                                            e.target.style.borderColor = 'rgba(82, 82, 82, 0.2)'
                                            e.target.style.color = 'rgba(255, 255, 255, 0.5)'
                                          }}
                                          title="Delete log"
                                        >
                                          ×
                                        </button>
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
                              color: 'rgba(255, 255, 255, 0.95)',
                              fontSize: '0.875rem',
                              textShadow: '0 1px 3px rgba(0, 0, 0, 0.5)'
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
                                
                                // Parse foods to get dish name
                                let dishName = null
                                try {
                                    if (log.foods) {
                                        if (typeof log.foods === 'string') {
                                            // Try to parse as JSON first
                                            try {
                                                const parsed = JSON.parse(log.foods)
                                                if (typeof parsed === 'object' && parsed !== null) {
                                                    // Check if it's structured data with dish_name
                                                    if (parsed.dish_name) {
                                                        dishName = parsed.dish_name
                                                    } else if (Array.isArray(parsed)) {
                                                        // It's an array, use first item or join
                                                        dishName = parsed.length > 0 ? parsed[0] : null
                                                    } else {
                                                        // It's an object, try to get a meaningful name
                                                        const values = Object.values(parsed).filter(v => v && typeof v === 'string')
                                                        dishName = values.length > 0 ? values[0] : null
                                                    }
                                                } else {
                                                    dishName = String(parsed)
                                                }
                                            } catch {
                                                // Not JSON, treat as plain text - extract first meaningful part
                                                const text = log.foods.trim()
                                                // Try to get first line or first 50 chars
                                                const firstLine = text.split('\n')[0].trim()
                                                dishName = firstLine.length > 0 && firstLine.length < 100 ? firstLine : (text.length > 100 ? text.substring(0, 100) + '...' : text)
                                            }
                                        } else if (Array.isArray(log.foods)) {
                                            dishName = log.foods.length > 0 ? log.foods[0] : null
                                        } else {
                                            dishName = String(log.foods)
                                        }
                                    }
                                } catch {
                                    dishName = 'Meal'
                                }
                                
                                // Fallback: if no dish name, try to use first item from items array
                                if (!dishName || dishName === 'Food logged' || dishName === 'Meal' || dishName === 'null') {
                                    // Try to get from items if available
                                    try {
                                        if (log.foods && typeof log.foods === 'string') {
                                            const parsed = JSON.parse(log.foods)
                                            if (parsed && parsed.items && Array.isArray(parsed.items) && parsed.items.length > 0) {
                                                dishName = parsed.items[0]
                                            }
                                        }
                                    } catch {
                                        // Ignore parsing errors
                                    }
                                    
                                    // Final fallback to meal type
                                    if (!dishName || dishName === 'Food logged' || dishName === 'Meal' || dishName === 'null') {
                                        dishName = log.meal_type ? log.meal_type.charAt(0).toUpperCase() + log.meal_type.slice(1) : 'Meal'
                                    }
                                }
                                
                                return (
                                  <div
                                    key={log.id}
                                    className="glassmorphism"
                                    style={{
                                      padding: 'var(--spacing-md)',
                                      margin: 0,
                                      transition: 'all 0.2s ease',
                                      position: 'relative'
                                    }}
                                    onMouseEnter={(e) => {
                                      e.currentTarget.style.transform = 'translateY(-1px)'
                                    }}
                                    onMouseLeave={(e) => {
                                      e.currentTarget.style.transform = 'translateY(0)'
                                    }}
                                  >
                                    <div style={{ 
                                      display: 'flex', 
                                      justifyContent: 'space-between', 
                                      alignItems: 'flex-start',
                                      paddingRight: '32px' // Space for delete button
                                    }}>
                                      <div style={{ flex: 1 }}>
                                        {/* Dish Name */}
                                        {dishName && (
                                          <div style={{ 
                                            fontWeight: '600', 
                                            color: 'var(--text-light)',
                                            marginBottom: '0.5rem',
                                            fontSize: '0.95rem',
                                            textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)'
                                          }}>
                                            {dishName}
                                          </div>
                                        )}
                                        
                                        {/* Calories and Macros in one line */}
                                        <div style={{ 
                                          display: 'flex', 
                                          gap: 'var(--spacing-md)',
                                          fontSize: '0.875rem',
                                          flexWrap: 'wrap',
                                          alignItems: 'center'
                                        }}>
                                          {log.calories && (
                                            <span style={{ color: 'var(--text-light)', fontWeight: '500', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                                              {Math.round(log.calories)} cal
                                            </span>
                                          )}
                                          {macros && macros.protein && (
                                            <span style={{ color: 'rgba(255, 255, 255, 0.7)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                                              P: {Math.round(macros.protein)}g
                                            </span>
                                          )}
                                          {macros && macros.carbs && (
                                            <span style={{ color: 'rgba(255, 255, 255, 0.7)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                                              C: {Math.round(macros.carbs)}g
                                            </span>
                                          )}
                                          {macros && macros.fats && (
                                            <span style={{ color: 'rgba(255, 255, 255, 0.7)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                                              F: {Math.round(macros.fats)}g
                                            </span>
                                          )}
                                        </div>
                                      </div>
                                      <div style={{ 
                                        fontSize: '0.75rem', 
                                        color: 'rgba(255, 255, 255, 0.7)',
                                        textAlign: 'right',
                                        marginLeft: 'var(--spacing-md)',
                                        textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)'
                                      }}>
                                        <div style={{ 
                                          fontWeight: '600', 
                                          color: 'var(--text-light)',
                                          marginBottom: '0.25rem',
                                          fontSize: '0.875rem',
                                          textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)'
                                        }}>
                                          {log.meal_type ? log.meal_type.charAt(0).toUpperCase() + log.meal_type.slice(1) : 'Meal'}
                                        </div>
                                        <div>{formattedDate}</div>
                                        <div>{formattedTime}</div>
                                      </div>
                                    </div>
                                    {log.notes && (
                                      <div style={{ 
                                        fontSize: '0.875rem', 
                                        color: 'rgba(255, 255, 255, 0.7)',
                                        marginTop: 'var(--spacing-sm)',
                                        fontStyle: 'italic',
                                        paddingTop: 'var(--spacing-sm)',
                                        borderTop: '1px solid rgba(82, 82, 82, 0.2)',
                                        textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)',
                                        paddingRight: '32px',
                                        position: 'relative'
                                      }}>
                                        {log.notes}
                                        {/* Delete button - aligned with notes text */}
                                        <button
                                          onClick={() => handleDeleteLog(log.id, 'nutrition')}
                                          style={{
                                            position: 'absolute',
                                            right: 0,
                                            top: 'var(--spacing-sm)',
                                            background: 'rgba(255, 255, 255, 0.05)',
                                            border: '1px solid rgba(82, 82, 82, 0.2)',
                                            borderRadius: '50%',
                                            width: '24px',
                                            height: '24px',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            cursor: 'pointer',
                                            color: 'rgba(255, 255, 255, 0.5)',
                                            fontSize: '0.875rem',
                                            fontWeight: 'bold',
                                            transition: 'all 0.2s ease',
                                            padding: 0,
                                            lineHeight: '1'
                                          }}
                                          onMouseEnter={(e) => {
                                            e.target.style.background = 'rgba(220, 53, 69, 0.3)'
                                            e.target.style.borderColor = 'rgba(220, 53, 69, 0.6)'
                                            e.target.style.color = '#dc3545'
                                          }}
                                          onMouseLeave={(e) => {
                                            e.target.style.background = 'rgba(255, 255, 255, 0.05)'
                                            e.target.style.borderColor = 'rgba(82, 82, 82, 0.2)'
                                            e.target.style.color = 'rgba(255, 255, 255, 0.5)'
                                          }}
                                          title="Delete log"
                                        >
                                          ×
                                        </button>
                                      </div>
                                    )}
                                    {!log.notes && (
                                      <div style={{ position: 'relative', height: '0.875rem' }}>
                                        {/* Delete button - when no notes, position at bottom */}
                                        <button
                                          onClick={() => handleDeleteLog(log.id, 'nutrition')}
                                          style={{
                                            position: 'absolute',
                                            right: 'var(--spacing-xs)',
                                            bottom: 0,
                                            background: 'rgba(255, 255, 255, 0.05)',
                                            border: '1px solid rgba(82, 82, 82, 0.2)',
                                            borderRadius: '50%',
                                            width: '24px',
                                            height: '24px',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            cursor: 'pointer',
                                            color: 'rgba(255, 255, 255, 0.5)',
                                            fontSize: '0.875rem',
                                            fontWeight: 'bold',
                                            transition: 'all 0.2s ease',
                                            padding: 0,
                                            lineHeight: '1'
                                          }}
                                          onMouseEnter={(e) => {
                                            e.target.style.background = 'rgba(220, 53, 69, 0.3)'
                                            e.target.style.borderColor = 'rgba(220, 53, 69, 0.6)'
                                            e.target.style.color = '#dc3545'
                                          }}
                                          onMouseLeave={(e) => {
                                            e.target.style.background = 'rgba(255, 255, 255, 0.05)'
                                            e.target.style.borderColor = 'rgba(82, 82, 82, 0.2)'
                                            e.target.style.color = 'rgba(255, 255, 255, 0.5)'
                                          }}
                                          title="Delete log"
                                        >
                                          ×
                                        </button>
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
                              color: 'rgba(255, 255, 255, 0.95)',
                              fontSize: '0.875rem',
                              textShadow: '0 1px 3px rgba(0, 0, 0, 0.5)'
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
                                    className="glassmorphism"
                                    style={{
                                      padding: 'var(--spacing-md)',
                                      margin: 0,
                                      transition: 'all 0.2s ease',
                                      position: 'relative'
                                    }}
                                    onMouseEnter={(e) => {
                                      e.currentTarget.style.transform = 'translateY(-1px)'
                                    }}
                                    onMouseLeave={(e) => {
                                      e.currentTarget.style.transform = 'translateY(0)'
                                    }}
                                  >
                                    {/* Delete button */}
                                    <button
                                      onClick={() => handleDeleteLog(log.id, 'mental-fitness')}
                                      style={{
                                        position: 'absolute',
                                        bottom: 'var(--spacing-xs)',
                                        right: 'var(--spacing-xs)',
                                        background: 'rgba(255, 255, 255, 0.05)',
                                        border: '1px solid rgba(82, 82, 82, 0.2)',
                                        borderRadius: '50%',
                                        width: '24px',
                                        height: '24px',
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        cursor: 'pointer',
                                        color: 'rgba(255, 255, 255, 0.5)',
                                        fontSize: '0.875rem',
                                        fontWeight: 'bold',
                                        transition: 'all 0.2s ease',
                                        padding: 0,
                                        lineHeight: '1'
                                      }}
                                      onMouseEnter={(e) => {
                                        e.target.style.background = 'rgba(220, 53, 69, 0.3)'
                                        e.target.style.borderColor = 'rgba(220, 53, 69, 0.6)'
                                        e.target.style.color = '#dc3545'
                                      }}
                                      onMouseLeave={(e) => {
                                        e.target.style.background = 'rgba(255, 255, 255, 0.05)'
                                        e.target.style.borderColor = 'rgba(82, 82, 82, 0.2)'
                                        e.target.style.color = 'rgba(255, 255, 255, 0.5)'
                                      }}
                                      title="Delete log"
                                    >
                                      ×
                                    </button>
                                    <div style={{ 
                                      display: 'flex', 
                                      justifyContent: 'space-between', 
                                      alignItems: 'flex-start',
                                      marginBottom: 'var(--spacing-xs)',
                                      paddingRight: '32px' // Space for delete button
                                    }}>
                                      <div style={{ flex: 1 }}>
                                        <div style={{ 
                                          fontWeight: '600', 
                                          color: 'var(--text-light)',
                                          marginBottom: '0.25rem',
                                          textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)'
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
                                            <span style={{ color: 'var(--text-light)', fontWeight: '500', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                                              {Math.round(log.duration_minutes)} min
                                            </span>
                                          )}
                                          {log.mood_before && log.mood_after && (
                                            <span style={{ color: 'rgba(255, 255, 255, 0.7)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                                              Mood: {log.mood_before} → {log.mood_after}
                                            </span>
                                          )}
                                        </div>
                                      </div>
                                      <div style={{ 
                                        fontSize: '0.75rem', 
                                        color: 'rgba(255, 255, 255, 0.7)',
                                        textAlign: 'right',
                                        marginLeft: 'var(--spacing-md)',
                                        textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)'
                                      }}>
                                        <div>{formattedDate}</div>
                                        <div>{formattedTime}</div>
                                      </div>
                                    </div>
                                    {log.notes && (
                                      <div style={{ 
                                        fontSize: '0.875rem', 
                                        color: 'rgba(255, 255, 255, 0.7)',
                                        marginTop: 'var(--spacing-xs)',
                                        fontStyle: 'italic',
                                        paddingTop: 'var(--spacing-xs)',
                                        borderTop: '1px solid rgba(82, 82, 82, 0.2)',
                                        textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)',
                                        paddingRight: '32px' // Space for delete button
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
                              color: 'rgba(255, 255, 255, 0.95)',
                              fontSize: '0.875rem',
                              textShadow: '0 1px 3px rgba(0, 0, 0, 0.5)'
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
                  width: '44px',
                  height: '44px',
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
              <div className="glassmorphism" style={{
                position: 'absolute',
                top: '100%',
                right: 0,
                marginTop: '0.5rem',
                minWidth: '180px',
                zIndex: 1000,
                overflow: 'hidden',
                backdropFilter: 'blur(50px) saturate(180%)',
                WebkitBackdropFilter: 'blur(50px) saturate(180%)',
                background: 'rgba(15, 23, 42, 0.9)'
              }}>
                <button
                  onClick={() => {
                    router.push('/medical')
                    setMenuOpen(false)
                  }}
                  style={{
                    width: '100%',
                    padding: '0.75rem 1rem',
                    background: 'transparent',
                    color: 'var(--text-light)',
                    border: 'none',
                    textAlign: 'left',
                    cursor: 'pointer',
                    fontSize: '0.95rem',
                    fontWeight: '500',
                    textShadow: '0 1px 3px rgba(0, 0, 0, 0.5)',
                    transition: 'all 0.2s ease'
                  }}
                  onMouseEnter={(e) => {
                    e.target.style.background = 'rgba(255, 255, 255, 0.12)'
                    e.target.style.backdropFilter = 'blur(10px) saturate(150%)'
                    e.target.style.WebkitBackdropFilter = 'blur(10px) saturate(150%)'
                  }}
                  onMouseLeave={(e) => {
                    e.target.style.background = 'transparent'
                    e.target.style.backdropFilter = 'none'
                    e.target.style.WebkitBackdropFilter = 'none'
                  }}
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
                    background: 'transparent',
                    color: 'var(--text-light)',
                    border: 'none',
                    textAlign: 'left',
                    cursor: 'pointer',
                    fontSize: '0.95rem',
                    fontWeight: '500',
                    borderTop: '1px solid rgba(82, 82, 82, 0.2)',
                    textShadow: '0 1px 3px rgba(0, 0, 0, 0.5)',
                    transition: 'all 0.2s ease'
                  }}
                  onMouseEnter={(e) => {
                    e.target.style.background = 'rgba(255, 255, 255, 0.12)'
                    e.target.style.backdropFilter = 'blur(10px) saturate(150%)'
                    e.target.style.WebkitBackdropFilter = 'blur(10px) saturate(150%)'
                  }}
                  onMouseLeave={(e) => {
                    e.target.style.background = 'transparent'
                    e.target.style.backdropFilter = 'none'
                    e.target.style.WebkitBackdropFilter = 'none'
                  }}
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
                    background: 'transparent',
                    color: '#ff4444',
                    border: 'none',
                    textAlign: 'left',
                    cursor: 'pointer',
                    fontSize: '0.95rem',
                    fontWeight: '500',
                    borderTop: '1px solid rgba(82, 82, 82, 0.2)',
                    textShadow: '0 1px 3px rgba(0, 0, 0, 0.5)',
                    transition: 'all 0.2s ease'
                  }}
                  onMouseEnter={(e) => {
                    e.target.style.background = 'rgba(255, 68, 68, 0.15)'
                    e.target.style.backdropFilter = 'blur(10px) saturate(150%)'
                    e.target.style.WebkitBackdropFilter = 'blur(10px) saturate(150%)'
                  }}
                  onMouseLeave={(e) => {
                    e.target.style.background = 'transparent'
                    e.target.style.backdropFilter = 'none'
                    e.target.style.WebkitBackdropFilter = 'none'
                  }}
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
        background: 'transparent',
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
              className={msg.role === 'assistant' ? 'liquid-glass-card' : ''}
              style={{
                maxWidth: '75%',
                padding: msg.role === 'assistant' ? 'var(--spacing-md) var(--spacing-lg)' : 'var(--spacing-md) var(--spacing-lg)',
                borderRadius: msg.role === 'user' 
                  ? 'var(--border-radius-lg) var(--border-radius-lg) var(--border-radius-lg) 4px'
                  : '28px',
                background: msg.role === 'user' 
                  ? 'linear-gradient(135deg, var(--primary-color) 0%, var(--primary-hover) 100%)'
                  : 'rgba(255, 255, 255, 0.05)',
                color: msg.role === 'user' ? 'var(--text-light)' : 'var(--text-light)',
                boxShadow: msg.role === 'user' 
                  ? '0 2px 8px rgba(0, 112, 243, 0.2)'
                  : undefined,
                wordWrap: 'break-word',
                border: msg.role === 'user' ? 'none' : undefined,
                textShadow: msg.role === 'assistant' ? '0 1px 2px rgba(0, 0, 0, 0.3)' : undefined
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
                <div>
                  {/* Show medical warnings at the TOP for assistant messages */}
                  {msg.warnings && msg.warnings.length > 0 && (
                    <div style={{ marginBottom: 'var(--spacing-md)' }}>
                      <MedicalWarning 
                        warnings={msg.warnings}
                      />
                    </div>
                  )}
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
                        thead: ({node, ...props}) => <thead style={{ background: 'rgba(255, 255, 255, 0.1)' }} {...props} />,
                        tbody: ({node, ...props}) => <tbody {...props} />,
                        tr: ({node, ...props}) => <tr style={{ borderBottom: '1px solid rgba(82, 82, 82, 0.2)' }} {...props} />,
                        th: ({node, ...props}) => (
                          <th style={{
                            padding: '0.5rem',
                            textAlign: 'left',
                            fontWeight: 'bold',
                            border: '1px solid rgba(82, 82, 82, 0.2)',
                            color: 'var(--text-light)',
                            textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)'
                          }} {...props} />
                        ),
                        td: ({node, ...props}) => (
                          <td style={{
                            padding: '0.5rem',
                            border: '1px solid rgba(82, 82, 82, 0.2)',
                            color: 'var(--text-light)',
                            textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)'
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
                        ),
                        a: ({node, href, ...props}) => {
                          const isVisited = visitedLinks.includes(href)
                          return (
                            <a
                              href={href}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={() => handleLinkClick(href)}
                              style={{
                                color: isVisited ? '#BA55D3' : '#00FF00', // Medium orchid purple for visited, green for unvisited
                                textDecoration: 'underline',
                                fontWeight: '500',
                                transition: 'color 0.2s ease',
                                cursor: 'pointer'
                              }}
                              {...props}
                            />
                          )
                        }
                      }}
                    >
                      {msg.content}
                    </ReactMarkdown>
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: '1.25rem' }}>
            <div className="glassmorphism" style={{ 
              padding: 'var(--spacing-md) var(--spacing-lg)', 
              display: 'flex',
              flexDirection: 'column',
              gap: 'var(--spacing-sm)',
              minWidth: '200px'
            }}>
              {(() => {
                // Filter and validate steps
                const validSteps = steps
                  .map(step => {
                    if (!step) return null
                    const stepText = typeof step === 'string' ? step.trim() : String(step).trim()
                    return stepText.length > 0 ? stepText : null
                  })
                  .filter(Boolean)
                
                return validSteps.length > 0 ? (
                  // Show steps if available (coordinator agent)
                  validSteps.map((stepText, index) => (
                    <div key={index} style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 'var(--spacing-sm)'
                    }}>
                      <div style={{
                        width: '8px',
                        height: '8px',
                        borderRadius: '50%',
                        background: index === validSteps.length - 1 
                          ? 'rgba(59, 130, 246, 0.8)' 
                          : 'rgba(34, 197, 94, 0.8)',
                        flexShrink: 0,
                        boxShadow: index === validSteps.length - 1 
                          ? '0 0 8px rgba(59, 130, 246, 0.5)' 
                          : 'none'
                      }}></div>
                      <span style={{ 
                        color: index === validSteps.length - 1 
                          ? 'rgba(255, 255, 255, 0.95)' 
                          : 'rgba(255, 255, 255, 0.7)', 
                        fontSize: '0.9rem', 
                        textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)',
                        fontWeight: index === validSteps.length - 1 ? '500' : '400'
                      }}>
                        {index === validSteps.length - 1 ? '→ ' : '✓ '}{stepText}
                      </span>
                    </div>
                  ))
                ) : (
                // Fallback to "Thinking..." if no steps available
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 'var(--spacing-sm)'
                }}>
                  <div style={{
                    width: '12px',
                    height: '12px',
                    borderWidth: '2px',
                    borderStyle: 'solid',
                    borderColor: 'rgba(255, 255, 255, 0.5)',
                    borderTopColor: 'transparent',
                    borderRadius: '50%',
                    animation: 'spin 0.8s linear infinite'
                  }}></div>
                  <span style={{ color: 'rgba(255, 255, 255, 0.8)', fontSize: '0.9rem', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>Thinking...</span>
                </div>
                )
              })()}
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div style={{ 
        background: 'transparent', 
        borderTop: '1px solid rgba(255, 255, 255, 0.1)',
        boxShadow: '0 -2px 8px rgba(0,0,0,0.2)'
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
            <div className="glassmorphism" style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--spacing-sm)',
              padding: 'var(--spacing-sm)',
              borderRadius: 'var(--border-radius)'
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
              <span style={{ flex: 1, fontSize: '0.875rem', color: 'rgba(255, 255, 255, 0.8)', textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)' }}>
                {selectedImage?.name || 'Image selected'}
              </span>
              <button
                type="button"
                onClick={() => {
                  setSelectedImage(null)
                  setImagePreview(null)
                }}
                style={{
                  padding: '0.5rem',
                  background: 'transparent',
                  color: 'rgba(255, 255, 255, 0.7)',
                  border: 'none',
                  borderRadius: 'var(--border-radius)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '32px',
                  height: '32px',
                  transition: 'all 0.2s ease'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.color = '#ff4444'
                  e.currentTarget.style.background = 'rgba(255, 68, 68, 0.1)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = 'rgba(255, 255, 255, 0.7)'
                  e.currentTarget.style.background = 'transparent'
                }}
                aria-label="Remove image"
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
                  style={{ transition: 'color 0.2s ease' }}
                >
                  <line x1="18" y1="6" x2="6" y2="18"></line>
                  <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
              </button>
            </div>
          )}
          
          <div style={{ display: 'flex', gap: 'var(--spacing-md)', alignItems: 'center' }}>
            {/* Image Upload (for Nutrition and Coordinator Agents) */}
            {(selectedAgent === 'nutrition' || selectedAgent === 'coordinator') && (
              <label
                className="glassmorphism"
                style={{
                  padding: '0.75rem',
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
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)'
                  e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.4)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'rgba(23, 23, 23, 0.05)'
                  e.currentTarget.style.borderColor = 'rgba(82, 82, 82, 0.2)'
                }}
              >
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="white"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
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

