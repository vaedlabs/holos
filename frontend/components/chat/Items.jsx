'use client'

import { byDay } from '@/lib/turnView'

/**
 * A coach's items (P5.3): a plan over several days is a table by day, a single session a
 * list. Each row is what the coach gave and the gate kept: its text (`display`), its note,
 * and the cautions the gate added.
 */
export default function Items({ items }) {
  const days = byDay(items)
  if (days.length === 1 && !days[0].day) {
    return (
      <ul className="chat-items">
        {items.map((item, i) => (
          <li key={i}>
            <span className="chat-item-name">{item.display}</span>
            <Detail item={item} />
          </li>
        ))}
      </ul>
    )
  }
  return (
    <table className="chat-table">
      <thead>
        <tr><th>Day</th><th>What</th><th>How</th></tr>
      </thead>
      <tbody>
        {days.flatMap(({ day, items: rows }) => rows.map((item, i) => (
          <tr key={`${day}-${i}`}>
            {i === 0 && <th scope="row" rowSpan={rows.length}>{day || '—'}</th>}
            <td>{item.display}</td>
            <td><Detail item={item} /></td>
          </tr>
        )))}
      </tbody>
    </table>
  )
}

function Detail({ item }) {
  return (
    <>
      {item.note && <span className="chat-item-note">{item.note}</span>}
      {item.caveats.map((c, i) => <span key={i} className="chat-caveat">{c}</span>)}
    </>
  )
}
