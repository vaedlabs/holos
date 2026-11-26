// @ts-check
'use client'

import { useMemo } from 'react'

import LoadingState from '@/components/ai/LoadingState'
import { accountCards, guestCards } from '@/lib/cards'
import { turnView } from '@/lib/turnView'

import Answer from './Answer'

/** One answer: its events through `turnView`, or its text when nothing was kept. While
 * it's coming, the step it's on; never for a crisis reply, which shows at once (P5.4).
 * A card's decision also goes to `onSettled(entryKey, index, state)`, so the chat knows which cards
 * still wait when a newer entry replaces them. */
/**
 * @param {{ entry: import('@/types/app').Entry, guest: boolean,
 *   store: ReturnType<typeof import('@/lib/guestStore').guestStore> | null, status: string,
 *   onRetry?: ((agent: string) => void) | null,
 *   onSettled?: (key: string, index: number | null, state: import('@/lib/turnView').CardState) => void }} props
 */
export default function AnswerEntry({ entry, guest, store, status, onRetry, onSettled }) {
  const view = useMemo(() => (entry.events ? turnView(entry.events) : null), [entry.events])
  const cards = useMemo(() => {
    // A card comes in an event carrying the answer's trace ID, so it's set by the time a card shows
    const decide = guest && store ? guestCards(store, entry.traceId ?? '') : accountCards()
    const told = (action) => async (card, ...rest) => {
      const result = await action(card, ...rest)
      if (result.state) onSettled?.(entry.key, card.index, result.state)
      return result
    }
    return { confirm: told(decide.confirm), discard: told(decide.discard) }
  }, [guest, store, entry.traceId, entry.key, onSettled])
  if (!view) return <p className="m-0 whitespace-pre-wrap">{entry.text}</p>
  return (
    <div className="flex flex-col gap-3">
      <Answer view={view} live={entry.live} onRetry={onRetry} onConfirm={cards.confirm}
              onDiscard={cards.discard} />
      {entry.live && !view.crisis && !view.done && <LoadingState label={status || 'Starting…'} />}
    </div>
  )
}
