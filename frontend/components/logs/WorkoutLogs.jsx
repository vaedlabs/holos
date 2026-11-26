// @ts-check
'use client'

import { humanize, workoutView } from '@/lib/logs'

import LogItem, { LogList } from './LogItem'

/**
 * Workouts: what was done ("Running · 30 min", "Deadlift · 3 × 8"); with several exercises listed,
 * the title is the workout's kind, so the names aren't said twice.
 */
/** @param {{ logs: import('@/lib/logs').WorkoutLog[], onDelete: (log: import('@/lib/logs').WorkoutLog, title: string) => void }} props */
export default function WorkoutLogs({ logs, onDelete }) {
  return (
    <LogList empty="No workouts logged yet. Tell the exercise coach what you did and it shows up here.">
      {logs.map((log) => {
        const v = workoutView(log)
        return (
          <LogItem key={log.id} title={v.exercises.length > 0 ? humanize(log.exercise_type) || 'Workout' : v.title}
                   name={v.title} detail={v.detail} when={v.when} notes={v.notes}
                   onDelete={() => onDelete(log, v.title)}>
            {v.exercises.length > 0 && (
              <ul className="m-0 list-none p-0 text-sm text-foreground-secondary">
                {v.exercises.map((e, i) => (
                  <li key={i}>{e.name}{e.amount && <span className="tabular-nums"> · {e.amount}</span>}</li>
                ))}
              </ul>
            )}
          </LogItem>
        )
      })}
    </LogList>
  )
}
