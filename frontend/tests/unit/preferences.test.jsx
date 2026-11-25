// @vitest-environment jsdom
/**
 * The preferences page (R7; D062 B4): none saved yet is an empty state, not an error; saved
 * values read as words; deleting the account asks in a dialog and wants DELETE typed.
 */

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/lib/api'

const api = vi.hoisted(() => ({
  getUserPreferences: vi.fn(),
  updateUserPreferences: vi.fn(),
  clearConversationHistory: vi.fn(),
  deleteAccount: vi.fn(),
}))
vi.mock('@/lib/api', async (importOriginal) => ({ ...(await importOriginal()), api, signOut: vi.fn() }))
vi.mock('@/hooks/useAuth', () => ({ useRequireAuth: () => ({ mounted: true, isAuthenticated: true }) }))
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }))

const { default: PreferencesPage } = await import('@/app/preferences/page')

beforeEach(() => Object.values(api).forEach((fn) => fn.mockReset()))
afterEach(cleanup)

describe('the preferences page', () => {
  it('with none saved yet shows how to add them, and no error', async () => {
    api.getUserPreferences.mockRejectedValue(new ApiError(404, 'not_found', 'There are no preferences yet.'))
    render(<PreferencesPage />)
    expect(await screen.findByText('No preferences recorded yet.')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Add preferences' })).toBeTruthy()
    expect(screen.queryByText('There are no preferences yet.')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('shows saved values in words', async () => {
    api.getUserPreferences.mockResolvedValue({ goals: 'Build Muscle', activity_level: 'very_high', lifestyle: 'very_active' })
    render(<PreferencesPage />)
    expect(await screen.findByText('Very high')).toBeTruthy()
    expect(screen.getByText('Very active')).toBeTruthy()
    expect(screen.queryByText('very_active')).toBeNull()
  })

  it('a real failure to load says so', async () => {
    api.getUserPreferences.mockRejectedValue(new ApiError(503, 'unavailable', 'Holos is busy right now.'))
    render(<PreferencesPage />)
    expect(await screen.findByText('Holos is busy right now.')).toBeTruthy()
  })

  it('deleting the account asks in a dialog and needs DELETE typed', async () => {
    api.getUserPreferences.mockResolvedValue({ goals: 'Build Muscle' })
    api.deleteAccount.mockResolvedValue(undefined)
    render(<PreferencesPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Delete account' }))
    const confirm = await screen.findByRole('button', { name: 'Delete account' })
    expect(confirm.disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('Type DELETE to confirm'), { target: { value: 'DELETE' } })
    expect(confirm.disabled).toBe(false)
    fireEvent.click(confirm)
    await waitFor(() => expect(api.deleteAccount).toHaveBeenCalledOnce())
  })

  it('a confirmation box closes on a click outside, and its action waits a moment before it counts', async () => {
    api.getUserPreferences.mockResolvedValue({ goals: 'Build Muscle' })
    render(<PreferencesPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Clear conversation history' }))
    const box = await screen.findByRole('alertdialog')
    expect(box.dataset.armed).toBe('false')
    await waitFor(() => expect(box.dataset.armed).toBe('true'))
    fireEvent.click(document.querySelector('[data-slot=alert-dialog-overlay]'))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    expect(api.clearConversationHistory).not.toHaveBeenCalled()
  })
})
