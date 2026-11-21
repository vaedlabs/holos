import { FlatCompat } from '@eslint/eslintrc'

// Next 15's eslint-config-next is in the old format, so FlatCompat reads it
const compat = new FlatCompat({ baseDirectory: import.meta.dirname })

const config = [
  { ignores: ['.next/', 'node_modules/', 'coverage/'] },
  // ESLint picks up only .js, .mjs and .cjs on its own; the components are .jsx
  { files: ['**/*.{js,jsx,mjs}'] },
  ...compat.extends('next/core-web-vitals'),
]

export default config
