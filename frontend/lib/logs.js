/**
 * An account's logs as the person reads them (D062 B1, B3). The log endpoints send a workout's
 * exercises, a meal's foods and its macros as JSON strings (`str | None`, R9 types them); these
 * read the shapes actually stored, and anything else falls back to a plain name, never raw JSON.
 *
 *   exercises: [{name, sets, reps, duration_s}]
 *   foods:     [{name, portion, calories, protein_g, carbs_g, fat_g}]
 *   macros:    {protein_g, carbs_g, fat_g}
 */

/** A JSON string as a value, or null when it isn't JSON. */
function parsed(text) {
  if (typeof text !== 'string') return text ?? null
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

/** "mindfulness_meditation" as "Mindfulness meditation". */
export function humanize(slug) {
  if (!slug) return ''
  const words = String(slug).replace(/[_-]+/g, ' ').trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

const minutes = (value) => (value ? `${Math.round(value)} min` : null)

/** One exercise's amount: "3 × 8", "30 min" or nothing. */
function amount(exercise) {
  if (exercise.sets && exercise.reps) return `${exercise.sets} × ${exercise.reps}`
  if (exercise.duration_s) return minutes(exercise.duration_s / 60)
  return null
}

/** A workout: its title ("Running"), what was done ("30 min", "3 × 8") and its exercises. */
export function workoutView(log) {
  const list = parsed(log.exercises)
  const exercises = Array.isArray(list) ? list.filter((e) => e && e.name) : []
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

/** A meal: its foods by name ("Rotis, Dal"), the meal, calories and macros. */
export function mealView(log) {
  const list = parsed(log.foods)
  const foods = Array.isArray(list) ? list.filter((f) => f && f.name) : []
  const macros = parsed(log.macros)
  const grams = (key) => (macros && typeof macros[key] === 'number' ? Math.round(macros[key]) : null)
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

/** A practice: its kind ("Mindfulness meditation"), how long, and the mood around it. */
export function practiceView(log) {
  return {
    title: humanize(log.activity_type) || 'Practice',
    detail: minutes(log.duration_minutes) || '',
    mood: log.mood_before && log.mood_after ? `${log.mood_before} → ${log.mood_after}`
      : log.mood_after || log.mood_before || '',
    when: log.activity_date,
    notes: log.notes || '',
  }
}

/** "Mon 23 Nov, 6:59 am" in the person's own zone. */
export function logWhen(iso) {
  const d = new Date(iso)
  const day = d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })
  const time = d.toLocaleTimeString('en-GB', { hour: 'numeric', minute: '2-digit', hour12: true })
  return `${day}, ${time}`
}
