/**
 * The preferences' choices, shared by onboarding and the preferences page: what is stored, and
 * the words the person sees for it (so the page reads "Very Active", not "very_active").
 */

export const GOALS = ['Build Muscle', 'Lose Weight', 'Lose Fat', 'Gain Strength', 'Improve Flexibility',
                      'Increase Endurance', 'Cardiovascular Health', 'Athletic Performance', 'General Fitness',
                      'Rehabilitation', 'Mental Wellness', 'Inner Peace']

export const EXERCISE_TYPES = ['Calisthenics', 'Weight Lifting', 'Cardio', 'High-Intensity Interval Training', 'Yoga',
                               'Pilates', 'Running', 'Cycling', 'Swimming', 'Powerlifting', 'CrossFit', 'Boxing',
                               'Martial Arts', 'Dancing', 'Stretching']

export const ACTIVITY_LEVELS = [['light', 'Light'], ['moderate', 'Moderate'], ['high', 'High'], ['very_high', 'Very high']]

export const GENDERS = [['XX', 'XX (biological female)'], ['XY', 'XY (biological male)'], ['other', 'Other']]

export const LIFESTYLES = [['sedentary', 'Sedentary'], ['active', 'Active'], ['very_active', 'Very active'],
                           ['athlete', 'Athlete']]

// A goal or exercise type in sentence case, as the rest of the app writes (owner, 25 Nov 2026).
// Only the words shown: what's stored stays "Build Muscle", so saved answers still match
const KEEP_CASE = new Set(['CrossFit'])
export const optionLabel = (option) => (KEEP_CASE.has(option) ? option
  : option.charAt(0) + option.slice(1).toLowerCase())

/** The words for a stored value, or the value itself when it isn't one of the choices. */
export function choiceLabel(choices, value) {
  return choices.find(([v]) => v === value)?.[1] ?? value
}
