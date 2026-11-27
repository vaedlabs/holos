// @ts-check
const path = require('node:path')

const { defineConfig } = require('@playwright/test')

/**
 * Browser tests (P5.5; P5.7 runs them in CI): a production build of the app and its own backend,
 * on ports of their own (3100, 8100), so the dev servers on 3000 and 8000 keep running. The
 * backend is the local one with the dev database; the tests make no model call. Playwright's own
 * Chromium (owner, 27 Nov 2026, Part E #80). Run: npm run test:e2e.
 */
const APP = 'http://localhost:3100'
const API = 'http://localhost:8100'

module.exports = defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1, // one guest session for all, under the backend's 10 new sessions an hour per IP (C.12)
  retries: 0,
  reporter: 'list',
  globalSetup: './tests/e2e/global-setup.js',
  use: { baseURL: APP, browserName: 'chromium', trace: 'retain-on-failure' },
  webServer: [
    {
      command: 'conda run --no-capture-output -n holos uvicorn app.main:app --port 8100',
      cwd: path.join(__dirname, '..', 'backend'),
      url: `${API}/health`,
      // The backend's origins for this app, over its .env (load_dotenv never overrides)
      env: { APP_ORIGIN: APP, API_ORIGIN: API },
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: 'npm run build && npm run start -- -p 3100',
      url: `${APP}/login`,
      env: { NEXT_PUBLIC_API_URL: API, NEXT_DIST_DIR: '.next-e2e' },
      reuseExistingServer: false,
      timeout: 300_000,
    },
  ],
})
