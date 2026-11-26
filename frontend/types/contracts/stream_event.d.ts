// Generated from contracts/schema by npm run contracts:types. Don't edit.

export type StreamEvent =
  | AcceptedEvent
  | StepEvent
  | SectionStartEvent
  | ItemEvent
  | TextEvent
  | SourcesEvent
  | SectionEndEvent
  | PendingWriteEvent
  | CommittedEvent
  | LoggedNoteEvent
  | CrisisEvent
  | NoticeEvent
  | ErrorEvent
  | DoneEvent
export type ExerciseId =
  | 'back_squat'
  | 'front_squat'
  | 'goblet_squat'
  | 'bodyweight_squat'
  | 'sumo_squat'
  | 'split_squat'
  | 'pistol_squat'
  | 'hack_squat'
  | 'jump_squat'
  | 'cossack_squat'
  | 'wall_sit'
  | 'forward_lunge'
  | 'reverse_lunge'
  | 'walking_lunge'
  | 'lateral_lunge'
  | 'jumping_lunge'
  | 'step_up'
  | 'leg_press'
  | 'leg_extension'
  | 'leg_curl'
  | 'nordic_curl'
  | 'deadlift'
  | 'romanian_deadlift'
  | 'sumo_deadlift'
  | 'trap_bar_deadlift'
  | 'good_morning'
  | 'hip_thrust'
  | 'glute_bridge'
  | 'single_leg_glute_bridge'
  | 'calf_raise'
  | 'seated_calf_raise'
  | 'clamshell'
  | 'side_lying_leg_raise'
  | 'hip_abduction_machine'
  | 'kettlebell_swing'
  | 'box_jump'
  | 'broad_jump'
  | 'jump_rope'
  | 'jumping_jacks'
  | 'burpee'
  | 'mountain_climber'
  | 'hiit_workout'
  | 'circuit_training'
  | 'bench_press'
  | 'incline_bench_press'
  | 'dumbbell_bench_press'
  | 'push_up'
  | 'knee_push_up'
  | 'incline_push_up'
  | 'dip'
  | 'overhead_press'
  | 'dumbbell_shoulder_press'
  | 'arnold_press'
  | 'lateral_raise'
  | 'front_raise'
  | 'upright_row'
  | 'chest_fly'
  | 'pec_deck'
  | 'skull_crusher'
  | 'overhead_tricep_extension'
  | 'tricep_pushdown'
  | 'pull_up'
  | 'chin_up'
  | 'lat_pulldown'
  | 'seated_cable_row'
  | 'bent_over_row'
  | 'dumbbell_row'
  | 'face_pull'
  | 'band_pull_apart'
  | 'bicep_curl'
  | 'hammer_curl'
  | 'wrist_curl'
  | 'shrug'
  | 'farmer_carry'
  | 'plank'
  | 'high_plank'
  | 'side_plank'
  | 'crunch'
  | 'sit_up'
  | 'bicycle_crunch'
  | 'v_up'
  | 'lying_leg_raise'
  | 'hanging_leg_raise'
  | 'russian_twist'
  | 'dead_bug'
  | 'bird_dog'
  | 'ab_wheel_rollout'
  | 'back_extension'
  | 'superman_hold'
  | 'pallof_press'
  | 'walking'
  | 'brisk_walking'
  | 'hiking'
  | 'jogging'
  | 'running'
  | 'interval_running'
  | 'sprinting'
  | 'long_distance_running'
  | 'stair_climbing'
  | 'cycling'
  | 'stationary_cycling'
  | 'spin_class'
  | 'rowing_machine'
  | 'elliptical'
  | 'swimming'
  | 'aqua_aerobics'
  | 'dance_workout'
  | 'yoga_flow'
  | 'sun_salutation'
  | 'downward_dog'
  | 'childs_pose'
  | 'cat_cow'
  | 'hamstring_stretch'
  | 'quad_stretch'
  | 'hip_flexor_stretch'
  | 'chest_doorway_stretch'
  | 'neck_mobility'
  | 'foam_rolling'
  | 'tai_chi'
  | 'pilates_mat'
  | 'headstand'
  | 'shoulder_stand'
  | 'handstand'
  | 'neck_bridge'
  | 'badminton'
  | 'tennis'
  | 'table_tennis'
  | 'squash'
  | 'pickleball'
  | 'padel'
  | 'cricket'
  | 'football'
  | 'basketball'
  | 'volleyball'
  | 'kabaddi'
  | 'kho_kho'
  | 'field_hockey'
  | 'rugby'
  | 'american_football'
  | 'baseball'
  | 'handball'
  | 'ultimate_frisbee'
  | 'boxing'
  | 'kickboxing'
  | 'martial_arts'
  | 'wrestling'
  | 'golf'
  | 'climbing'
  | 'skating'
  | 'skiing'
  | 'surfing'
  | 'kayaking'
  | 'horse_riding'
