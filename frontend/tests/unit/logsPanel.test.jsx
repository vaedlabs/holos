// @vitest-environment jsdom
/**
 * The logs panel (owner, 24 Nov 2026): the header's Logs toggles it for everyone; an account
 * sees its logs, a guest is told they come with signing in and nothing is fetched.
 */

import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getWorkoutLogs: vi.fn(), getNutritionLogs: vi.fn(), getMentalFitnessLogs: vi.fn(),
  deleteWorkoutLog: vi.fn(), deleteNutritionLog: vi.fn(), deleteMentalFitnessLog: vi.fn(),
}))
vi.mock('@/lib/api', async (importOriginal) => ({ ...(await importOriginal()), api }))

const { default: LogsPanel } = await import('@/components/logs/LogsPanel')

beforeEach(() => Object.values(api).forEach((fn) => fn.mockReset()))
afterEach(cleanup)

describe('the logs panel', () => {
  it('is nothing while closed', () => {
    const { container } = render(<LogsPanel open={false} guest={false} />)
    expect(container.innerHTML).toBe('')
  })

  it('tells a guest the logs come with signing in, and fetches nothing', () => {
    render(<LogsPanel open guest />)
    expect(screen.getByText('Your logs are available once you sign in.')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Sign in' }).getAttribute('href')).toBe('/login')
    expect(api.getWorkoutLogs).not.toHaveBeenCalled()
  })

  it("shows an account's logs once loaded", async () => {
    api.getWorkoutLogs.mockResolvedValue({ logs: [{ id: 1, workout_date: '2026-11-23T01:29:00Z', exercise_type: 'running',
      exercises: '[{"name": "Running", "duration_s": 1800}]', duration_minutes: 30, notes: null }] })
    api.getNutritionLogs.mockResolvedValue({ logs: [] })
    api.getMentalFitnessLogs.mockResolvedValue({ logs: [] })
    render(<LogsPanel open guest={false} />)
    expect(screen.getByRole('region', { name: 'Logs' })).toBeTruthy()
    expect(await screen.findByText('Running')).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Nutrition' })).toBeTruthy()
  })
})
