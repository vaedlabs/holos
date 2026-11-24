'use client'

import { practiceView } from '@/lib/logs'

import LogItem, { LogList } from './LogItem'

/** Practices: the kind, how long, and the mood before and after when it was given. */
export default function PracticeLogs({ logs, onDelete }) {
  return (
    <LogList empty="No practices logged yet. Tell the mental wellbeing coach what you did and it shows up here.">
      {logs.map((log) => {
        const v = practiceView(log)
        return (
          <LogItem key={log.id} title={v.title} detail={v.detail} when={v.when} notes={v.notes}
                   onDelete={() => onDelete(log, v.title)}>
            {v.mood && <p className="m-0 text-sm text-foreground-secondary">Mood: {v.mood}</p>}
          </LogItem>
        )
      })}
    </LogList>
  )
}