/**
 * Allergen tags (Plan C.3).
 */
export type Allergen =
  | 'peanut'
  | 'tree_nut'
  | 'milk'
  | 'egg'
  | 'fish'
  | 'crustacean'
  | 'mollusc'
  | 'soy'
  | 'gluten'
  | 'sesame'
  | 'mustard'
  | 'celery'
  | 'lupin'
  | 'sulphites'
/**
 * Diet tags a profile can carry (Plan C.3).
 */
export type Diet =
  | 'vegan'
  | 'vegetarian'
  | 'eggetarian'
  | 'jain'
  | 'halal'
  | 'kosher'
  | 'pescatarian'
  | 'lactose_free'
export type PracticeId =
  | 'box_breathing'
  | 'breathing_4_7_8'
  | 'breath_retention'
  | 'wim_hof_breathing'
  | 'kapalbhati'
  | 'bhastrika'
  | 'diaphragmatic_breathing'
  | 'coherent_breathing'
  | 'extended_exhale_breathing'
  | 'alternate_nostril_breathing'
  | 'bhramari'
  | 'mindfulness_meditation'
  | 'body_scan'
  | 'loving_kindness_meditation'
  | 'guided_imagery'
  | 'yoga_nidra'
  | 'mantra_meditation'
  | 'trataka'
  | 'walking_meditation'
  | 'progressive_muscle_relaxation'
  | 'grounding_54321'
  | 'self_compassion_break'
  | 'gratitude_journaling'
  | 'expressive_journaling'
  | 'thought_record'
  | 'scheduled_worry_time'
  | 'sleep_wind_down'
/**
 * A catalogue ID. Only when nothing in the catalogue fits what they did: 'other_activity', with its name in `activity`; never in place of an entry that fits.
 */
