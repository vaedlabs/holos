// @vitest-environment jsdom
/**
 * The logs as the person reads them (R7; D062 B1, B3): from the API's real shape, a workout's
 * exercises and a meal's foods as lists and its macros as an object (R9, Part E #74). The
 * fixtures are checked against the log contracts, so they can't drift from what is sent.
 */

import fs from 'node:fs'
import path from 'node:path'
import Ajv2020 from 'ajv/dist/2020'
import addFormats from 'ajv-formats'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import MealLogs from '@/components/logs/MealLogs'
import PracticeLogs from '@/components/logs/PracticeLogs'
import WorkoutLogs from '@/components/logs/WorkoutLogs'
import { mealView, practiceView, workoutView } from '@/lib/logs'

afterEach(cleanup)

// As the log endpoints send them (dev database, 23 Nov 2026; lists since R9)
const row = { user_id: 7, created_at: '2026-11-23T01:30:00Z', updated_at: null }
const food = (name, portion, calories) => ({ name, portion, calories, protein_g: null, carbs_g: null, fat_g: null })
const run = { ...row, id: 1, workout_date: '2026-11-23T01:29:00Z', exercise_type: 'running', duration_minutes: 30,
  exercises: [{ catalogue_id: 'running', name: 'Running', sets: null, reps: null, duration_s: 1800 }],
  notes: 'About 4 km; easy run.' }
const deadlift = { ...row, id: 2, workout_date: '2026-11-22T12:00:00Z', exercise_type: 'deadlift', duration_minutes: null,
  exercises: [{ catalogue_id: 'deadlift', name: 'Deadlift', sets: 3, reps: 8, duration_s: null }], notes: null }
const lunch = { ...row, id: 3, meal_date: '2026-11-23T08:00:00Z', meal_type: 'lunch', calories: 490,
  foods: [food('Rotis', '2 rotis', 220), food('Dal', '1 bowl', 270)],
  macros: { protein_g: 21, carbs_g: 70, fat_g: 12, complete: true }, notes: null }
const meditation = { ...row, id: 4, activity_date: '2026-11-16T01:15:00Z', activity_type: 'mindfulness_meditation',
  duration_minutes: 10, notes: 'Dhyan' }

const ajv = addFormats(new Ajv2020({ strict: false, allErrors: true }))
const contract = (file) => ajv.compile(JSON.parse(fs.readFileSync(
  path.resolve(__dirname, '../../../contracts/schema', file), 'utf8')))

it('the fixtures are what the log endpoints send (their contracts)', () => {
  expect(contract('workout_logs.json')({ logs: [run, deadlift], total: 2 })).toBe(true)
  expect(contract('nutrition_logs.json')({ logs: [lunch], total: 1 })).toBe(true)
  expect(contract('mental_fitness_logs.json')({ logs: [meditation], total: 1 })).toBe(true)
  // A JSON string, as the endpoints sent before R9, is no longer the contract
  expect(contract('nutrition_logs.json')({ logs: [{ ...lunch, foods: '[]' }], total: 1 })).toBe(false)
})

describe('reading a log', () => {
  it('a workout reads as what was done, never as JSON', () => {
    expect(workoutView(run)).toMatchObject({ title: 'Running', detail: '30 min' })
    expect(workoutView(deadlift)).toMatchObject({ title: 'Deadlift', detail: '3 × 8' })
  })

  it('a meal reads as its foods, with calories and macros', () => {
    expect(mealView(lunch)).toMatchObject({ title: 'Rotis, Dal', meal: 'Lunch', calories: 490,
                                            macros: { protein: 21, carbs: 70, fat: 12 } })
  })

  it('a workout shows each count the person gave, and none it didn\'t', () => {
    const with_ = (fields) => ({ ...run, duration_minutes: null,
      exercises: [{ name: 'Bodyweight squat', catalogue_id: null, sets: null, reps: null, duration_s: null, ...fields }] })
    expect(workoutView(with_({ reps: 15 })).detail).toBe('15 reps')
    expect(workoutView(with_({ sets: 3 })).detail).toBe('3 sets')
    expect(workoutView(with_({ sets: 3, reps: 8 })).detail).toBe('3 × 8')
    expect(workoutView(with_({})).detail).toBe('')
  })

  it('with nothing listed, a log falls back to a plain name', () => {
    // The server leaves out what didn't read (an old row, broken text): an empty list here
    expect(workoutView({ ...run, exercises: [] }).title).toBe('Running')
    expect(mealView({ ...lunch, foods: [], macros: null })).toMatchObject(
      { title: 'Lunch', macros: { protein: null, carbs: null, fat: null } })
    expect(mealView({ ...lunch, foods: [], meal_type: null }).title).toBe('Meal')
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

  it('a meal log is its meal, then its foods by name with their portions, once each', () => {
    const { container } = render(<MealLogs logs={[lunch]} onDelete={vi.fn()} />)
    expect(screen.getByText('Lunch')).toBeTruthy()
    expect(screen.getByText('Rotis · 2 rotis')).toBeTruthy()
    expect(screen.queryByText('Rotis, Dal')).toBeNull()
    expect(screen.getByRole('button', { name: 'Delete Rotis, Dal' })).toBeTruthy()
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

describe('what a log was saved with (Part E #65 (4))', () => {
  const warning = (fields) => ({ kind: 'conflict', item: 'Poha', rule_id: 'DI-ALG-01', attributes: ['peanut'],
                                 reason: 'Contains an allergen in your profile', left_out: false, ...fields })
  const breakfast = (warnings) => ({ ...lunch, id: 9, meal_type: 'breakfast', foods: [food('Poha', '1 plate', 300)],
                                     warnings })
  const shown = (warnings) => {
    render(<MealLogs logs={[breakfast(warnings)]} onDelete={() => {}} />)
    return screen.getAllByRole('listitem')[0].textContent // the log; its foods are items too
  }

  it('the fixtures with warnings are what the endpoint sends', () => {
    expect(contract('nutrition_logs.json')({ logs: [breakfast([warning(), warning({ kind: 'unchecked' })])], total: 1 }))
      .toBe(true)
  })

  it('what was left out is a quiet note', () => {
    const text = shown([warning({ left_out: true }), warning({ left_out: true })])
    expect(text).toContain('Poha · without peanut')
    expect(text.match(/without peanut/g)).toHaveLength(1)
    expect(text).not.toContain('You confirmed')
  })

  it('a conflict the person confirmed is flagged with what fired, and says they confirmed it', () => {
    shown([warning()])
    const flag = screen.getByText(/You confirmed this entry/)
    expect(flag.textContent).toBe('Poha: contains an allergen in your profile (peanut). You confirmed this entry.')
    expect(flag.closest('.text-caution')).not.toBeNull()
  })

  it('an unchecked ingredient, or none stored, says nothing', () => {
    const plain = shown(undefined)
    cleanup()
    expect(shown([warning({ kind: 'unchecked', reason: 'Not checked against your allergies' })])).toBe(plain)
  })
})
