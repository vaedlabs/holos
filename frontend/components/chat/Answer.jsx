// @ts-check
'use client'

import { CircleAlert, Info, RotateCcw } from 'lucide-react'

import CrisisCard from '@/components/CrisisCard'
import { StreamingBlock } from '@/components/ai/StreamingText'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { COACHES, safeLink } from '@/lib/turnView'

import Card, { RepeatCard } from './Card'
import Items, { Caution } from './Items'
import Prose from './Prose'

const FAILED = {
  busy: 'This coach is busy right now.',
  cap_reached: "You've reached today's limit.",
  unavailable: "This coach couldn't answer just now.",
  malformed: "This coach's answer didn't come through.",
}

// Each coach's colour, written out so Tailwind finds the classes
const PILLAR = { physical: 'bg-fitness', nutrition: 'bg-nutrition', mental: 'bg-mind' }

/**
 * One answer (C.5): Holos's own reply, each coach's section in the order it came (text,
 * item tables, sources, cautions, cards), the entries already logged on one card, the
 * summary, notices and helplines. A coach that failed shows Retry only while the answer
 * is live (`onRetry`), never in history. While `live`, each part fades in as it arrives;
 * a crisis reply shows at once, plain (P5.4).
 */
/**
 * @param {{ view: import('@/lib/turnView').TurnView, live?: boolean,
 *   onRetry?: ((agent: string) => void) | null } & import('./Card').Decide} props
 */
export default function Answer({ view, live = false, onRetry, onConfirm, onDiscard }) {
  const moving = live && !view.crisis
  return (
    <div className="flex flex-col gap-5">
      {view.own.map((t, i) => (
        <StreamingBlock key={`own-${i}`} live={moving}><Prose text={t} /></StreamingBlock>
      ))}
      {view.sections.map((s) => (
        <section key={s.agent} aria-label={COACHES[s.agent]} className="flex flex-col gap-2.5">
          <h3 className="m-0 flex items-center gap-2 font-sans text-sm font-semibold text-muted-foreground">
            <span aria-hidden="true" className={`size-2 rounded-full ${PILLAR[s.agent] ?? 'bg-primary'}`} />
            {COACHES[s.agent]}
          </h3>
          {s.error && (
            <div className="flex flex-wrap items-center gap-2 text-sm text-foreground-secondary">
              <CircleAlert aria-hidden="true" className="size-4 text-destructive" />
              <p className="m-0">{FAILED[s.error] || FAILED.unavailable}</p>
              {onRetry && (
                <Button type="button" variant="outline" size="sm" onClick={() => onRetry(s.agent)}>
                  <RotateCcw /> Retry
                </Button>
              )}
            </div>
          )}
          {s.blocks.map((b, i) => (
            <StreamingBlock key={i} live={moving}>
              {b.type === 'text' ? <Prose text={b.text} /> : <Items items={b.items} />}
            </StreamingBlock>
          ))}
          {s.sources.length > 0 && (
            <div className="flex flex-col gap-1">
              <p className="m-0 text-xs font-semibold tracking-wide text-muted-foreground uppercase">Sources</p>
              <ul className="m-0 flex list-none flex-col gap-1 p-0 text-sm">
                {s.sources.map((src) => {
                  const href = safeLink(src.url)
                  return (
                    <li key={src.id}>
                      {href ? (
                        <a href={href} target="_blank" rel="noopener noreferrer nofollow"
                           className="text-primary underline underline-offset-2 hover:no-underline">
                          {src.title}
                        </a>
                      ) : src.title}
                    </li>
                  )
                })}
              </ul>
            </div>
          )}
          {s.warnings.map((w, i) => <Caution key={i}>{w}</Caution>)}
          {s.cards.map((c, i) => (
            <Card key={i} card={c} onConfirm={onConfirm} onDiscard={onDiscard} />
          ))}
        </section>
      ))}
      {view.repeats.length > 0 && (
        <RepeatCard cards={view.repeats} onConfirm={onConfirm} onDiscard={onDiscard} />
      )}
      {view.summary.map((t, i) => (
        <StreamingBlock key={`sum-${i}`} live={moving}>
          <div className="border-l-2 border-primary pl-3"><Prose text={t} /></div>
        </StreamingBlock>
      ))}
      {view.notices.map((n, i) => (
        <Alert key={i}>
          <Info />
          <AlertDescription>{n.message}</AlertDescription>
        </Alert>
      ))}
      {view.crisis && <CrisisCard text={view.crisis.text} helplines={view.crisis.helplines} />}
      {view.error && (
        <Alert variant="destructive">
          <CircleAlert />
          <AlertDescription>{view.error.message}</AlertDescription>
        </Alert>
      )}
    </div>
  )
}
