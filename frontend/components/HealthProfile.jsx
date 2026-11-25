'use client'

import { useCallback, useEffect, useState } from 'react'
import { Check, CircleAlert, Info, ShieldCheck, TriangleAlert } from 'lucide-react'
import { toast } from 'sonner'

import catalogue from '../../contracts/catalogue.json'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Field, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Textarea } from '@/components/ui/textarea'
import { api, request } from '@/lib/api'

/**
 * The health profile (Plan C.8, P5.3; Part E #42): pickers for what the safety check
 * enforces, and a separate box it can't check. After saving it shows what Holos
 * understood and what it couldn't check, with a picker to say what was meant.
 *
 * An account saves text in the catalogue's own words (`catalogue.json` `save`), which
 * its profile resolution reads back as the same IDs; what someone types beside the
 * pickers is kept as typed. A guest's profile is IDs and notes, in this browser (P5.2).
 */

export const SAMPLES = {
  'Knee injury': { condition_ids: ['knee_ligament_injury'] },
  'Nut allergy': { allergen_tags: ['peanut', 'tree_nut'] },
  Anxiety: { condition_ids: ['anxiety'] },
}
const byName = (list) => Object.fromEntries(list.map((x) => [x.save.toLowerCase(), x.id]))
const CONDITION_BY_SAVE = byName(catalogue.conditions)
const FOOD_BY_SAVE = byName([...catalogue.allergens, ...catalogue.diets])
const NAMES = Object.fromEntries([...catalogue.conditions, ...catalogue.allergens,
                                  ...catalogue.diets].map((x) => [x.id, x.name]))
const split = (text) => (text || '').split(/[,;\n]/).map((s) => s.trim()).filter(Boolean)
const without = (text, phrase) => split(text)
  .filter((p) => p.toLowerCase() !== phrase.toLowerCase()).join(', ')

/** An account's saved text as pickers and what was typed beside them. */
export function readSaved(medical, preferences) {
  const conditions = []
  const otherConditions = []
  for (const part of split(medical?.conditions)) {
    const id = CONDITION_BY_SAVE[part.toLowerCase()]
    if (id) conditions.push(id)
    else otherConditions.push(part)
  }
  const allergens = []
  const diets = []
  const otherFood = []
  const allergenIds = new Set(catalogue.allergens.map((a) => a.id))
  for (const part of split(preferences?.dietary_restrictions)) {
    const id = FOOD_BY_SAVE[part.toLowerCase()]
    if (!id) otherFood.push(part)
    else (allergenIds.has(id) ? allergens : diets).push(id)
  }
  return { conditions, allergens, diets, otherConditions: otherConditions.join(', '),
           otherFood: otherFood.join(', '), limitations: medical?.limitations || '',
           medications: medical?.medications || '', notes: medical?.notes || '' }
}

/** The account's text to save, in the catalogue's words. */
export function toSave(form) {
  const save = (list, ids) => ids.map((id) => list.find((x) => x.id === id).save)
  return {
    medical: {
      conditions: [...save(catalogue.conditions, form.conditions),
                   ...split(form.otherConditions)].join(', '),
      limitations: form.limitations, medications: form.medications, notes: form.notes,
    },
    preferences: {
      dietary_restrictions: [...save(catalogue.allergens, form.allergens),
                             ...save(catalogue.diets, form.diets), ...split(form.otherFood)]
        .join(', '),
    },
  }
}

const EMPTY = { conditions: [], allergens: [], diets: [], otherConditions: '', otherFood: '',
                limitations: '', medications: '', notes: '' }

/** A guest's profile from this browser, as the form's first state. */
function guestForm(store) {
  const p = store?.profile()
  return p ? { ...EMPTY, conditions: p.condition_ids, allergens: p.allergen_tags, diets: p.diet_tags,
               notes: p.notes } : EMPTY
}

