import { fileURLToPath } from 'node:url'
import { transformWithOxc } from 'vite'
import { defineConfig } from 'vitest/config'

// Next's pages are .js files with JSX; Vite reads only .jsx as JSX, so the app's own .js
// files are turned to plain JS first (Vite 8 transforms with Oxc)
const jsxInJs = {
  name: 'jsx-in-js',
  enforce: 'pre',
  transform(code, id) {
    if (!/\/frontend\/(app|components|hooks|lib)\/.*\.js$/.test(id)) return null
    return transformWithOxc(code, id, { lang: 'jsx', jsx: { runtime: 'automatic' } })
  },
}

export default defineConfig({
  plugins: [jsxInJs],
  resolve: { alias: { '@': fileURLToPath(new URL('.', import.meta.url)) } },
  // Components run in jsdom (a `@vitest-environment jsdom` line in their test file)
  test: { include: ['tests/unit/**/*.test.{js,jsx}'], environment: 'node' },
})
