// @ts-check
'use client'

import { Badge } from '@/components/ui/badge'
import { mealView } from '@/lib/logs'

import LogItem, { LogList } from './LogItem'

/**
 * Meals: calories and protein, carbs and fat, and the foods. With each food's portion listed, the
 * title is the meal ("Breakfast"), so the names aren't said twice; otherwise the names, and the
 * meal as a badge.
 */
/** @param {{ logs: import('@/lib/logs').NutritionLog[], onDelete: (log: import('@/lib/logs').NutritionLog, title: string) => void }} props */
export default function MealLogs({ logs, onDelete }) {
  return (
    <LogList empty="No meals logged yet. Tell the food coach what you ate, or send a photo, and it shows up here.">
      {logs.map((log) => {
        const v = mealView(log)
        const { protein, carbs, fat } = v.macros
        const detail = [v.calories !== null && `${v.calories} kcal`,
                        protein !== null && `protein ${protein} g`, carbs !== null && `carbs ${carbs} g`,
                        fat !== null && `fat ${fat} g`].filter(Boolean).join(' · ')
        const listed = v.foods.some((f) => f.portion)
        return (
          <LogItem key={log.id} warnings={log.warnings} title={listed ? v.meal || 'Meal' : v.title} name={v.title} detail={detail}
                   when={v.when} notes={v.notes} onDelete={() => onDelete(log, v.title)}>
            {!listed && v.meal && <Badge variant="outline" className="text-nutrition">{v.meal}</Badge>}
            {listed && (
              <ul className="m-0 list-none p-0 text-sm text-foreground-secondary">
                {v.foods.map((f, i) => <li key={i}>{f.name}{f.portion && ` · ${f.portion}`}</li>)}
              </ul>
            )}
          </LogItem>
        )
      })}
    </LogList>
  )
}