export type LoggedExerciseId =
  | 'back_squat'
  | 'front_squat'
  | 'goblet_squat'
  | 'bodyweight_squat'
  | 'sumo_squat'
  | 'split_squat'
  | 'pistol_squat'
  | 'hack_squat'
  | 'jump_squat'
  | 'cossack_squat'
  | 'wall_sit'
  | 'forward_lunge'
  | 'reverse_lunge'
  | 'walking_lunge'
  | 'lateral_lunge'
  | 'jumping_lunge'
  | 'step_up'
  | 'leg_press'
  | 'leg_extension'
  | 'leg_curl'
  | 'nordic_curl'
  | 'deadlift'
  | 'romanian_deadlift'
  | 'sumo_deadlift'
  | 'trap_bar_deadlift'
  | 'good_morning'
  | 'hip_thrust'
  | 'glute_bridge'
  | 'single_leg_glute_bridge'
  | 'calf_raise'
  | 'seated_calf_raise'
  | 'clamshell'
  | 'side_lying_leg_raise'
  | 'hip_abduction_machine'
  | 'kettlebell_swing'
  | 'box_jump'
  | 'broad_jump'
  | 'jump_rope'
  | 'jumping_jacks'
  | 'burpee'
  | 'mountain_climber'
  | 'hiit_workout'
  | 'circuit_training'
  | 'bench_press'
  | 'incline_bench_press'
  | 'dumbbell_bench_press'
  | 'push_up'
  | 'knee_push_up'
  | 'incline_push_up'
  | 'dip'
  | 'overhead_press'
  | 'dumbbell_shoulder_press'
  | 'arnold_press'
  | 'lateral_raise'
  | 'front_raise'
  | 'upright_row'
  | 'chest_fly'
  | 'pec_deck'
  | 'skull_crusher'
  | 'overhead_tricep_extension'
  | 'tricep_pushdown'
  | 'pull_up'
  | 'chin_up'
  | 'lat_pulldown'
  | 'seated_cable_row'
  | 'bent_over_row'
  | 'dumbbell_row'
  | 'face_pull'
  | 'band_pull_apart'
  | 'bicep_curl'
  | 'hammer_curl'
  | 'wrist_curl'
  | 'shrug'
  | 'farmer_carry'
  | 'plank'
  | 'high_plank'
  | 'side_plank'
  | 'crunch'
  | 'sit_up'
  | 'bicycle_crunch'
  | 'v_up'
  | 'lying_leg_raise'
  | 'hanging_leg_raise'
  | 'russian_twist'
  | 'dead_bug'
  | 'bird_dog'
  | 'ab_wheel_rollout'
  | 'back_extension'
  | 'superman_hold'
  | 'pallof_press'
  | 'walking'
  | 'brisk_walking'
  | 'hiking'
  | 'jogging'
  | 'running'
  | 'interval_running'
  | 'sprinting'
  | 'long_distance_running'
  | 'stair_climbing'
  | 'cycling'
  | 'stationary_cycling'
  | 'spin_class'
  | 'rowing_machine'
  | 'elliptical'
  | 'swimming'
  | 'aqua_aerobics'
  | 'dance_workout'
  | 'yoga_flow'
  | 'sun_salutation'
  | 'downward_dog'
  | 'childs_pose'
  | 'cat_cow'
  | 'hamstring_stretch'
  | 'quad_stretch'
  | 'hip_flexor_stretch'
  | 'chest_doorway_stretch'
  | 'neck_mobility'
  | 'foam_rolling'
  | 'tai_chi'
  | 'pilates_mat'
  | 'headstand'
  | 'shoulder_stand'
  | 'handstand'
  | 'neck_bridge'
  | 'badminton'
  | 'tennis'
  | 'table_tennis'
  | 'squash'
  | 'pickleball'
  | 'padel'
  | 'cricket'
  | 'football'
  | 'basketball'
  | 'volleyball'
  | 'kabaddi'
  | 'kho_kho'
  | 'field_hockey'
  | 'rugby'
  | 'american_football'
  | 'baseball'
  | 'handball'
  | 'ultimate_frisbee'
  | 'boxing'
  | 'kickboxing'
  | 'martial_arts'
  | 'wrestling'
  | 'golf'
  | 'climbing'
  | 'skating'
  | 'skiing'
  | 'surfing'
  | 'kayaking'
  | 'horse_riding'
  | 'other_activity'

export interface AcceptedEvent {
  data: AcceptedData
  event: 'accepted'
}
export interface AcceptedData {
  contract_version: number
  mode: 'guest' | 'account'
  seq: number
  trace_id: string
}
export interface StepEvent {
  data: StepData
  event: 'step'
}
export interface StepData {
  agent?: ('physical' | 'nutrition' | 'mental') | null
  detail?: string | null
  name:
    | 'admitted'
    | 'routed'
    | 'agent_started'
    | 'tool_call'
    | 'gate'
    | 'retry'
    | 'composing'
    | 'still_working'
  seq: number
  trace_id: string
}
export interface SectionStartEvent {
  data: SectionStartData
  event: 'section_start'
}
export interface SectionStartData {
  agent: 'physical' | 'nutrition' | 'mental'
  kind: 'plan' | 'answer' | 'log_ack' | 'clarify'
  seq: number
  trace_id: string
}
export interface ItemEvent {
  data: ItemData
  event: 'item'
}
export interface ItemData {
  agent: 'physical' | 'nutrition' | 'mental'
  caveats?: string[]
  display: string
  item: ExerciseItem | FoodItem | PracticeItem
  seq: number
  trace_id: string
}
export interface ExerciseItem {
  catalogue_id: ExerciseId
  /**
   * Only in a plan over several days: the day or meal this item belongs to, for example 'Mon', 'Day 2', 'Daily' or 'Tue lunch'; null otherwise.
   */
  day: string | null
  /**
   * Seconds. At most 5400 (90 minutes), except walking, hiking, jogging, running, cycling, rowing, elliptical, swimming, cricket, baseball, golf, climbing, skiing, kayaking, horse riding and other activities, which may be longer.
   */
  duration_s: number | null
  intensity: 'low' | 'moderate' | 'high'
  /**
   * At most 120 characters.
   */
  note: string
  reps: number | null
  sets: number | null
}
export interface FoodItem {
  /**
   * @maxItems 14
   */
  allergen_tags: Allergen[]
  calories: number | null
  /**
   * Only in a plan over several days: the day or meal this item belongs to, for example 'Mon', 'Day 2', 'Daily' or 'Tue lunch'; null otherwise.
   */
  day: string | null
  /**
   * @maxItems 8
   */
  diet_tags: Diet[]
  /**
   * 1 to 8 main ingredients, in English, each at most 30 characters.
   *
   * @minItems 1
   * @maxItems 8
   */
  ingredients: [string, ...string[]]
  /**
   * The dish, at most 60 characters.
   */
  name: string
  /**
   * At most 120 characters.
   */
  note: string
  /**
   * At most 80 characters, for example '1 bowl (250 g)' or '2 rotis, 1 cup dal'.
   */
  portion: string
}
export interface PracticeItem {
  catalogue_id: PracticeId
  /**
   * Only in a plan over several days: the day or meal this item belongs to, for example 'Mon', 'Day 2', 'Daily' or 'Tue lunch'; null otherwise.
   */
  day: string | null
  duration_min: number
  /**
   * At most 120 characters.
   */
  note: string
}
export interface TextEvent {
  data: TextData
  event: 'text'
}
/**
 * One coach's text, the multi-coach summary, or neither: Holos's own reply.
 */
