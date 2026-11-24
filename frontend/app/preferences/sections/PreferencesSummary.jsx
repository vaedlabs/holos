'use client'

import { SlidersHorizontal } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { ACTIVITY_LEVELS, GENDERS, LIFESTYLES, choiceLabel } from '@/lib/preferenceOptions'

const FIELDS = [
  ['goals', 'Fitness Goals'],
  ['exercise_types', 'Preferred Exercise Types'],
  ['activity_level', 'Activity Level', ACTIVITY_LEVELS],
  ['age', 'Age'],
  ['gender', 'Gender/Sex', GENDERS],
  ['lifestyle', 'Lifestyle', LIFESTYLES],
  ['location', 'Location'],
]

/** The saved preferences in words, or, with none yet, a way to add them (D062 B4). */
export default function PreferencesSummary({ preferences, onEdit }) {
  const shown = FIELDS.filter(([key]) => preferences?.[key] !== null && preferences?.[key] !== undefined && preferences?.[key] !== '')
  if (shown.length === 0) {
    return (
      <Empty className="border">
        <EmptyHeader>
          <EmptyMedia variant="icon"><SlidersHorizontal /></EmptyMedia>
          <EmptyTitle>No preferences recorded yet.</EmptyTitle>
          <EmptyDescription>Your goals and the training you like help the coaches plan for you.</EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Button type="button" onClick={onEdit}>Add Preferences</Button>
        </EmptyContent>
      </Empty>
    )
  }
  return (
    <div className="flex flex-col gap-4 rounded-xl border bg-card p-5 text-card-foreground shadow-card">
      <dl className="m-0 grid gap-x-6 gap-y-4 sm:grid-cols-2">
        {shown.map(([key, label, choices]) => (
          <div key={key} className="flex flex-col gap-0.5">
            <dt className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">{label}</dt>
            <dd className="m-0">{choices ? choiceLabel(choices, preferences[key]) : String(preferences[key])}</dd>
          </div>
        ))}
      </dl>
      <Button type="button" variant="outline" className="self-start" onClick={onEdit}>Edit</Button>
    </div>
  )
}
