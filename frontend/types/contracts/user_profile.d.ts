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
