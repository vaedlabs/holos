'use client'

// Adapted from beautifului.dev "Prompt Bar" (MIT, Copyright (c) 2026 Shane Levine; see LICENSE
// here): the composer as one card, the message above a row of controls. Holos keeps a photo
// button and a "who answers" menu in place of its model picker; its @ sources, / commands and
// dictation are left out (E072).
import { useLayoutEffect, useRef } from 'react'
import { ArrowUp, Camera, ChevronDown, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

const short = (name) => name.replace(/ coach$/, '')

// Browsers without CSS field-sizing (Firefox) get the message box's height from its text instead
const sizesItself = () => typeof CSS !== 'undefined' && CSS.supports?.('field-sizing', 'content')

/** "Auto" when Holos picks, one coach's name, or how many were picked. */
function whoLabel(chosen, coaches) {
  if (chosen.length === 0) return 'Auto'
  if (chosen.length === 1) return short(coaches[chosen[0]])
  return `${chosen.length} coaches`
}

export default function PromptBar({
  value, onChange, onSubmit, sending, photo, onPhoto, onRemovePhoto, coaches, chosen, onChoose,
}) {
  const fileInput = useRef(null)
  const box = useRef(null)
  useLayoutEffect(() => {
    const el = box.current
    if (!el || sizesItself()) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [value])
  const ready = value.trim().length > 0 && !sending
  const submit = (e) => {
    e.preventDefault()
    if (ready) onSubmit()
  }
  const toggle = (agent) => onChoose((prev) => (prev.includes(agent)
    ? prev.filter((a) => a !== agent) : [...prev, agent]))

  return (
    <form onSubmit={submit}
          className="flex flex-col gap-2 rounded-xl border bg-card p-2.5 pl-3.5 shadow-card transition-colors duration-(--duration-fast) focus-within:border-ring">
      {photo && (
        <span className="flex w-fit items-center gap-1 rounded-md bg-raised py-0.5 pr-0.5 pl-2 text-sm text-foreground-secondary">
          Photo ready
          <Button type="button" variant="ghost" size="icon-xs" aria-label="Remove photo" onClick={onRemovePhoto}>
            <X />
          </Button>
        </span>
      )}
      <textarea ref={box} aria-label="Message" rows={2} maxLength={2000} value={value}
                placeholder="A meal, a workout, how you feel…"
                onChange={(e) => onChange(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) submit(e) }}
                className="field-sizing-content max-h-48 min-h-12 w-full resize-none bg-transparent text-(length:--control-text) text-foreground outline-none placeholder:text-muted-foreground md:text-base" />
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <Button type="button" variant="outline" size="icon" aria-label="Add a photo of a meal"
                  onClick={() => fileInput.current?.click()}>
            <Camera />
          </Button>
          <input ref={fileInput} type="file" accept="image/*" hidden onChange={onPhoto} />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button type="button" variant="outline" aria-label={`Who answers: ${whoLabel(chosen, coaches)}`}>
                {whoLabel(chosen, coaches)}
                <ChevronDown />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-64">
              <DropdownMenuLabel>Who answers</DropdownMenuLabel>
              <DropdownMenuCheckboxItem checked={chosen.length === 0} onSelect={(e) => e.preventDefault()}
                                        onCheckedChange={() => onChoose(() => [])}>
                Auto: Holos picks
              </DropdownMenuCheckboxItem>
              <DropdownMenuSeparator />
              {Object.entries(coaches).map(([agent, name]) => (
                <DropdownMenuCheckboxItem key={agent} checked={chosen.includes(agent)}
                                          onSelect={(e) => e.preventDefault()}
                                          onCheckedChange={() => toggle(agent)}>
                  {name}
                </DropdownMenuCheckboxItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <Button type="submit" size="icon" aria-label="Send" disabled={!ready}>
          <ArrowUp />
        </Button>
      </div>
    </form>
  )
}
