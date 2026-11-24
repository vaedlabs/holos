// @vitest-environment jsdom
/**
 * The logs as the person reads them (R7; D062 B1, B3): from the API's real shape, where a
 * workout's exercises and a meal's foods and macros come as JSON strings.
 */

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import MealLogs from '@/components/logs/MealLogs'
import PracticeLogs from '@/components/logs/PracticeLogs'
import WorkoutLogs from '@/components/logs/WorkoutLogs'
import { mealView, practiceView, workoutView } from '@/lib/logs'

afterEach(cleanup)

// As the log endpoints send them (dev database, 23 Nov 2026)
const run = { id: 1, workout_date: '2026-11-23T01:29:00Z', exercise_type: 'running', duration_minutes: 30,
  exercises: '[{"catalogue_id": "running", "name": "Running", "sets": null, "reps": null, "duration_s": 1800}]',
  notes: 'About 4 km; easy run.' }
const deadlift = { id: 2, workout_date: '2026-11-22T12:00:00Z', exercise_type: 'deadlift', duration_minutes: null,
  exercises: '[{"catalogue_id": "deadlift", "name": "Deadlift", "sets": 3, "reps": 8, "duration_s": null}]', notes: null }
const lunch = { id: 3, meal_date: '2026-11-23T08:00:00Z', meal_type: 'lunch', calories: 490,
  foods: '[{"name": "Rotis", "portion": "2 rotis", "calories": 220.0}, {"name": "Dal", "portion": "1 bowl", "calories": 270.0}]',
  macros: '{"protein_g": 21.0, "carbs_g": 70.0, "fat_g": 12.0, "complete": true}', notes: null }
const meditation = { id: 4, activity_date: '2026-11-16T01:15:00Z', activity_type: 'mindfulness_meditation',
  duration_minutes: 10, mood_before: null, mood_after: null, notes: 'Dhyan' }

describe('reading a log', () => {
  it('a workout reads as what was done, never as JSON', () => {
    expect(workoutView(run)).toMatchObject({ title: 'Running', detail: '30 min' })
    expect(workoutView(deadlift)).toMatchObject({ title: 'Deadlift', detail: '3 × 8' })
  })

  it('a meal reads as its foods, with calories and macros', () => {
    expect(mealView(lunch)).toMatchObject({ title: 'Rotis, Dal', meal: 'Lunch', calories: 490,
                                            macros: { protein: 21, carbs: 70, fat: 12 } })
  })

  it('anything unreadable falls back to a plain name', () => {
    expect(workoutView({ ...run, exercises: 'not json' }).title).toBe('Running')
    expect(mealView({ ...lunch, foods: '{"oops"', macros: null }).title).toBe('Lunch')
    expect(mealView({ ...lunch, foods: null, meal_type: null }).title).toBe('Meal')
  })

  it('a practice reads as its kind and length', () => {
    expect(practiceView(meditation)).toMatchObject({ title: 'Mindfulness meditation', detail: '10 min' })
  })
})

describe('the lists', () => {
  it('a workout log reads "Running · 30 min"', () => {
    const { container } = render(<WorkoutLogs logs={[run]} onDelete={vi.fn()} />)
    expect(container.textContent).toContain('Running')
    expect(screen.getByText('30 min')).toBeTruthy()
    expect(container.textContent).not.toContain('catalogue_id')
  })

  it('a meal log renders its foods by name', () => {
    const { container } = render(<MealLogs logs={[lunch]} onDelete={vi.fn()} />)
    expect(screen.getByText('Rotis, Dal')).toBeTruthy()
    expect(container.textContent).toContain('490 kcal')
    expect(container.textContent).not.toContain('"name"')
  })

  it('Delete names the entry it asks about', () => {
    const onDelete = vi.fn()
    render(<PracticeLogs logs={[meditation]} onDelete={onDelete} />)
    fireEvent.click(screen.getByRole('button', { name: 'Delete Mindfulness meditation' }))
    expect(onDelete).toHaveBeenCalledWith(meditation, 'Mindfulness meditation')
  })

  it('an empty list says how entries get there', () => {
    render(<MealLogs logs={[]} onDelete={vi.fn()} />)
    expect(screen.getByText(/No meals logged yet/)).toBeTruthy()
  })
})
