'use client'

import { useState } from 'react'
import { CircleAlert } from 'lucide-react'

import ButtonSelector from '@/components/ButtonSelector'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Field, FieldDescription, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Spinner } from '@/components/ui/spinner'
import { api } from '@/lib/api'
import { ACTIVITY_LEVELS, EXERCISE_TYPES, GENDERS, GOALS, LIFESTYLES } from '@/lib/preferenceOptions'

const Optional = () => <span className="font-normal text-muted-foreground">(optional)</span>

/** The preferences as a form, starting from what's saved (L50); Save Changes sends them,
 * with an empty field as "not given" (null). */
export default function PreferencesForm({ preferences, onSaved, onCancel }) {
  const [form, setForm] = useState(() => ({
    goals: preferences?.goals || '',
    exercise_types: preferences?.exercise_types || '',
    activity_level: preferences?.activity_level || '',
    location: preferences?.location || '',
    age: preferences?.age || '',
    gender: preferences?.gender || '',
    lifestyle: preferences?.lifestyle || '',
  }))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const ageOutOfRange = form.age !== '' && (form.age < 13 || form.age > 120)

  const change = (e) => {
    const { name, value } = e.target
    setForm((prev) => ({ ...prev, [name]: value }))
  }

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    if (form.location && form.location.length > 100) {
      setError('Location must be less than 100 characters')
      return
    }
    setSaving(true)
    try {
      const updated = await api.updateUserPreferences(Object.fromEntries(
        Object.entries(form).map(([key, value]) => [key, value === '' || value === undefined ? null : value])))
      onSaved(updated)
    } catch (err) {
      setError(err.message || 'Failed to update preferences')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit}
          className="flex flex-col gap-5 rounded-xl border bg-card p-5 text-card-foreground shadow-card sm:p-6">
      <ButtonSelector label="Fitness Goals" options={GOALS} value={form.goals}
                      onChange={(value) => setForm((prev) => ({ ...prev, goals: value }))}
                      placeholder="Type other goals (comma-separated)..." />
      <ButtonSelector label="Preferred Exercise Types" options={EXERCISE_TYPES} value={form.exercise_types}
                      onChange={(value) => setForm((prev) => ({ ...prev, exercise_types: value }))}
                      placeholder="Type other exercise types (comma-separated)..." />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field>
          <FieldLabel htmlFor="activity_level">Activity Level</FieldLabel>
          <FieldDescription>The level of fitness activity you want to do</FieldDescription>
          <NativeSelect id="activity_level" name="activity_level" className="w-full" value={form.activity_level} onChange={change}>
            <NativeSelectOption value="">Select activity level</NativeSelectOption>
            {ACTIVITY_LEVELS.map(([v, label]) => <NativeSelectOption key={v} value={v}>{label}</NativeSelectOption>)}
          </NativeSelect>
        </Field>
        <Field data-invalid={ageOutOfRange || undefined}>
          <FieldLabel htmlFor="age">Age <Optional /></FieldLabel>
          <Input id="age" name="age" type="number" inputMode="numeric" min="13" max="120" value={form.age}
                 onChange={change} placeholder="Enter your age" aria-invalid={ageOutOfRange || undefined} />
          {ageOutOfRange && <FieldError>Age must be between 13 and 120</FieldError>}
        </Field>
        <Field>
          <FieldLabel htmlFor="gender">Gender/Sex <Optional /></FieldLabel>
          <NativeSelect id="gender" name="gender" className="w-full" value={form.gender} onChange={change}>
            <NativeSelectOption value="">Select gender/sex</NativeSelectOption>
            {GENDERS.map(([v, label]) => <NativeSelectOption key={v} value={v}>{label}</NativeSelectOption>)}
            <NativeSelectOption value="">Prefer not to say</NativeSelectOption>
          </NativeSelect>
        </Field>
        <Field>
          <FieldLabel htmlFor="lifestyle">Lifestyle <Optional /></FieldLabel>
          <NativeSelect id="lifestyle" name="lifestyle" className="w-full" value={form.lifestyle} onChange={change}>
            <NativeSelectOption value="">Select lifestyle</NativeSelectOption>
            {LIFESTYLES.map(([v, label]) => <NativeSelectOption key={v} value={v}>{label}</NativeSelectOption>)}
          </NativeSelect>
        </Field>
        <Field className="sm:col-span-2">
          <FieldLabel htmlFor="location">Location <Optional /></FieldLabel>
          <Input id="location" name="location" type="text" value={form.location} onChange={change}
                 placeholder="City or location" maxLength={100} />
        </Field>
      </div>
      {error && (
        <Alert variant="destructive">
          <CircleAlert />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={saving}>{saving ? <><Spinner /> Saving…</> : 'Save Changes'}</Button>
        <Button type="button" variant="outline" disabled={saving} onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  )
}
