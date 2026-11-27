// @ts-check
const fs = require('node:fs')
const path = require('node:path')

const { chromium } = require('@playwright/test')

const GUEST = path.join(__dirname, '.auth', 'guest.json')

const API = 'http://localhost:8100'

/**
 * One guest session for every test that needs one, started the way a person starts it (the
 * landing page, Turnstile's test keys), and kept for the next run while the backend still takes
 * it (240 minutes): the backend allows 10 new sessions an hour per IP (C.12), which a run per
 * change would use up.
 */
module.exports = async function globalSetup(config) {
  const { baseURL } = config.projects[0].use
  const browser = await chromium.launch()
  if (fs.existsSync(GUEST)) {
    const kept = await browser.newContext({ storageState: GUEST })
    const session = await kept.request.get(`${API}/session/csrf`)
    const mode = session.ok() ? (await session.json()).mode : null
    await kept.close()
    if (mode === 'guest') {
      await browser.close()
      return
    }
  }
  const page = await browser.newPage({ baseURL })
  await page.goto('/')
  await page.getByRole('button', { name: 'Try Holos as a guest' }).click()
  await page.waitForURL('**/dashboard', { timeout: 60_000 })
  fs.mkdirSync(path.dirname(GUEST), { recursive: true })
  await page.context().storageState({ path: GUEST })
  await browser.close()
}

module.exports.GUEST = GUEST
