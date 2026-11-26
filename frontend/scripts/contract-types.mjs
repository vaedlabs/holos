/**
 * Types for the frontend from the contracts the backend writes (R9, Part E #74):
 *
 *   npm run contracts:types      # after `python -m app.contracts.generate` changes a schema
 *
 * Each contracts/schema/*.json (not llm/: the app never sees those) becomes one module in
 * types/contracts/, named for its file, and index.d.ts re-exports each one's top type.
 * One module each, since the schemas share definition names (StagedWrite is in both the
 * history and the import) that one file would declare twice. CI regenerates them and fails
 * if they differ from the committed files.
 */

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { compile } from 'json-schema-to-typescript'

const here = path.dirname(fileURLToPath(import.meta.url))
const SCHEMAS = path.resolve(here, '../../contracts/schema')
const OUT = path.resolve(here, '../types/contracts')
const BANNER = "// Generated from contracts/schema by npm run contracts:types. Don't edit."

// "stream_event" as "StreamEvent": the top type's name, whatever the schema's title
const typeName = (file) => file.replace(/\.json$/, '').split('_')
  .map((w) => w[0].toUpperCase() + w.slice(1)).join('')

// A property's title (Pydantic's "At", "Kind") would become a type alias of its own
// (`at: At`, `kind: Kind3`); without it the type is written in place (`at: string`)
function untitled(node, isProperty = false) {
  if (Array.isArray(node)) return node.map((n) => untitled(n))
  if (!node || typeof node !== 'object') return node
  const out = {}
  for (const [key, value] of Object.entries(node)) {
    if (key === 'title' && isProperty) continue
    if (key === 'properties') {
      out.properties = Object.fromEntries(Object.entries(value).map(([k, v]) => [k, untitled(v, true)]))
    } else {
      out[key] = untitled(value, isProperty && ['anyOf', 'oneOf', 'items'].includes(key))
    }
  }
  return out
}

const files = fs.readdirSync(SCHEMAS).filter((f) => f.endsWith('.json')).sort()
fs.rmSync(OUT, { recursive: true, force: true })
fs.mkdirSync(OUT, { recursive: true })
const index = [BANNER, '']
for (const file of files) {
  const schema = JSON.parse(fs.readFileSync(path.join(SCHEMAS, file), 'utf8'))
  const name = typeName(file)
  const ts = await compile({ ...untitled(schema), title: name }, name, {
    bannerComment: BANNER,
    additionalProperties: false,
    // A list of at most 6 sources is Source[], not a union of six tuple types
    maxItems: -1,
    style: { singleQuote: true, semi: false, printWidth: 100 },
  })
  const stem = file.replace(/\.json$/, '')
  fs.writeFileSync(path.join(OUT, `${stem}.d.ts`), ts)
  index.push(`export type { ${name} } from './${stem}'`)
}
fs.writeFileSync(path.join(OUT, 'index.d.ts'), `${index.join('\n')}\n`)
console.log(`wrote ${files.length} modules to types/contracts/`)
