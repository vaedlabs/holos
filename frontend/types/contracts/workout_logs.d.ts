// Generated from contracts/schema by npm run contracts:types. Don't edit.

export interface WorkoutLogs {
  logs: WorkoutLogResponse[]
  total: number
}
export interface WorkoutLogResponse {
  created_at: string
  duration_minutes: number | null
  exercise_type: string | null
  exercises: LoggedExerciseView[]
  id: number
  notes: string | null
  updated_at: string | null
  user_id: number
  workout_date: string
}
export interface LoggedExerciseView {
  catalogue_id?: string | null
  duration_s?: number | null
  name: string
  reps?: number | null
  sets?: number | null
}
