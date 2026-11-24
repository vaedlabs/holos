'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { CircleAlert } from 'lucide-react'

import ButtonSelector from '@/components/ButtonSelector'
import HealthProfile from '@/components/HealthProfile'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Field, FieldDescription, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Progress } from '@/components/ui/progress'
import { Spinner } from '@/components/ui/spinner'
import { useRequireAuth } from '@/hooks/useAuth'
import { api } from '@/lib/api'
import { ACTIVITY_LEVELS, EXERCISE_TYPES, GENDERS, GOALS, LIFESTYLES } from '@/lib/preferenceOptions'

const STEPS = ['Demographics', 'Your health', 'Fitness preferences']

const Optional = () => <span className="font-normal text-muted-foreground">(optional)</span>

export default function OnboardingPage() {
  const router = useRouter()
  const { mounted, isAuthenticated } = useRequireAuth()
  const [step, setStep] = useState(0) // 0: demographics, 1: medical, 2: preferences
  const [demographicsData, setDemographicsData] = useState({ age: '', gender: '', lifestyle: '' })
  const [preferencesData, setPreferencesData] = useState({
    goals: '', exercise_types: '', activity_level: '', location: '',
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  // Saved answers are loaded first, so finishing onboarding again can't overwrite
  // the user's medical history with an empty form
  const [loaded, setLoaded] = useState(false)
  useEffect(() => {
    if (!mounted || !isAuthenticated) return undefined
    let cancelled = false
    api.getUserPreferences().then((p) => {
      if (cancelled || !p) return
      setDemographicsData({ age: p.age ?? '', gender: p.gender || '', lifestyle: p.lifestyle || '' })
      setPreferencesData({ goals: p.goals || '', exercise_types: p.exercise_types || '',
                           activity_level: p.activity_level || '', location: p.location || '' })
    }).catch(() => {}).finally(() => { if (!cancelled) setLoaded(true) })
    return () => { cancelled = true }
  }, [mounted, isAuthenticated])

  if (!mounted || !isAuthenticated) return null

  const ageOutOfRange = demographicsData.age !== '' && (demographicsData.age < 13 || demographicsData.age > 120)

  const handleDemographicsSubmit = (e) => {
    e.preventDefault()
    setError('')
    // Every field is optional, but an age given must be one Holos can plan for
    if (ageOutOfRange) {
      setError('Age must be between 13 and 120')
      return
    }
    setStep(1)
  }

  const handleDemographicsChange = (e) => {
    const { name, value } = e.target
    setDemographicsData((prev) => ({
      ...prev,
      [name]: name === 'age' ? (value === '' ? '' : parseInt(value, 10) || '') : value,
    }))
  }

  const handlePreferencesSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (preferencesData.location && preferencesData.location.length > 100) {
      setError('Location must be less than 100 characters')
      return
    }
    setLoading(true)
    try {
      // A field left empty is "not given" (null), never "" (age can't be "")
      const answers = { ...preferencesData, ...demographicsData }
      await api.updateUserPreferences(Object.fromEntries(
        Object.entries(answers).map(([key, value]) => [key, value === '' ? null : value])))
      router.push('/dashboard')
    } catch (err) {
      setError(err.message || 'Failed to save information. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handlePreferencesChange = (e) => {
    const { name, value } = e.target
    setPreferencesData((prev) => ({ ...prev, [name]: value }))
  }

  const failed = error && (
    <Alert variant="destructive">
      <CircleAlert />
      <AlertDescription>{error}</AlertDescription>
    </Alert>
  )

  return (
    <div className="flex min-h-dvh flex-col items-center px-4 py-10">
      <main className="flex w-full max-w-chat flex-col gap-6">
        <div className="flex flex-col gap-3">
          <span className="font-heading text-xl font-bold tracking-tight">Holos</span>
          <h1 className="m-0 font-heading text-2xl font-bold tracking-tight">Welcome! Let&apos;s set up your profile</h1>
          <p className="m-0 text-sm font-medium text-foreground-secondary">Step {step + 1} of {STEPS.length} · {STEPS[step]}</p>
          <Progress value={((step + 1) / STEPS.length) * 100} aria-label={`Step ${step + 1} of ${STEPS.length}`} />
        </div>

        {!loaded ? (
          <p role="status" className="m-0 text-foreground-secondary">Loading your profile…</p>
        ) : (
          <section className="flex flex-col gap-5 rounded-xl border bg-card p-5 text-card-foreground shadow-card sm:p-6">
            {step === 0 && (
              <>
                <div className="flex flex-col gap-1">
                  <h2 className="m-0 font-heading text-lg font-semibold">Demographics</h2>
                  <p className="m-0 text-foreground-secondary">Tell us a bit about yourself to personalize your experience.</p>
                </div>
                <form onSubmit={handleDemographicsSubmit} className="flex flex-col gap-4">
                  <Field data-invalid={ageOutOfRange || undefined}>
                    <FieldLabel htmlFor="age">Age <Optional /></FieldLabel>
                    <Input id="age" name="age" type="number" inputMode="numeric" min="13" max="120"
                           value={demographicsData.age} onChange={handleDemographicsChange}
                           placeholder="Enter your age" aria-invalid={ageOutOfRange || undefined} />
                    {ageOutOfRange && <FieldError>Age must be between 13 and 120</FieldError>}
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="gender">Gender/Sex <Optional /></FieldLabel>
                    <NativeSelect id="gender" name="gender" className="w-full" value={demographicsData.gender}
                                  onChange={handleDemographicsChange}>
                      <NativeSelectOption value="">Select gender/sex</NativeSelectOption>
                      {GENDERS.map(([v, label]) => <NativeSelectOption key={v} value={v}>{label}</NativeSelectOption>)}
                      <NativeSelectOption value="">Prefer not to say</NativeSelectOption>
                    </NativeSelect>
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="lifestyle">Lifestyle <Optional /></FieldLabel>
                    <FieldDescription>Your daily lifestyle and activity patterns</FieldDescription>
                    <NativeSelect id="lifestyle" name="lifestyle" className="w-full" value={demographicsData.lifestyle}
                                  onChange={handleDemographicsChange}>
                      <NativeSelectOption value="">Select lifestyle</NativeSelectOption>
                      {LIFESTYLES.map(([v, label]) => <NativeSelectOption key={v} value={v}>{label}</NativeSelectOption>)}
                    </NativeSelect>
                  </Field>
                  {failed}
                  <Button type="submit" size="lg" className="w-full sm:w-auto sm:self-end">Next</Button>
                </form>
              </>
            )}

            {step === 1 && (
              <>
                <div className="flex flex-col gap-1">
                  <h2 className="m-0 font-heading text-lg font-semibold">Your health</h2>
                  <p className="m-0 text-foreground-secondary">This information helps us recommend safe exercises for you.</p>
                </div>
                <HealthProfile mode="account" onSaved={() => setStep(2)} />
              </>
            )}

            {step === 2 && (
              <>
                <div className="flex flex-col gap-1">
                  <h2 className="m-0 font-heading text-lg font-semibold">Fitness Preferences</h2>
                  <p className="m-0 text-foreground-secondary">Tell us about your fitness goals and preferences.</p>
                </div>
                <form onSubmit={handlePreferencesSubmit} className="flex flex-col gap-5">
                  <ButtonSelector label="Fitness Goals" options={GOALS} value={preferencesData.goals}
                                  onChange={(value) => setPreferencesData((prev) => ({ ...prev, goals: value }))}
                                  placeholder="Type other goals (comma-separated)..." />
                  <ButtonSelector label="Preferred Exercise Types" options={EXERCISE_TYPES}
                                  value={preferencesData.exercise_types}
                                  onChange={(value) => setPreferencesData((prev) => ({ ...prev, exercise_types: value }))}
                                  placeholder="Type other exercise types (comma-separated)..." />
                  <Field>
                    <FieldLabel htmlFor="activity_level">Activity Level</FieldLabel>
                    <FieldDescription>The level of fitness activity you want to do</FieldDescription>
                    <NativeSelect id="activity_level" name="activity_level" className="w-full"
                                  value={preferencesData.activity_level} onChange={handlePreferencesChange}>
                      <NativeSelectOption value="">Select activity level</NativeSelectOption>
                      {ACTIVITY_LEVELS.map(([v, label]) => <NativeSelectOption key={v} value={v}>{label}</NativeSelectOption>)}
                    </NativeSelect>
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="location">Location <Optional /></FieldLabel>
                    <Input id="location" name="location" type="text" value={preferencesData.location}
                           onChange={handlePreferencesChange} placeholder="City or address" maxLength={100} />
                  </Field>
                  {failed}
                  <div className="grid grid-cols-[1fr_2fr] gap-2.5">
                    <Button type="button" size="lg" variant="outline" onClick={() => setStep(1)}>Back</Button>
                    <Button type="submit" size="lg" disabled={loading}>
                      {loading ? <><Spinner /> Saving…</> : 'Complete Setup'}
                    </Button>
                  </div>
                </form>
              </>
            )}
          </section>
        )}
      </main>
    </div>
  )
}
