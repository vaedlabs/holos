// @ts-check
/**
 * An account's logs as the person reads them (D062 B1, B3). The log endpoints send a workout's
 * exercises, a meal's foods and its macros as lists and an object (R9, Part E #74), typed from
 * contracts/schema; a name is always there, anything else may be missing.
 *
 * @typedef {import('../types/contracts').WorkoutLogs['logs'][number]} WorkoutLog
 * @typedef {import('../types/contracts').NutritionLogs['logs'][number]} NutritionLog
 * @typedef {import('../types/contracts').MentalFitnessLogs['logs'][number]} PracticeLog
 * @typedef {WorkoutLog['exercises'][number]} Exercise
 * @typedef {NonNullable<NutritionLog['warnings']>[number]} WriteWarning
 */

/**
 * "mindfulness_meditation" as "Mindfulness meditation".
 * @param {string | null | undefined} slug
 */
export function humanize(slug) {
  if (!slug) return ''
  const words = String(slug).replace(/[_-]+/g, ' ').trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

const minutes = (/** @type {number | null | undefined} */ value) => (value ? `${Math.round(value)} min` : null)

/**
 * One exercise's amount, from whatever the person said: "3 × 8", "15 reps", "3 sets", "30 min",
 * or nothing when none was given (owner, 25 Nov 2026: reps alone were dropped).
 * @param {Exercise} exercise
 */
function amount(exercise) {
  const { sets, reps, duration_s: seconds } = exercise
  if (sets && reps) return `${sets} × ${reps}`
  if (reps) return `${reps} ${reps === 1 ? 'rep' : 'reps'}`
  if (sets) return `${sets} ${sets === 1 ? 'set' : 'sets'}`
  if (seconds) return minutes(seconds / 60)
  return null
}

/**
 * A workout: its title ("Running"), what was done ("30 min", "3 × 8") and its exercises.
 * @param {WorkoutLog} log
 */
export function workoutView(log) {
  const exercises = log.exercises
  const title = exercises.length > 0 ? exercises.map((e) => e.name).join(', ')
    : humanize(log.exercise_type) || 'Workout'
  const parts = exercises.length === 1 ? [amount(exercises[0])] : []
  if (exercises.length !== 1 || !exercises[0].duration_s) parts.push(minutes(log.duration_minutes))
  return {
    title,
    detail: parts.filter(Boolean).join(' · '),
    exercises: exercises.length > 1 ? exercises.map((e) => ({ name: e.name, amount: amount(e) })) : [],
    when: log.workout_date,
    notes: log.notes || '',
  }
}

/**
 * A meal: its foods by name ("Rotis, Dal"), the meal, calories and macros.
 * @param {NutritionLog} log
 */
export function mealView(log) {
  const { foods, macros } = log
  const grams = (/** @type {'protein_g' | 'carbs_g' | 'fat_g'} */ key) => {
    const value = macros?.[key]
    return typeof value === 'number' ? Math.round(value) : null
  }
  return {
    title: foods.length > 0 ? foods.map((f) => f.name).join(', ') : humanize(log.meal_type) || 'Meal',
    meal: humanize(log.meal_type),
    calories: typeof log.calories === 'number' ? Math.round(log.calories) : null,
    macros: { protein: grams('protein_g'), carbs: grams('carbs_g'), fat: grams('fat_g') },
    foods: foods.map((f) => ({ name: f.name, portion: f.portion || '' })),
    when: log.meal_date,
    notes: log.notes || '',
  }
}

/**
 * A practice: its kind ("Mindfulness meditation") and how long.
 * @param {PracticeLog} log
 */
export function practiceView(log) {
  return {
    title: humanize(log.activity_type) || 'Practice',
    detail: minutes(log.duration_minutes) || '',
    when: log.activity_date,
    notes: log.notes || '',
  }
}

/**
 * "Mon 23 Nov, 6:59 am" in the person's own zone.
 * @param {string} iso
 */
export function logWhen(iso) {
  const d = new Date(iso)
  const day = d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })
  const time = d.toLocaleTimeString('en-GB', { hour: 'numeric', minute: '2-digit', hour12: true })
  return `${day}, ${time}`
}

/**
 * What a log's stored warnings say (Part E #65 (4)): what the person left out ("Poha · without
 * peanut"), quietly; and the conflicts they confirmed, each once. An unchecked ingredient
 * says nothing: it was recorded, not judged.
 * @param {WriteWarning[] | undefined} warnings
 * @returns {{ without: string[], confirmed: string[] }}
 */
export function warningNotes(warnings = []) {
  const without = warnings.filter((w) => w.left_out)
    .map((w) => `${w.item} · without ${w.attributes.join(', ')}`)
  // As the server words a warning (staging.warning_text), with what fired: the stored reason is
  // the rule's, e.g. "Contains an allergen in your profile"
  const confirmed = warnings.filter((w) => w.kind === 'conflict' && !w.left_out)
    .map((w) => `${w.item}: ${w.reason.charAt(0).toLowerCase()}${w.reason.slice(1)}`
                + (w.attributes.length ? ` (${w.attributes.join(', ')})` : ''))
  return { without: [...new Set(without)], confirmed: [...new Set(confirmed)] }
}
