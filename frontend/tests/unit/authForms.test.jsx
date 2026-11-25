// @vitest-environment jsdom
/**
 * The invite and login forms (D064, Part E #73): the "please agree" error goes once the box
 * is ticked, and a 422 shows its reason under the field it names, not as a general message.
 */

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import InvitePage from '@/app/invite/[token]/page'
import LoginPage from '@/app/login/page'
import { ApiError } from '@/lib/api'

const { acceptInvite, signIn } = vi.hoisted(() => ({ acceptInvite: vi.fn(), signIn: vi.fn() }))
vi.mock('@/lib/api', async (importOriginal) => ({ ...(await importOriginal()), acceptInvite, signIn }))
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }), useParams: () => ({ token: 't' }) }))
vi.mock('@/hooks/useAuth', () => ({ useRedirectIfAuthenticated: () => ({ mounted: true }) }))
// The silk background draws with WebGL, which jsdom hasn't got
vi.mock('@/components/AuthShell', () => ({ default: ({ children }) => <main>{children}</main> }))

// Radix's checkbox measures itself; jsdom has no ResizeObserver
globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const INVALID = new ApiError(422, 'bad_request', "Some of what was sent isn't valid.", null, [],
                             { email: 'not a valid address' })
const fill = (email, password) => {
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: email } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: password } })
}

describe('the invite page', () => {
  it('the "please agree" error goes once the box is ticked', () => {
    render(<InvitePage />)
    fill('a@example.com', 'secret')
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(screen.getByText(/Please agree/)).toBeTruthy()
    fireEvent.click(screen.getByRole('checkbox'))
    expect(screen.queryByText(/Please agree/)).toBeNull()
    expect(acceptInvite).not.toHaveBeenCalled()
  })

  it('a 422 shows its reason under the field, and goes when the field changes', async () => {
    acceptInvite.mockRejectedValue(INVALID)
    render(<InvitePage />)
    fill('me@home.test', 'secret')
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))
    await waitFor(() => expect(screen.getByText('Not a valid address')).toBeTruthy())
    expect(screen.getByLabelText('Email').getAttribute('aria-invalid')).toBe('true')
    expect(screen.queryByText("Some of what was sent isn't valid.")).toBeNull()
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'me@example.com' } })
    expect(screen.queryByText('Not a valid address')).toBeNull()
  })

  it("any other error is the server's message", async () => {
    acceptInvite.mockRejectedValue(new ApiError(410, 'expired', 'This invite has expired.'))
    render(<InvitePage />)
    fill('a@example.com', 'secret')
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))
    await waitFor(() => expect(screen.getByText('This invite has expired.')).toBeTruthy())
  })
})

describe('the login page', () => {
  it('a 422 shows its reason under the field it names', async () => {
    signIn.mockRejectedValue(INVALID)
    render(<LoginPage />)
    fill('me@home.test', 'secret')
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(screen.getByText('Not a valid address')).toBeTruthy())
    expect(screen.queryByText("Some of what was sent isn't valid.")).toBeNull()
  })

  it('wrong credentials stay one message', async () => {
    signIn.mockRejectedValue(new ApiError(401, 'bad_credentials', 'Wrong email or password.'))
    render(<LoginPage />)
    fill('a@example.com', 'secret')
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(screen.getByText('Wrong email or password.')).toBeTruthy())
  })
})
