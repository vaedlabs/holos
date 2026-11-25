'use client'

import { practiceView } from '@/lib/logs'

import LogItem, { LogList } from './LogItem'

/**
 * Practices: the kind, how long, and the note. The mood before and after isn't shown: the coach
 * guessed it from the words, and the mood rating is to go altogether (owner, 25 Nov 2026).
 */
export default function PracticeLogs({ logs, onDelete }) {
  return (
    <LogList empty="No practices logged yet. Tell the mental wellbeing coach what you did and it shows up here.">
      {logs.map((log) => {
        const v = practiceView(log)
        return (
          <LogItem key={log.id} title={v.title} detail={v.detail} when={v.when} notes={v.notes}
                   onDelete={() => onDelete(log, v.title)} />
        )
      })}
    </LogList>
  )
}
