// Generated from contracts/schema by npm run contracts:types. Don't edit.

export interface MentalFitnessLogs {
  logs: MentalFitnessLogResponse[]
  total: number
}
export interface MentalFitnessLogResponse {
  activity_date: string
  activity_type: string | null
  created_at: string
  duration_minutes: number | null
  id: number
  notes: string | null
  updated_at: string | null
  user_id: number
}
