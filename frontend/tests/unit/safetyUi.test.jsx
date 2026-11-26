// @vitest-environment jsdom
/**
 * The safety pieces on every page (P5.4; Part E #78): "Need help now?" opens the helplines from
 * the bundled contracts/crisis.json with nothing fetched, so it works with the backend down; the
 * demo notice stays until closed and comes once a browser session.
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import DemoNotice, { DEMO_TEXT } from '@/components/DemoNotice'
import HelpNow from '@/components/HelpNow'
import { Toaster } from '@/components/ui/sonner'

afterEach(cleanup)

describe('Need help now?', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch')))) // the backend is down
  })
  afterEach(() => vi.unstubAllGlobals())

  it('opens the helplines with nothing fetched', () => {
    render(<HelpNow />)
    fireEvent.click(screen.getByRole('button', { name: 'Need help now?' }))
    const dialog = screen.getByRole('dialog')
    expect(dialog.textContent).toContain('Tele-MANAS')
    expect(dialog.textContent).toContain('988')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('a phone can call each number; the website opens on its own', () => {
    render(<HelpNow />)
    fireEvent.click(screen.getByRole('button', { name: 'Need help now?' }))
    expect(screen.getByRole('link', { name: '14416' }).getAttribute('href')).toBe('tel:14416')
    expect(screen.getByRole('link', { name: '988' }).getAttribute('href')).toBe('tel:988')
    expect(screen.getByRole('link', { name: 'findahelpline.com' }).getAttribute('href')).toBe('https://findahelpline.com')
  })
})

describe('the demo notice', () => {
  beforeEach(() => {
    sessionStorage.clear()
    // jsdom has no matchMedia; the toaster asks it for the colour scheme
    vi.stubGlobal('matchMedia', (query) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {},
                                              addListener() {}, removeListener() {} }))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('stays until closed, and comes once a browser session', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      const first = render(<><Toaster /><DemoNotice /></>)
      await screen.findByText(DEMO_TEXT)
      await act(async () => vi.advanceTimersByTime(60_000))
      expect(screen.getByText(DEMO_TEXT)).toBeTruthy() // still there a minute on
      fireEvent.click(screen.getByRole('button', { name: /close/i }))
      await waitFor(() => expect(screen.queryByText(DEMO_TEXT)).toBeNull())
      first.unmount()

      render(<><Toaster /><DemoNotice /></>) // the next page this session
      await act(async () => vi.advanceTimersByTime(1000))
      expect(screen.queryByText(DEMO_TEXT)).toBeNull()
    } finally {
      vi.useRealTimers()
    }
  })
})
