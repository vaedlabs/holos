'use client'

import { workoutView } from '@/lib/logs'

import LogItem, { LogList } from './LogItem'

/** Workouts: what was done ("Running · 30 min", "Deadlift · 3 × 8"), each exercise when several. */
export default function WorkoutLogs({ logs, onDelete }) {
  return (
    <LogList empty="No workouts logged yet. Tell the exercise coach what you did and it shows up here.">
      {logs.map((log) => {
        const v = workoutView(log)
        return (
          <LogItem key={log.id} title={v.title} detail={v.detail} when={v.when} notes={v.notes}
                   onDelete={() => onDelete(log, v.title)}>
            {v.exercises.length > 0 && (
              <ul className="m-0 list-none p-0 text-sm text-foreground-secondary">
                {v.exercises.map((e, i) => (
                  <li key={i}>{e.name}{e.amount && <span className="font-mono"> · {e.amount}</span>}</li>
                ))}
              </ul>
            )}
          </LogItem>
        )
      })}
    </LogList>
  )
}
