// Generated from contracts/schema by npm run contracts:types. Don't edit.

export interface NutritionLogs {
  logs: NutritionLogResponse[]
  total: number
}
export interface NutritionLogResponse {
  calories: number | null
  created_at: string
  foods: LoggedFoodView[]
  id: number
  macros: MacrosView | null
  meal_date: string
  meal_type: string | null
  notes: string | null
  updated_at: string | null
  user_id: number
  warnings?: WriteWarning[]
}
export interface LoggedFoodView {
  calories?: number | null
  carbs_g?: number | null
  fat_g?: number | null
  name: string
  portion?: string | null
  protein_g?: number | null
}
export interface MacrosView {
  carbs_g?: number | null
  complete?: boolean | null
  fat_g?: number | null
  protein_g?: number | null
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
