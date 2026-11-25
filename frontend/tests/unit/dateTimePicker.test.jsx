// @vitest-environment jsdom
/**
 * The themed date and time picker (owner, 24 Nov 2026): the field shows the chosen moment in
 * words, and picking a day keeps the time.
 */

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import DateTimePicker, { DateTimeField } from '@/components/DateTimePicker'

afterEach(cleanup)

const draw = (value, onChange = vi.fn()) => render(
  <DateTimePicker value={value} onChange={onChange}>
    <div><DateTimeField id="when" value={value} /></div>
  </DateTimePicker>)

describe('the date and time picker', () => {
  it('shows the moment in words', () => {
    draw('2026-11-24T20:05')
    expect(screen.getByRole('button', { name: /Tue, 24 Nov 2026, 8:05 pm/ })).toBeTruthy()
  })

  it('picking a day keeps the time', () => {
    const onChange = vi.fn()
    draw('2026-11-24T08:00', onChange)
    fireEvent.click(screen.getByRole('button', { name: /24 Nov 2026/ }))
    fireEvent.click(screen.getByRole('button', { name: /November 25/ }))
    expect(onChange).toHaveBeenCalledWith('2026-11-25T08:00')
  })

  it('has a wheel each for hour, minute and am or pm', () => {
    draw('2026-11-24T08:00')
    fireEvent.click(screen.getByRole('button', { name: /24 Nov 2026/ }))
    for (const name of ['Hour', 'Minute', 'AM or PM']) expect(screen.getByRole('listbox', { name })).toBeTruthy()
  })
})
