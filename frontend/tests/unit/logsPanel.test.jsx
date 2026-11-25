// @vitest-environment jsdom
/**
 * The logs drawer (owner, 24 and 25 Nov 2026): the header's Logs opens it for everyone; an
 * account sees its logs on the newest entry's tab, a guest is told they come with signing in and
 * nothing is fetched.
 */

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getWorkoutLogs: vi.fn(), getNutritionLogs: vi.fn(), getMentalFitnessLogs: vi.fn(),
  deleteWorkoutLog: vi.fn(), deleteNutritionLog: vi.fn(), deleteMentalFitnessLog: vi.fn(),
}))
vi.mock('@/lib/api', async (importOriginal) => ({ ...(await importOriginal()), api }))
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))
vi.mock('sonner', () => ({ toast }))

const { default: LogsPanel } = await import('@/components/logs/LogsPanel')

const open = (guest) => {
  render(<LogsPanel guest={guest}><button type="button">Logs</button></LogsPanel>)
  fireEvent.click(screen.getByRole('button', { name: 'Logs' }))
}

beforeEach(() => { Object.values(api).forEach((fn) => fn.mockReset()); localStorage.clear() })
afterEach(cleanup)

describe('the logs drawer', () => {
  it('is only its button while closed', () => {
    render(<LogsPanel guest={false}><button type="button">Logs</button></LogsPanel>)
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(api.getWorkoutLogs).not.toHaveBeenCalled()
  })

  it('tells a guest the logs come with signing in, and fetches nothing', () => {
    open(true)
    expect(screen.getByText('Your logs are available once you sign in.')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Sign in' }).getAttribute('href')).toBe('/login')
    expect(api.getWorkoutLogs).not.toHaveBeenCalled()
  })

  it("shows an account's logs once loaded", async () => {
    api.getWorkoutLogs.mockResolvedValue({ logs: [{ id: 1, workout_date: '2026-11-23T01:29:00Z', exercise_type: 'running',
      exercises: '[{"name": "Running", "duration_s": 1800}]', duration_minutes: 30, notes: null }] })
    api.getNutritionLogs.mockResolvedValue({ logs: [] })
    api.getMentalFitnessLogs.mockResolvedValue({ logs: [] })
    open(false)
    expect(screen.getByRole('dialog', { name: 'Logs' })).toBeTruthy()
    expect(await screen.findByText('Running')).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Nutrition' })).toBeTruthy()
  })


  it('a delete says so, and leaves the focus on the open tab', async () => {
    api.getWorkoutLogs.mockResolvedValue({ logs: [] })
    api.getNutritionLogs.mockResolvedValue({ logs: [] })
    api.getMentalFitnessLogs.mockResolvedValue({ logs: [{ id: 7, activity_date: '2026-11-25T04:27:00Z',
      activity_type: 'mindfulness_meditation', duration_minutes: 10, notes: null }] })
    api.deleteMentalFitnessLog.mockResolvedValue({})
    open(false)
    fireEvent.click(await screen.findByRole('button', { name: 'Delete Mindfulness meditation' }))
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Mindfulness meditation deleted'))
    expect(await screen.findByText(/No practices logged yet/)).toBeTruthy()
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('tab', { name: 'Mental' })))
  })

  it('Keep it sends the focus back to the bin it came from', async () => {
    api.getWorkoutLogs.mockResolvedValue({ logs: [] })
    api.getNutritionLogs.mockResolvedValue({ logs: [] })
    api.getMentalFitnessLogs.mockResolvedValue({ logs: [{ id: 7, activity_date: '2026-11-25T04:27:00Z',
      activity_type: 'mindfulness_meditation', duration_minutes: 10, notes: null }] })
    open(false)
    const bin = await screen.findByRole('button', { name: 'Delete Mindfulness meditation' })
    bin.focus()
    fireEvent.click(bin)
    fireEvent.click(screen.getByRole('button', { name: 'Keep it' }))
    await waitFor(() => expect(document.activeElement).toBe(bin))
    expect(api.deleteMentalFitnessLog).not.toHaveBeenCalled()
  })

  it('a click outside the box closes it, deleting nothing', async () => {
    api.getWorkoutLogs.mockResolvedValue({ logs: [] })
    api.getNutritionLogs.mockResolvedValue({ logs: [] })
    api.getMentalFitnessLogs.mockResolvedValue({ logs: [{ id: 7, activity_date: '2026-11-25T04:27:00Z',
      activity_type: 'mindfulness_meditation', duration_minutes: 10, notes: null }] })
    open(false)
    fireEvent.click(await screen.findByRole('button', { name: 'Delete Mindfulness meditation' }))
    fireEvent.click(document.querySelector('[data-slot=alert-dialog-overlay]'))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    expect(screen.getByRole('dialog', { name: 'Logs' })).toBeTruthy()
    expect(api.deleteMentalFitnessLog).not.toHaveBeenCalled()
  })
})
