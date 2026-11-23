import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

import { checkContrast, checkLiterals, contrast, findLiterals } from '../../scripts/check_theme.mjs'

const theme = readFileSync(fileURLToPath(new URL('../../app/theme.css', import.meta.url)), 'utf8')

describe('check_theme', () => {
  it('passes the real theme in both modes', () => {
    const { failures, rows } = checkContrast(theme)
    expect(failures).toEqual([])
    expect(rows.some((r) => r.mode === 'dark')).toBe(true)
  })

  it('measures contrast the WCAG way', () => {
    expect(contrast('#000000', '#FFFFFF')).toBeCloseTo(21, 5)
    expect(contrast('#777777', '#FFFFFF')).toBeCloseTo(4.48, 2)
  })

  it('fails a planted low-contrast text colour, naming the mode and pair', () => {
    const planted = theme.replace('--sage-600: #5D6963;', '--sage-600: #B0B8B3;')
    const { failures } = checkContrast(planted)
    expect(failures.some((f) => f.startsWith('light: --muted-foreground on --background'))).toBe(true)
    expect(failures.some((f) => f.startsWith('dark:'))).toBe(false)
  })

  it('fails a role that is not a resolvable colour', () => {
    const planted = theme.replace('--primary: light-dark(var(--teal-700), var(--green-400));', '--primary: light-dark(var(--teal-700), var(--nope));')
    expect(checkContrast(planted).failures.some((f) => f.includes('--nope is not defined'))).toBe(true)
  })

  it('finds colour literals but not ids or anchors', () => {
    expect(findLiterals('color: #0F766E; background: rgb(0 0 0 / .5)').map((h) => h.match)).toEqual(['#0F766E', 'rgb('])
    expect(findLiterals('className="bg-[#fff] text-primary"').map((h) => h.match)).toEqual(['#fff'])
    expect(findLiterals('<a href="#main">skip</a> {"#" + id}')).toEqual([])
  })

  it('fails a planted literal in a new file, and only counts legacy ones', () => {
    const root = mkdtempSync(join(tmpdir(), 'check-theme-'))
    for (const dir of ['app', 'components/chat', 'hooks', 'lib']) mkdirSync(join(root, dir), { recursive: true })
    writeFileSync(join(root, 'app/theme.css'), ':root { --white: #FFFFFF; }')
    writeFileSync(join(root, 'components/New.jsx'), 'export const X = () => <div style={{ color: "#ff0000" }} />')
    writeFileSync(join(root, 'components/chat/Card.jsx'), 'const old = "rgba(0,0,0,.5)"')
    const { failures, legacyHits } = checkLiterals(root, new Set(['components/chat/Card.jsx']))
    expect(failures).toEqual(['components/New.jsx:1 colour literal #ff0000 (use a role from app/theme.css)'])
    expect(legacyHits).toBe(1)
  })

  it('finds named colours where a colour is set, and only there', () => {
    expect(findLiterals("<div style={{ color: 'white', backgroundColor: \"navy\" }} />").map((h) => h.match)).toEqual(['white', 'navy'])
    expect(findLiterals('.x { border: 1px solid black; }').map((h) => h.match)).toEqual(['black'])
    expect(findLiterals("color: 'currentColor'; background: transparent; fill: inherit")).toEqual([])
    expect(findLiterals('const label = "Green tea, white rice"')).toEqual([])
  })

  it('fails a stale legacy entry, and a leftover legacy.css once the list is empty', () => {
    const root = mkdtempSync(join(tmpdir(), 'check-theme-'))
    for (const dir of ['app', 'components', 'hooks', 'lib']) mkdirSync(join(root, dir), { recursive: true })
    writeFileSync(join(root, 'app/legacy.css'), '')
    expect(checkLiterals(root, new Set(['components/Gone.jsx'])).failures).toEqual([
      'components/Gone.jsx is in LEGACY but no longer exists: remove it from the list',
    ])
    expect(checkLiterals(root, new Set()).failures).toEqual(['app/legacy.css still exists: R7 deletes it'])
  })
})