export interface TextData {
  agent?: ('physical' | 'nutrition' | 'mental') | null
  chunk: string
  seq: number
  summary?: boolean
  trace_id: string
}
export interface SourcesEvent {
  data: SourcesData
  event: 'sources'
}
export interface SourcesData {
  agent: 'physical' | 'nutrition' | 'mental'
  seq: number
  /**
   * @minItems 1
   * @maxItems 5
   */
  sources: [Source, ...Source[]]
  trace_id: string
}
export interface Source {
  id: string
  title: string
  url: string
}
export interface SectionEndEvent {
  data: SectionEndData
  event: 'section_end'
}
export interface SectionEndData {
  agent: 'physical' | 'nutrition' | 'mental'
  decisions?: Decision[]
  error?: ('busy' | 'cap_reached' | 'unavailable' | 'malformed' | 'service_unavailable') | null
  removed_count: number
  seq: number
  trace_id: string
  warnings?: string[]
}
export interface Decision {
  action: 'allow' | 'warn' | 'block'
  offending_items?: string[]
  reason: string
  rule_id: string
  rules_version: number
}
export interface PendingWriteEvent {
  data: PendingWriteData
  event: 'pending_write'
}
export interface PendingWriteData {
  at: string
  attributes?: string[]
  entry?: StagedWrite | null
  kind?: ('workout' | 'meal' | 'practice') | null
  meal?: ('breakfast' | 'lunch' | 'dinner' | 'snack') | null
  profile_hash?: string | null
  repeat_of?: RepeatOf | null
  seq: number
  summary: string
  time_guessed?: boolean
  trace_id: string
  warnings?: string[]
  write_id?: string | null
}
export interface StagedWrite {
  args: LogWorkoutArgs | LogMealArgs | LogPracticeArgs
  at?: string | null
  kind: 'workout' | 'meal' | 'practice'
  repeat_of?: RepeatOf | null
  time_guessed?: boolean
  /**
   * @maxItems 20
   */
  warnings?: WriteWarning[]
}
export interface LogWorkoutArgs {
  /**
   * Only with 'other_activity': what they did, in a few of their words, such as 'Archery'; null otherwise.
   */
  activity: string | null
  catalogue_id: LoggedExerciseId
  /**
   * Seconds. At most 5400 (90 minutes), except walking, hiking, jogging, running, cycling, rowing, elliptical, swimming, cricket, baseball, golf, climbing, skiing, kayaking, horse riding and other activities, which may be longer.
   */
  duration_s: number | null
  note: string
  reps: number | null
  sets: number | null
  when: When
}
/**
 * When it happened, copied from what the person said: 'this morning' is today and morning, 'yesterday at 7' is yesterday and 7:00, 'kal raat' is yesterday and night. Every field null when they mean just now ('abhi', 'just now', 'just got back') or say nothing about when; never add a part of the day they didn't name.
 */
