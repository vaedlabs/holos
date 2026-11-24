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

export const ACTIVITY_LEVELS = [['light', 'Light'], ['moderate', 'Moderate'], ['high', 'High'], ['very_high', 'Very High']]

export const GENDERS = [['XX', 'XX (Biological Female)'], ['XY', 'XY (Biological Male)'], ['other', 'Other']]

export const LIFESTYLES = [['sedentary', 'Sedentary'], ['active', 'Active'], ['very_active', 'Very Active'],
                           ['athlete', 'Athlete']]

/** The words for a stored value, or the value itself when it isn't one of the choices. */
export function choiceLabel(choices, value) {
  return choices.find(([v]) => v === value)?.[1] ?? value
}
