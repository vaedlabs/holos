// CI guard for the theme file (R7, E072):
//   1. no colour literal outside app/theme.css, so every colour goes through a role;
//   2. every text role reaches WCAG AA on the surfaces it sits on, in light and in dark.
// Usage: node scripts/check_theme.mjs (exit 1 on a failure). The checks are exported for the tests.
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = fileURLToPath(new URL('..', import.meta.url))
const THEME = 'app/theme.css'
const SCANNED_DIRS = ['app', 'components', 'hooks', 'lib']
const SCANNED_EXT = /\.(js|jsx|mjs|css)$/

// Files allowed colour literals while R7 rebuilt them; R7 ended with none, and app/legacy.css deleted.
// Keep it empty: a new colour goes in theme.css.
export const LEGACY = new Set([])

// Hex colours, CSS colour functions, and Tailwind arbitrary colours like bg-[#fff]
const LITERAL = /(?<![\w&/-])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b|\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(/g

// Named colours where a colour is set: a CSS declaration or a style={{ }} property. transparent,
// currentColor and inherit name no colour, so they pass.
const NAMED = 'black|white|red|green|blue|yellow|orange|purple|pink|gray|grey|silver|maroon|navy|teal|olive|lime|aqua|cyan|magenta|fuchsia|brown|gold|indigo|violet|crimson|coral|salmon|tomato|khaki|beige|ivory|lavender|turquoise|tan|plum|orchid|chocolate|firebrick|darkred|darkblue|darkgreen|darkgray|darkgrey|lightgray|lightgrey|lightblue|lightgreen|whitesmoke|gainsboro|slategray|slategrey|dimgray|dimgrey|skyblue|steelblue|royalblue|dodgerblue|seagreen|forestgreen|limegreen|goldenrod|hotpink|deeppink|rebeccapurple'
const COLOUR_PROP = '(?:color|background(?:-color)?|backgroundColor|border(?:-(?:top|right|bottom|left))?(?:-color)?|border(?:Top|Right|Bottom|Left)?Color|outline(?:-color)?|outlineColor|fill|stroke|box-shadow|boxShadow|text-shadow|textShadow|caret-color|caretColor|accent-color|accentColor)'
const NAMED_LITERAL = new RegExp(`\\b${COLOUR_PROP}\\s*:\\s*['"\`]?[^;'"\`}\\n]*?\\b(${NAMED})\\b`, 'gi')

// [text role, surface role, minimum ratio]. 4.5 is AA for text; 3 is for a control's edge or focus
// ring against what's around it (WCAG 1.4.11).
const TEXT_ROLES = ['foreground', 'foreground-secondary', 'muted-foreground', 'primary', 'destructive', 'caution', 'fitness', 'nutrition', 'mind']
const SURFACES = ['background', 'card', 'raised', 'primary-tint']
export const PAIRS = [
  ...TEXT_ROLES.flatMap((text) => SURFACES.map((surface) => [text, surface, 4.5])),
  ['primary-foreground', 'primary', 4.5],
  ['primary-tint-foreground', 'primary-tint', 4.5],
  ['popover-foreground', 'popover', 4.5],
  ['crisis-foreground', 'crisis-background', 4.5],
  ['input', 'background', 3],
  ['input', 'card', 3],
  ['ring', 'background', 3],
  ['ring', 'card', 3],
  ['crisis-border', 'crisis-background', 3],
  ['on-silk', 'silk', 4.5], // the wordmark on the sign-in pages' silk, at its brightest
]

export function findLiterals(text) {
  const hits = []
  text.split('\n').forEach((line, i) => {
    for (const m of line.matchAll(LITERAL)) hits.push({ line: i + 1, match: m[0] })
    for (const m of line.matchAll(NAMED_LITERAL)) hits.push({ line: i + 1, match: m[1] })
  })
  return hits
}

function* walk(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) yield* walk(path)
    else if (SCANNED_EXT.test(entry.name)) yield path
  }
}

