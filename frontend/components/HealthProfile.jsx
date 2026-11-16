'use client'

import { useCallback, useEffect, useState } from 'react'

import catalogue from '../../contracts/catalogue.json'
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

export default function HealthProfile({ mode, store, onSaved }) {
  const account = mode === 'account'
  const [form, setForm] = useState(EMPTY)
  const [understood, setUnderstood] = useState(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

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

  useEffect(() => {
    if (account) {
      Promise.allSettled([api.getMedicalHistory(), api.getUserPreferences()]).then(([m, p]) => {
        setForm(readSaved(m.value, p.value))
        check().catch(() => {})
      })
    } else if (store) {
      const p = store.profile()
      if (p) setForm({ ...EMPTY, conditions: p.condition_ids, allergens: p.allergen_tags,
                       diets: p.diet_tags, notes: p.notes })
    }
  }, [account, store, check])

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }))
  const toggle = (field, id) => setForm((f) => ({ ...f, [field]: f[field].includes(id)
    ? f[field].filter((x) => x !== id) : [...f[field], id] }))

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
      await check(form)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  /** "Couldn't check: menopause" → the condition they meant, in place of the phrase. */
  const meant = (phrase, id) => setForm((f) => ({
    ...f, conditions: f.conditions.includes(id) ? f.conditions : [...f.conditions, id],
    otherConditions: without(f.otherConditions, phrase), limitations: without(f.limitations, phrase),
    otherFood: without(f.otherFood, phrase) }))

  const sample = (profile) => setForm({ ...EMPTY, conditions: profile.condition_ids || [],
                                        allergens: profile.allergen_tags || [] })

  return (
    <form className="health-profile" onSubmit={save}>
      {!account && (
        <div className="health-samples">
          <span>Try a sample profile:</span>
          {Object.entries(SAMPLES).map(([name, profile]) => (
            <button key={name} type="button" className="btn btn-outline" onClick={() => sample(profile)}>
              {name}
            </button>
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
        <>
          <Text id="otherConditions" label="Other conditions or injuries" value={form.otherConditions}
                onChange={set('otherConditions')} />
          <Text id="limitations" label="Physical limitations" value={form.limitations}
                onChange={set('limitations')} />
          <Text id="otherFood" label="Other food restrictions" value={form.otherFood}
                onChange={set('otherFood')} />
          <Text id="medications" label="Medications" value={form.medications}
                onChange={set('medications')} />
        </>
      )}
      <Text id="notes" label="Anything else (Holos reads this, but can't safety-check it)"
            value={form.notes} onChange={set('notes')} textarea />
      {error && <p className="alert alert-error">{error}</p>}
      <button type="submit" className="btn btn-primary" disabled={saving}>
        {saving ? 'Saving…' : 'Save'}
      </button>
      {understood && <Understood view={understood} onMeant={meant} />}
      {understood && onSaved && ( /* onboarding: see what Holos understood, then go on */
        <button type="button" className="btn btn-primary" onClick={onSaved}>Continue</button>
      )}
    </form>
  )
}

function Pickers({ legend, items, picked, onToggle }) {
  return (
    <fieldset className="health-pickers">
      <legend>{legend}</legend>
      {items.map((x) => (
        <label key={x.id} className={picked.includes(x.id) ? 'picked' : ''}>
          <input type="checkbox" checked={picked.includes(x.id)} onChange={() => onToggle(x.id)} />
          {x.name}
        </label>
      ))}
    </fieldset>
  )
}

function Text({ id, label, value, onChange, textarea }) {
  const Field = textarea ? 'textarea' : 'input'
  return (
    <div className="form-group">
      <label htmlFor={id} className="form-label">{label}</label>
      <Field id={id} className={textarea ? 'form-textarea' : 'form-input'} value={value}
             onChange={onChange} maxLength={textarea ? 1000 : 300} />
    </div>
  )
}

function Understood({ view, onMeant }) {
  const found = [...view.conditions.map((c) => c.name),
                 ...view.allergens.map((a) => NAMES[a] || a), ...view.diets.map((d) => NAMES[d] || d)]
  // Medications are always only read, never checked (C.8): no picker for them
  const unclear = view.unchecked.filter((u) => !u.startsWith('medications:'))
  return (
    <div className="health-understood" aria-live="polite">
      <p><strong>Holos understood:</strong>{' '}
        {found.length ? found.map((n) => `${n} ✓`).join(', ') : 'nothing to check yet'}</p>
      {view.unchecked.length > 0 && (
        <div className="health-unchecked">
          <p><strong>Holos couldn&apos;t check:</strong></p>
          <ul>
            {view.unchecked.map((u) => (
              <li key={u}>
                &ldquo;{u}&rdquo;
                {unclear.includes(u) && (
                  <select aria-label={`What did you mean by ${u}?`} defaultValue=""
                          onChange={(e) => e.target.value && onMeant(u, e.target.value)}>
                    <option value="">Pick the condition you meant…</option>
                    {catalogue.conditions.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
