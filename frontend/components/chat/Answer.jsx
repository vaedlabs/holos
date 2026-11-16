'use client'

import Card, { RepeatCard } from './Card'
import Items from './Items'
import Prose from './Prose'
import { COACHES, safeLink } from '@/lib/turnView'

const FAILED = {
  busy: 'This coach is busy right now.',
  cap_reached: "You've reached today's limit.",
  unavailable: "This coach couldn't answer just now.",
  malformed: "This coach's answer didn't come through.",
}

/**
 * One answer (C.5): Holos's own reply, each coach's section in the order it came (text,
 * item tables, sources, cautions, cards), the entries already logged on one card, the
 * summary, notices and helplines. A coach that failed shows Retry only while the answer
 * is live (`onRetry`), never in history.
 */
export default function Answer({ view, onRetry, onConfirm, onDiscard }) {
  return (
    <div className="chat-answer">
      {view.own.map((t, i) => <Prose key={`own-${i}`} text={t} />)}
      {view.sections.map((s) => (
        <section key={s.agent} className="chat-section" aria-label={COACHES[s.agent]}>
          <h3 className="chat-section-title">{COACHES[s.agent]}</h3>
          {s.error && (
            <p className="chat-section-error">
              {FAILED[s.error] || FAILED.unavailable}
              {onRetry && (
                <button type="button" className="btn btn-outline" onClick={() => onRetry(s.agent)}>
                  Retry
                </button>
              )}
            </p>
          )}
          {s.blocks.map((b, i) => (b.type === 'text'
            ? <Prose key={i} text={b.text} />
            : <Items key={i} items={b.items} />))}
          {s.sources.length > 0 && (
            <ul className="chat-sources">
              {s.sources.map((src) => {
                const href = safeLink(src.url)
                return (
                  <li key={src.id}>
                    {href ? <a href={href} target="_blank" rel="noopener noreferrer nofollow">{src.title}</a>
                          : src.title}
                  </li>
                )
              })}
            </ul>
          )}
          {s.warnings.map((w, i) => <p key={i} className="chat-caveat">{w}</p>)}
          {s.cards.map((c, i) => (
            <Card key={i} card={c} onConfirm={onConfirm} onDiscard={onDiscard} />
          ))}
        </section>
      ))}
      {view.repeats.length > 0 && (
        <RepeatCard cards={view.repeats} onConfirm={onConfirm} onDiscard={onDiscard} />
      )}
      {view.summary.map((t, i) => (
        <div key={`sum-${i}`} className="chat-summary"><Prose text={t} /></div>
      ))}
      {view.notices.map((n, i) => <p key={i} className="alert alert-info">{n.message}</p>)}
      {view.crisis && (
        <div className="chat-crisis" role="alert">
          <p>{view.crisis.text}</p>
          <ul>
            {view.crisis.helplines.map((h) => (
              <li key={h.name}><strong>{h.name}</strong> ({h.region}): {h.contact}</li>
            ))}
          </ul>
        </div>
      )}
      {view.error && <p className="alert alert-error">{view.error.message}</p>}
    </div>
  )
}
