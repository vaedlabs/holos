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
export default function AnswerEntry({ entry, guest, store, status, onRetry, onSettled }) {
  const view = useMemo(() => (entry.events ? turnView(entry.events) : null), [entry.events])
  const cards = useMemo(() => {
    const decide = guest ? guestCards(store, entry.traceId) : accountCards()
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