export function checkLiterals(root = ROOT, legacy = LEGACY) {
  const failures = []
  let legacyHits = 0
  for (const dir of SCANNED_DIRS) {
    for (const path of walk(join(root, dir))) {
      const rel = relative(root, path)
      if (rel === THEME) continue
      const hits = findLiterals(readFileSync(path, 'utf8'))
      if (legacy.has(rel)) legacyHits += hits.length
      else for (const h of hits) failures.push(`${rel}:${h.line} colour literal ${h.match} (use a role from ${THEME})`)
    }
  }
  // The list only shrinks: an entry whose file is gone is stale, and once the list is empty the old
  // stylesheet must be gone too (R7 ends with app/legacy.css deleted)
  for (const rel of legacy) {
    if (!existsSync(join(root, rel))) failures.push(`${rel} is in LEGACY but no longer exists: remove it from the list`)
  }
  if (legacy.size === 0 && existsSync(join(root, 'app/legacy.css'))) failures.push('app/legacy.css still exists: R7 deletes it')
  return { failures, legacyHits }
}

// Reads `--name: value;` declarations from the theme's two :root blocks (palette, roles). The
// @media dark block holds only shadows, so it is ignored here.
function declarations(css) {
  const vars = new Map()
  const body = css.replace(/\/\*[\s\S]*?\*\//g, '')
  for (const block of body.matchAll(/(?:^|\n):root\s*\{([^}]*)\}/g)) {
    for (const m of block[1].matchAll(/--([\w-]+)\s*:\s*([^;]+);/g)) vars.set(m[1], m[2].trim())
  }
  return vars
}

function resolve(vars, name, mode, seen = new Set()) {
  if (seen.has(name)) throw new Error(`--${name} refers to itself`)
  seen.add(name)
  const value = vars.get(name)
  if (value === undefined) throw new Error(`--${name} is not defined in ${THEME}`)
  const ld = value.match(/^light-dark\(\s*(.+?)\s*,\s*(.+?)\s*\)$/)
  const picked = ld ? ld[mode === 'light' ? 1 : 2] : value
  const ref = picked.match(/^var\(--([\w-]+)\)$/)
  if (ref) return resolve(vars, ref[1], mode, seen)
  if (/^#[0-9a-fA-F]{6}$/.test(picked)) return picked
  throw new Error(`--${name} resolves to ${picked}; the contrast check needs a 6-digit hex`)
}

function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

export function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

export function checkContrast(css, pairs = PAIRS) {
  const vars = declarations(css)
  const failures = []
  const rows = []
  for (const mode of ['light', 'dark']) {
    for (const [fg, bg, min] of pairs) {
      let ratio
      try {
        ratio = contrast(resolve(vars, fg, mode), resolve(vars, bg, mode))
      } catch (err) {
        failures.push(`${mode}: ${err.message}`)
        continue
      }
      rows.push({ mode, fg, bg, ratio, min })
      if (ratio < min) failures.push(`${mode}: --${fg} on --${bg} is ${ratio.toFixed(2)}:1, needs ${min}:1`)
    }
  }
  return { failures, rows }
}

function main() {
  const literals = checkLiterals()
  const theme = checkContrast(readFileSync(join(ROOT, THEME), 'utf8'))
  const failures = [...literals.failures, ...theme.failures]
  if (process.argv.includes('--table')) {
    for (const r of theme.rows) console.log(`${r.mode.padEnd(5)} ${r.ratio.toFixed(2).padStart(6)}  --${r.fg} on --${r.bg}`)
  }
  for (const f of failures) console.error(f)
  const lowest = Math.min(...theme.rows.filter((r) => r.min === 4.5).map((r) => r.ratio))
  console.log(
    `check_theme: ${theme.rows.length} contrast pairs (lowest text pair ${lowest.toFixed(2)}:1), ` +
      `${literals.legacyHits} colour literals left in ${LEGACY.size} legacy files, ${failures.length} failures`,
  )
  if (failures.length) process.exit(1)
}

if (process.argv[1] === fileURLToPath(import.meta.url)) main()
