'use client'

// The chat's parts replayed from the contract's sample streams (contracts/streams), so a theme
// edit can be checked on a live answer, a held entry, a repeat and a crisis reply with no model
// call. Dev only, inside /styleguide.
import { useEffect, useMemo, useRef, useState } from 'react'
import { Play } from 'lucide-react'

import LoadingState from '@/components/ai/LoadingState'
import PromptBar from '@/components/ai/PromptBar'
import Answer from '@/components/chat/Answer'
import { Button } from '@/components/ui/button'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { COACHES, stepStatus, turnView } from '@/lib/turnView'

const STEP_MS = 280

// No sample stream holds a repeat (C.17, #67), so the preview makes one
const ev = (name, data) => ({ name, data: { seq: 0, trace_id: 'tr_repeat', ...data } })
const repeat = (i, summary, at) => ev('pending_write', {
  kind: 'meal', summary, warnings: [], attributes: [], at, meal: 'lunch', time_guessed: false,
  write_id: `pw_r${i}`, repeat_of: { summary: 'Lunch: Dal, rice', at: '2026-11-23T07:30:00Z', log_id: String(i), this_turn: false } })
const REPEAT = [
  ev('text', { agent: 'nutrition', chunk: 'Dal and rice again: a steady, filling lunch.' }),
  repeat(1, 'Lunch: Dal, rice', '2026-11-23T08:00:00Z'),
  ev('done', {}),
]

// Deciding a card here answers locally: the preview never writes to the server
const confirm = async () => ({ state: 'logged', message: '' })
const discard = async () => ({ state: 'discarded', message: '' })

export default function ChatPreview({ streams }) {
  const all = { ...streams, 'repeat (made here)': REPEAT }
  const names = Object.keys(all)
  const [name, setName] = useState(names.includes('pending_write') ? 'pending_write' : names[0])
  const [shown, setShown] = useState(all[name])
  const [live, setLive] = useState(false)
  const [status, setStatus] = useState('')
  const [draft, setDraft] = useState('')
  const [chosen, setChosen] = useState([])
  const [run, setRun] = useState(0) // each replay starts its cards afresh
  const timer = useRef(null)
  const view = useMemo(() => turnView(shown), [shown])

  useEffect(() => () => clearInterval(timer.current), [])

  const replay = () => {
    clearInterval(timer.current)
    const events = all[name]
    let i = 0
    setShown([])
    setStatus('')
    setRun((prev) => prev + 1)
    setLive(true)
    timer.current = setInterval(() => {
      const event = events[i]
      i += 1
      if (event.name === 'step') setStatus((prev) => stepStatus(prev, event.data.name))
      setShown(() => events.slice(0, i))
      if (i >= events.length) {
        clearInterval(timer.current)
        setLive(false)
      }
    }, STEP_MS)
  }
  const pick = (value) => {
    clearInterval(timer.current)
    setName(value)
    setShown(all[value])
    setLive(false)
  }

  return (
    <div className="flex max-w-chat flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <NativeSelect aria-label="Sample stream" value={name} onChange={(e) => pick(e.target.value)}>
          {names.map((n) => <NativeSelectOption key={n} value={n}>{n}</NativeSelectOption>)}
        </NativeSelect>
        <Button type="button" variant="outline" onClick={replay}><Play /> Replay live</Button>
      </div>
      <div className="flex max-w-[85%] self-end rounded-xl bg-primary-tint px-3.5 py-2.5 text-primary-tint-foreground">
        Had poha with peanuts for breakfast, and a 30 minute run.
      </div>
      <div key={`${name}-${run}`} className="flex flex-col gap-3">
        <Answer view={view} live={live} onRetry={null} onConfirm={confirm} onDiscard={discard} />
        {live && !view.crisis && !view.done && <LoadingState label={status || 'Starting…'} />}
      </div>
      <PromptBar value={draft} onChange={setDraft} onSubmit={() => setDraft('')} sending={false}
                 photo={null} onPhoto={() => {}} onRemovePhoto={() => {}}
                 coaches={COACHES} chosen={chosen} onChoose={setChosen} />
    </div>
  )
}
