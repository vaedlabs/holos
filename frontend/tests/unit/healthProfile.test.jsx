// @vitest-environment jsdom
/**
 * The health profile (P5.3, Part E #42): typed "torn ACL" shows as understood;
 * "menopause" shows as not checked with a picker; the free box carries no warning; what
 * an account saves reads back as the same pickers.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import catalogue from '../../../contracts/catalogue.json'
import HealthProfile, { readSaved, toSave } from '@/components/HealthProfile'
import { forgetSession, rememberSession } from '@/lib/api'

const NONE = { conditions: [], allergens: [], diets: [], unchecked: [] }
const json = (status, body) => new Response(JSON.stringify(body), {
  status, headers: { 'content-type': 'application/json' } })

/** The server, by route; each call recorded with its body. */
function server(routes) {
  const calls = []
  vi.stubGlobal('fetch', vi.fn(async (url, init = {}) => {
    const route = `${init.method || 'GET'} ${new URL(url).pathname}`
    calls.push({ route, body: init.body ? JSON.parse(init.body) : null })
    const answer = routes[route]
    if (!answer) return json(404, { code: 'not_found', message: 'none' })
    return json(200, typeof answer === 'function' ? answer(calls.at(-1).body) : answer)
  }))
  return calls
}

beforeEach(() => rememberSession({ csrf_token: 'c' }))
afterEach(() => { cleanup(); vi.unstubAllGlobals(); forgetSession() })

describe('an account', () => {
  it('typed "torn ACL" shows as understood', async () => {
    let saved = ''
    const calls = server({
      'POST /medical/history': (body) => { saved = body.conditions; return body },
      'POST /preferences': (body) => body,
      'GET /profile/check': () => (saved.includes('torn ACL')
        ? { ...NONE, conditions: [{ id: 'knee_ligament_injury', name: 'Knee ligament injury' }] }
        : NONE),
    })
    render(<HealthProfile mode="account" />)
    fireEvent.change(await screen.findByLabelText('Other conditions or injuries'),
                     { target: { value: 'torn ACL left knee' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(within(screen.getByRole('region', { name: 'Holos understood' })).getByText('Knee ligament injury')).toBeTruthy())
    expect(calls.find((c) => c.route === 'POST /medical/history').body.conditions)
      .toBe('torn ACL left knee')
  })

  it('"menopause" shows as not checked, with a picker that replaces it', async () => {
    server({
      'POST /medical/history': (b) => b, 'POST /preferences': (b) => b,
      'GET /profile/check': { ...NONE, unchecked: ['menopause'] },
    })
    render(<HealthProfile mode="account" />)
    const other = await screen.findByLabelText('Other conditions or injuries')
    fireEvent.change(other, { target: { value: 'menopause' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    const picker = await screen.findByLabelText('What did you mean by menopause?')
    expect(screen.getByText(/couldn.t check/)).toBeTruthy()
    fireEvent.change(picker, { target: { value: 'osteoporosis' } })
    expect(other.value).toBe('')
    expect(screen.getByLabelText('Osteoporosis').checked).toBe(true)
  })

  it('the free box carries no warning', async () => {
    server({ 'POST /medical/history': (b) => b, 'POST /preferences': (b) => b,
             'GET /profile/check': NONE })
    render(<HealthProfile mode="account" />)
    fireEvent.change(await screen.findByLabelText('Anything else'),
                     { target: { value: 'very little free time' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(screen.getByText(/Holos understood/)).toBeTruthy())
    expect(screen.queryByText(/couldn.t check/)).toBeNull()
  })

  it('loads what was saved: pickers ticked, the rest as typed', async () => {
    server({
      'GET /medical/history': { conditions: 'Knee ligament injury, bad hip thing', notes: 'n' },
      'GET /preferences': { dietary_restrictions: 'peanut allergy, vegan, no mushrooms' },
      'GET /profile/check': NONE,
    })
    render(<HealthProfile mode="account" />)
    await waitFor(() => expect(screen.getByLabelText('Knee ligament injury').checked).toBe(true))
    expect(screen.getByLabelText('Peanut').checked).toBe(true)
    expect(screen.getByLabelText('Vegan').checked).toBe(true)
    expect(screen.getByLabelText('Other conditions or injuries').value).toBe('bad hip thing')
    expect(screen.getByLabelText('Other food restrictions').value).toBe('no mushrooms')
  })
})

describe('onboarding', () => {
  it('shows what Holos understood before going on', async () => {
    server({ 'POST /medical/history': (b) => b, 'POST /preferences': (b) => b,
             'GET /profile/check': { ...NONE, unchecked: ['menopause'] } })
    const onSaved = vi.fn()
    render(<HealthProfile mode="account" onSaved={onSaved} />)
    await screen.findByRole('button', { name: 'Continue' })
    // A change since the last check: Save again before going on, one action at a time
    fireEvent.click(screen.getByLabelText('Asthma'))
    expect(screen.queryByRole('button', { name: 'Continue' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(screen.getByText(/couldn.t check/)).toBeTruthy())
    expect(onSaved).not.toHaveBeenCalled()
    fireEvent.click(await screen.findByRole('button', { name: 'Continue' }))
    expect(onSaved).toHaveBeenCalledOnce()
  })

  it('Back goes to the step before', async () => {
    server({ 'GET /profile/check': NONE })
    const onBack = vi.fn()
    render(<HealthProfile mode="account" onSaved={vi.fn()} onBack={onBack} />)
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(onBack).toHaveBeenCalledOnce()
  })
})

describe('saving on the profile page', () => {
  it('Save waits for a change', async () => {
    server({ 'GET /profile/check': NONE })
    render(<HealthProfile mode="account" />)
    const save = await screen.findByRole('button', { name: 'Save' })
    expect(save.disabled).toBe(true)
    fireEvent.click(screen.getByLabelText('Asthma'))
    expect(save.disabled).toBe(false)
  })
})

describe('a guest', () => {
  it('a sample profile is saved in the browser and shown as understood', async () => {
    server({ 'POST /profile/check': NONE })
    const store = { profile: () => null, setProfile: vi.fn() }
    render(<HealthProfile mode="guest" store={store} />)
    fireEvent.click(screen.getByRole('button', { name: 'Knee injury' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(within(screen.getByRole('region', { name: 'Holos understood' })).getByText('Knee ligament injury')).toBeTruthy())
    expect(store.setProfile).toHaveBeenCalledWith({ condition_ids: ['knee_ligament_injury'],
                                                    allergen_tags: [], diet_tags: [], notes: '' })
    expect(screen.queryByLabelText('Medications')).toBeNull() // a guest's profile is IDs and notes
  })
})

describe('saving in the catalogue\'s words', () => {
  it('every picker saved together loads back ticked', () => {
    const form = { conditions: catalogue.conditions.map((c) => c.id),
                   allergens: catalogue.allergens.map((a) => a.id),
                   diets: catalogue.diets.map((d) => d.id), otherConditions: 'bad hip',
                   otherFood: 'no mushrooms', limitations: 'l', medications: 'm', notes: 'n' }
    const { medical, preferences } = toSave(form)
    expect(readSaved(medical, preferences)).toEqual(form)
  })
})
