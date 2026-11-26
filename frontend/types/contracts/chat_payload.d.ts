// Generated from contracts/schema by npm run contracts:types. Don't edit.

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

export interface ChatPayload {
  agents?: ['physical' | 'nutrition' | 'mental', ...('physical' | 'nutrition' | 'mental')[]] | null
  client_request_id: string
  contract_version: number
  guest_history?: HistoryTurn[] | null
  guest_logs?:
    | {
        [k: string]: unknown
      }[]
    | null
  guest_profile?: UserProfile | null
  message: string
  timezone?: string | null
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
export interface UserProfile {
  /**
   * @maxItems 14
   */
  allergen_tags: Allergen[]
  /**
   * @maxItems 30
   */
  condition_ids: string[]
  /**
   * @maxItems 8
   */
  diet_tags: Diet[]
  notes: string
}