export interface When {
  /**
   * 'am' or 'pm' only when the person said which; null otherwise.
   */
  ampm: ('am' | 'pm') | null
  /**
   * 'today', 'yesterday', 'tomorrow', a weekday such as 'monday' (always the last one before today, never a coming one), or a date the person gave, as YYYY-MM-DD; null if they said nothing about the day. Copy a coming day as it is: it can't be logged, and the tool says so.
   */
  day: string | null
  /**
   * The part of the day the person named ('this morning', 'kal raat', 'shaam ko'); null if none.
   */
  part: ('morning' | 'afternoon' | 'evening' | 'night') | null
  /**
   * The clock time the person gave, as H:MM ('7:30', '19:30'); null if they gave none. Never guess one.
   */
  time: string | null
}
export interface LogMealArgs {
  /**
   * @minItems 1
   * @maxItems 5
   */
  foods: [LoggedFood, ...LoggedFood[]]
  meal: 'breakfast' | 'lunch' | 'dinner' | 'snack'
  when: When1
}
/**
 * A food in a meal log, with its protein, carbs and fat, so the person can track
 * them (owner, 3 Nov 2026, Part E #44). Plans and photo replies keep FoodItem.
 */
export interface LoggedFood {
  /**
   * @maxItems 14
   */
  allergen_tags: Allergen[]
  calories: number | null
  /**
   * Grams of carbohydrate in this portion, your best estimate; null only if you can't estimate it.
   */
  carbs_g: number | null
  /**
   * Only in a plan over several days: the day or meal this item belongs to, for example 'Mon', 'Day 2', 'Daily' or 'Tue lunch'; null otherwise.
   */
  day: string | null
  /**
   * @maxItems 8
   */
  diet_tags: Diet[]
  /**
   * Grams of fat in this portion, your best estimate; null only if you can't estimate it.
   */
  fat_g: number | null
  /**
   * 1 to 8 main ingredients, in English, each at most 30 characters.
   *
   * @minItems 1
   * @maxItems 8
   */
  ingredients: [string, ...string[]]
  /**
   * The dish, at most 60 characters.
   */
  name: string
  /**
   * At most 120 characters.
   */
  note: string
  /**
   * At most 80 characters, for example '1 bowl (250 g)' or '2 rotis, 1 cup dal'.
   */
  portion: string
  /**
   * Grams of protein in this portion, your best estimate; null only if you can't estimate it.
   */
  protein_g: number | null
}
/**
 * When it happened, copied from what the person said: 'this morning' is today and morning, 'yesterday at 7' is yesterday and 7:00, 'kal raat' is yesterday and night. Every field null when they mean just now ('abhi', 'just now', 'just got back') or say nothing about when; never add a part of the day they didn't name.
 */
export interface When1 {
  /**
   * 'am' or 'pm' only when the person said which; null otherwise.
   */
  ampm: ('am' | 'pm') | null
  /**
   * 'today', 'yesterday', 'tomorrow', a weekday such as 'monday' (always the last one before today, never a coming one), or a date the person gave, as YYYY-MM-DD; null if they said nothing about the day. Copy a coming day as it is: it can't be logged, and the tool says so.
   */
  day: string | null
  /**
   * The part of the day the person named ('this morning', 'kal raat', 'shaam ko'); null if none.
   */
  part: ('morning' | 'afternoon' | 'evening' | 'night') | null
  /**
   * The clock time the person gave, as H:MM ('7:30', '19:30'); null if they gave none. Never guess one.
   */
  time: string | null
}
export interface LogPracticeArgs {
  catalogue_id: PracticeId
  duration_min: number
  note: string
  when: When2
}
/**
 * When it happened, copied from what the person said: 'this morning' is today and morning, 'yesterday at 7' is yesterday and 7:00, 'kal raat' is yesterday and night. Every field null when they mean just now ('abhi', 'just now', 'just got back') or say nothing about when; never add a part of the day they didn't name.
 */
