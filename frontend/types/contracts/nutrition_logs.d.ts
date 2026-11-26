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