export default function HealthProfile({ mode, store, onSaved, onBack }) {
  const account = mode === 'account'
  const [form, setForm] = useState(() => (account ? EMPTY : guestForm(store)))
  const [understood, setUnderstood] = useState(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  // Changed since Holos last checked it: onboarding asks for Save again before Continue
  const [dirty, setDirty] = useState(false)

  const check = useCallback(async (next) => {
    if (account) return setUnderstood(await request('/profile/check'))
    // A guest: the pickers are the profile; the notes are read for what they name
    const fromNotes = next.notes.trim()
      ? await request('/profile/check', { method: 'POST', body: { notes: next.notes } })
      : { conditions: [], allergens: [], diets: [], unchecked: [] }
    return setUnderstood({
      conditions: [...new Set([...next.conditions, ...fromNotes.conditions.map((c) => c.id)])]
        .map((id) => ({ id, name: NAMES[id] || id })),
      allergens: [...new Set([...next.allergens, ...fromNotes.allergens])],
      diets: [...new Set([...next.diets, ...fromNotes.diets])], unchecked: [] })
  }, [account])

  // An account's saved profile, loaded before it can be edited (L50)
  useEffect(() => {
    if (!account) return undefined
    let live = true
    Promise.allSettled([api.getMedicalHistory(), api.getUserPreferences()]).then(([m, p]) => {
      if (!live) return
      setForm(readSaved(m.value, p.value))
      check().catch(() => {})
    })
    return () => { live = false }
  }, [account, check])

  const change = (update) => {
    setDirty(true)
    setForm(update)
  }
  const set = (field) => (e) => change((prev) => ({ ...prev, [field]: e.target.value }))
  const toggle = (field, id) => change((prev) => ({ ...prev, [field]: prev[field].includes(id)
    ? prev[field].filter((x) => x !== id) : [...prev[field], id] }))

  const save = async (e) => {
    e?.preventDefault()
    setSaving(true)
    setError('')
    try {
      if (account) {
        const { medical, preferences } = toSave(form)
        await api.updateMedicalHistory(medical)
        await api.updateUserPreferences(preferences)
      } else {
        await store.setProfile({ condition_ids: form.conditions, allergen_tags: form.allergens,
                                 diet_tags: form.diets, notes: form.notes })
      }
      toast.success('Health profile saved')
      await check(form)
      setDirty(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  /** "Couldn't check: menopause" → the condition they meant, in place of the phrase. */
  const meant = (phrase, id) => change((prev) => ({
    ...prev, conditions: prev.conditions.includes(id) ? prev.conditions : [...prev.conditions, id],
    otherConditions: without(prev.otherConditions, phrase), limitations: without(prev.limitations, phrase),
    otherFood: without(prev.otherFood, phrase) }))

  const sample = (profile) => change({ ...EMPTY, conditions: profile.condition_ids || [],
                                        allergens: profile.allergen_tags || [] })

  return (
    <form className="flex flex-col gap-6" onSubmit={save}>
      {!account && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-foreground-secondary">Try a sample profile:</span>
          {Object.entries(SAMPLES).map(([name, profile]) => (
            <Button key={name} type="button" variant="outline" size="sm" onClick={() => sample(profile)}>
              {name}
            </Button>
          ))}
        </div>
      )}
      <Pickers legend="Health conditions" items={catalogue.conditions} picked={form.conditions}
               onToggle={(id) => toggle('conditions', id)} />
      <Pickers legend="Allergies" items={catalogue.allergens} picked={form.allergens}
               onToggle={(id) => toggle('allergens', id)} />
      <Pickers legend="Diet" items={catalogue.diets} picked={form.diets}
               onToggle={(id) => toggle('diets', id)} />
      {account && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Text id="otherConditions" label="Other conditions or injuries" value={form.otherConditions}
                onChange={set('otherConditions')} />
          <Text id="limitations" label="Physical limitations" value={form.limitations}
                onChange={set('limitations')} />
          <Text id="otherFood" label="Other food restrictions" value={form.otherFood}
                onChange={set('otherFood')} />
          <Text id="medications" label="Medications" value={form.medications}
                onChange={set('medications')} />
        </div>
      )}
      <Text id="notes" label="Anything else" hint="Holos reads this, but can't safety-check it."
            value={form.notes} onChange={set('notes')} textarea />
      {error && (
        <Alert variant="destructive">
          <CircleAlert />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {understood && <Understood view={understood} onMeant={meant} />}
      {onSaved ? (
        // Onboarding: one action at a time. Save shows what Holos understood; once nothing has
        // changed since, it's Continue. Back and the action on the right, as on every step
        <div className="flex flex-col-reverse gap-2.5 sm:flex-row sm:justify-end">
          {onBack && <Button type="button" size="lg" variant="outline" onClick={onBack}>Back</Button>}
          {understood && !dirty
            ? <Button type="button" size="lg" onClick={onSaved}>Continue</Button>
            : <Button type="submit" size="lg" disabled={saving}>{saving ? 'Saving…' : 'Save'}</Button>}
        </div>
      ) : (
        // On the right as on every form; it waits for a change, so it says whether there's
        // anything to save (owner, 25 Nov 2026)
        <div className="flex justify-end">
          <Button type="submit" size="lg" disabled={saving || !dirty}>{saving ? 'Saving…' : 'Save'}</Button>
        </div>
      )}
    </form>
  )
}

function Pickers({ legend, items, picked, onToggle }) {
  return (
    <fieldset className="m-0 flex flex-col gap-2.5 border-0 p-0">
      <legend className="mb-2.5 p-0 text-sm font-medium">{legend}</legend>
      <div className="flex flex-wrap gap-2">
        {items.map((x) => (
          // The theme's chip (app/theme.css)
          <label key={x.id} className="chip">
            <input type="checkbox" className="sr-only" checked={picked.includes(x.id)} onChange={() => onToggle(x.id)} />
            {picked.includes(x.id) && <Check aria-hidden="true" />}
            {x.name}
          </label>
        ))}
      </div>
    </fieldset>
  )
}

function Text({ id, label, hint, value, onChange, textarea }) {
  const Control = textarea ? Textarea : Input
  return (
    <Field>
      {hint ? (
        // The hint opens from an (i) beside the label, outside it so it doesn't focus the box
        // (owner, 25 Nov 2026)
        <div className="flex items-center gap-1">
          <FieldLabel htmlFor={id}>{label}</FieldLabel>
          <Popover>
            <PopoverTrigger asChild>
              <Button type="button" variant="ghost" size="icon-xs" aria-label={`About ${label}`}
                      className="text-muted-foreground">
                <Info />
              </Button>
            </PopoverTrigger>
            <PopoverContent side="top" align="start" className="w-max max-w-80 text-sm text-foreground-secondary">{hint}</PopoverContent>
          </Popover>
        </div>
      ) : <FieldLabel htmlFor={id}>{label}</FieldLabel>}
      <Control id={id} value={value} onChange={onChange} maxLength={textarea ? 1000 : 300} />
    </Field>
  )
}

/** What Holos took from the profile: each kind as checked chips, then what it couldn't check. */
function Understood({ view, onMeant }) {
  const groups = [
    ['Conditions', view.conditions.map((c) => c.name)],
    ['Allergies', view.allergens.map((a) => NAMES[a] || a)],
    ['Diet', view.diets.map((d) => NAMES[d] || d)],
  ].filter(([, names]) => names.length > 0)
  // Medications are always only read, never checked (C.8): no picker for them
  const unclear = view.unchecked.filter((u) => !u.startsWith('medications:'))
  return (
    <section aria-live="polite" aria-labelledby="understood-title"
             className="flex flex-col gap-4 rounded-xl border bg-card p-4 text-card-foreground shadow-card sm:p-5">
      <div className="flex items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary-tint text-primary">
          <ShieldCheck aria-hidden="true" className="size-5" />
        </span>
        <div className="flex flex-col gap-0.5">
          <h2 id="understood-title" className="m-0 font-heading text-base font-semibold">Holos understood</h2>
          <p className="m-0 text-sm text-foreground-secondary">
            {groups.length > 0 ? 'Every plan and meal is checked against these.' : 'Nothing to check yet.'}
          </p>
        </div>
      </div>
      {groups.length > 0 && (
        <dl className="m-0 flex flex-col gap-3">
          {groups.map(([kind, names]) => (
            <div key={kind} className="flex flex-col gap-1.5">
              <dt className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">{kind}</dt>
              <dd className="m-0 flex flex-wrap gap-1.5">
                {names.map((name) => (
                  // The same chip as the pickers above, picked
                  <span key={name} className="chip" data-picked="">
                    <Check aria-hidden="true" />
                    {name}
                  </span>
                ))}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {view.unchecked.length > 0 && (
        <div className="flex flex-col gap-2.5 rounded-lg border border-dashed border-caution/60 p-3">
          <p className="m-0 flex items-center gap-2 text-sm font-medium text-caution">
            <TriangleAlert aria-hidden="true" className="size-4 shrink-0" />
            Holos couldn&apos;t check these
          </p>
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {view.unchecked.map((u) => (
              <li key={u} className="flex flex-wrap items-center gap-2 text-sm">
                <span>&ldquo;{u}&rdquo;</span>
                {unclear.includes(u) && (
                  <NativeSelect aria-label={`What did you mean by ${u}?`} defaultValue=""
                                onChange={(e) => e.target.value && onMeant(u, e.target.value)}>
                    <NativeSelectOption value="">Pick the condition you meant…</NativeSelectOption>
                    {catalogue.conditions.map((c) => <NativeSelectOption key={c.id} value={c.id}>{c.name}</NativeSelectOption>)}
                  </NativeSelect>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
