'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'

/**
 * An account's logs: workouts, meals and practices, newest first, each deletable. Moved
 * as it was from the old dashboard (P5.3, owner: the logs view stays as it is).
 */
export default function LogsPanel({ open }) {
  const workoutLogsOpen = open
  const [activeLogTab, setActiveLogTab] = useState('workouts')
  const [loadingLogs, setLoadingLogs] = useState(false)
  const [workoutLogs, setWorkoutLogs] = useState([])
  const [nutritionLogs, setNutritionLogs] = useState([])
  const [mentalFitnessLogs, setMentalFitnessLogs] = useState([])

  const loadAllLogs = useCallback(async () => {
    setLoadingLogs(true)
    try {
      const [workoutData, nutritionData, mentalData] = await Promise.all([
        api.getWorkoutLogs(10, 0).catch(() => ({ logs: [] })),
        api.getNutritionLogs(10, 0).catch(() => ({ logs: [] })),
        api.getMentalFitnessLogs(10, 0).catch(() => ({ logs: [] })),
      ])
      setWorkoutLogs(workoutData.logs || [])
      setNutritionLogs(nutritionData.logs || [])
      setMentalFitnessLogs(mentalData.logs || [])
    } finally {
      setLoadingLogs(false)
    }
  }, [])

  useEffect(() => {
    if (open) loadAllLogs()
  }, [open, loadAllLogs])

  const handleDeleteLog = async (logId, logType) => {
    if (!window.confirm(`Delete this ${logType} log?`)) return
    try {
      if (logType === 'workout') {
        await api.deleteWorkoutLog(logId)
        setWorkoutLogs((prev) => prev.filter((log) => log.id !== logId))
      } else if (logType === 'nutrition') {
        await api.deleteNutritionLog(logId)
        setNutritionLogs((prev) => prev.filter((log) => log.id !== logId))
      } else {
        await api.deleteMentalFitnessLog(logId)
        setMentalFitnessLogs((prev) => prev.filter((log) => log.id !== logId))
      }
    } catch (error) {
      window.alert(error.message)
    }
  }

  if (!workoutLogsOpen) return null
  return (
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

  )
}
