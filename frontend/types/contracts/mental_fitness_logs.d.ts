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
  warnings?: WriteWarning[]
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