export interface When2 {
  /**
   * 'am' or 'pm' only when the person said which; null otherwise.
   */
  ampm: ('am' | 'pm') | null
  /**
   * 'today', 'yesterday', 'tomorrow', a weekday such as 'monday' (always the last one before today, never a coming one), or a date the person gave, as YYYY-MM-DD; null if they said nothing about the day. Copy a coming day as it is: it can't be logged, and the tool says so.
   */
  day: string | null
  /**
   * The part of the day the person named ('this morning', 'kal raat', 'shaam ko'); null if none.
   */
  part: ('morning' | 'afternoon' | 'evening' | 'night') | null
  /**
   * The clock time the person gave, as H:MM ('7:30', '19:30'); null if they gave none. Never guess one.
   */
  time: string | null
}
/**
 * The entry a new one repeats (C.17, Part E #67): the card names it, and Replace
 * deletes it. `log_id` is the account's row or the guest's stored entry; none for an
 * entry of this same answer, which can't be replaced.
 */
export interface RepeatOf {
  at: string
  log_id?: string | null
  summary: string
  this_turn?: boolean
}
/**
 * What in a logged entry conflicts with the profile, kept with the log row (owner,
 * 3 Nov 2026, Part E #45). `conflict`: a rule fired, so the entry waits for the
 * person's confirmation; `unchecked`: ingredients the gate couldn't check, recorded
 * only. `left_out`: the person said at confirm that they didn't have it (the peanuts
 * picked out of the poha).
 */
export interface WriteWarning {
  /**
   * @maxItems 10
   */
  attributes: string[]
  item: string
  kind: 'conflict' | 'unchecked'
  left_out?: boolean
  reason: string
  rule_id: string
}
export interface CommittedEvent {
  data: CommittedData
  event: 'committed'
}
export interface CommittedData {
  seq: number
  trace_id: string
  /**
   * @minItems 1
   */
  writes: [CommittedWrite, ...CommittedWrite[]]
}
export interface CommittedWrite {
  at?: string | null
  entry?: StagedWrite | null
  kind: 'workout' | 'meal' | 'practice'
  summary: string
  warnings?: string[]
  write_id?: string | null
}
export interface LoggedNoteEvent {
  data: LoggedNoteData
  event: 'logged_note'
}
/**
 * After `committed`: one sentence from the coach about what was just saved (owner,
 * Part E #54 B). Optional: when it fails or is late, the record has said it.
 */
export interface LoggedNoteData {
  seq: number
  text: string
  trace_id: string
}
export interface CrisisEvent {
  data: CrisisData
  event: 'crisis'
}
export interface CrisisData {
  /**
   * @minItems 1
   */
  helplines: [Helpline, ...Helpline[]]
  seq: number
  text: string
  trace_id: string
}
export interface Helpline {
  contact: string
  name: string
  region: string
}
export interface NoticeEvent {
  data: NoticeData
  event: 'notice'
}
export interface NoticeData {
  code: 'cap_reached' | 'search_off' | 'partial_result' | 'month_budget_used'
  message: string
  seq: number
  trace_id: string
}
export interface ErrorEvent {
  data: ErrorData
  event: 'error'
}
export interface ErrorData {
  code: string
  message: string
  retry_after?: number | null
  seq: number
  trace_id: string
}
export interface DoneEvent {
  data: DoneData
  event: 'done'
}
export interface DoneData {
  said?: HistoryTurn | null
  seq: number
  trace: TraceView
  trace_id: string
  turn?: HistoryTurn | null
  usage: Usage
}
export interface HistoryTurn {
  agents?: ('physical' | 'nutrition' | 'mental')[] | null
  content: string
  prev?: string | null
  role: 'user' | 'assistant'
  shown?: string | null
  sig?: string | null
  ts: string
}
export interface TraceView {
  /**
   * @maxItems 3
   */
  agents?: ('physical' | 'nutrition' | 'mental')[]
  decisions?: Decision[]
  retries?: number
  route: ('coaching' | 'greeting' | 'meta' | 'off_topic' | 'unclear' | 'other_language') | 'crisis'
  sources?: Source[]
  steps?: TraceStep[]
  tools?: TraceTool[]
  trace_id: string
  usage: Usage
}
export interface TraceStep {
  agent?: ('physical' | 'nutrition' | 'mental') | null
  duration_ms: number
  name: string
  queue_ms: number
  start_ms: number
}
export interface TraceTool {
  args: string
  duration_ms: number
  name: string
  status: 'ok' | 'error' | 'refused' | 'staged' | 'held' | 'unavailable'
}
export interface Usage {
  cost_usd: number
  tokens_in: number
  tokens_out: number
}
