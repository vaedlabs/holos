// @ts-check
/**
 * The CSP in a real browser (P5.5; Plan C.6): every page carries it with a nonce of its own; a
 * script slipped into a page doesn't run; Turnstile still loads; moving between pages and the
 * chat's dialogs, toast and trace panel raise no violation; and "Need help now?" shows the
 * helplines with the backend unreachable (P5.4's test, E077). No model is called: the chat's
 * answer is the recorded `blocked_and_retried` stream.
 */
const fs = require('node:fs')
const path = require('node:path')

const { expect, test } = require('@playwright/test')

const { GUEST } = require('./global-setup')
const { watchViolations } = require('./watch')

const API = 'http://localhost:8100'
const nonceOf = (/** @type {string} */ policy) => policy.match(/'nonce-([^']+)'/)?.[1]

test('every page carries the CSP, with a new nonce each time, on all of its scripts', async ({ request }) => {
  const nonces = new Set()
  for (const route of ['/', '/login', '/dashboard', '/profile', '/onboarding']) {
    const response = await request.get(route)
    const policy = response.headers()['content-security-policy']
    expect(policy, route).toContain("default-src 'self'")
    expect(policy).toContain("object-src 'none'")
    expect(policy).toContain("frame-ancestors 'none'")
    expect(policy).toContain(`connect-src 'self' ${API}`)
    expect(policy).not.toContain('unsafe-eval') // a production build: development only (E080)
    nonces.add(nonceOf(policy))
  }
  expect(nonces.size).toBe(5)

  // Every script tag the server sends has this response's nonce (chunks Next loads later come
  // from the app itself, which 'self' allows)
  const response = await request.get('/login')
  const nonce = nonceOf(response.headers()['content-security-policy'] ?? '')
  const tags = (await response.text()).match(/<script\b[^>]*>/g) ?? []
  expect(tags.length).toBeGreaterThan(0)
  for (const tag of tags) expect(tag).toContain(`nonce="${nonce}"`)
})

test('a script slipped into the page is blocked, inline or from elsewhere', async ({ page }) => {
  const violations = await watchViolations(page)
  await page.goto('/login')
  await page.evaluate(() => {
    const inline = document.createElement('script')
    inline.textContent = 'window.__injected = true'
    document.body.append(inline)
    const remote = document.createElement('script')
    remote.src = 'https://evil.example/steal.js'
    document.body.append(remote)
  })
  await expect.poll(() => violations.length).toBeGreaterThanOrEqual(2)
  expect(await page.evaluate(() => /** @type {any} */ (window).__injected)).toBeUndefined()
  expect(violations.join('\n')).toMatch(/script-src/)
  expect(violations.join('\n')).toContain('evil.example')
})

test('Turnstile still loads on the landing page', async ({ page }) => {
  const violations = await watchViolations(page)
  /** @type {string[]} */
  const loaded = []
  page.on('response', (r) => {
    if (r.url().startsWith('https://challenges.cloudflare.com/') && r.ok()) loaded.push(new URL(r.url()).pathname)
  })
  // The token Turnstile gives is checked here, not by starting a guest: the backend allows 10
  // new sessions an hour per IP (C.12)
  /** @type {string[]} */
  const tokens = []
  await page.route(`${API}/session/start`, async (route) => {
    tokens.push(route.request().postDataJSON()?.turnstile_token ?? '')
    await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: { code: 'test' } }) })
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Try Holos as a guest' }).click()
  // Its test key passes and hands over a token; the widget's frame is in a shadow root, so its
  // loads are checked instead: the script, then the challenge it frames
  await expect.poll(() => tokens.length, { timeout: 30_000 }).toBe(1)
  expect(tokens[0]).not.toBe('')
  expect(loaded.some((p) => p.includes('/turnstile/v0/'))).toBe(true)
  expect(loaded.some((p) => p.includes('/challenge-platform/'))).toBe(true)
  expect(violations).toEqual([])
})

test.describe('as a guest', () => {
  test.use({ storageState: GUEST })

  test('moving between pages raises no violation', async ({ page }) => {
    const violations = await watchViolations(page)
    await page.goto('/dashboard')
    await page.getByRole('button', { name: 'Menu' }).click()
    await page.getByRole('menuitem', { name: 'Health profile' }).click()
    await page.waitForURL('**/profile')
    await expect(page.getByRole('heading', { name: 'Your health profile' })).toBeVisible()
    await page.getByRole('link', { name: 'Chat' }).click()
    await page.waitForURL('**/dashboard')
    await page.getByRole('link', { name: 'Holos' }).first().click()
    await expect(page.getByRole('textbox', { name: 'Message' })).toBeVisible()
    expect(violations).toEqual([])
  })
})

test.describe('the chat, as an account (the API answered by the test)', () => {
  const SAMPLE = fs.readFileSync(path.resolve(__dirname, '../../../contracts/streams/blocked_and_retried.jsonl'), 'utf8')
  const sse = SAMPLE.split('\n').filter(Boolean).map((line) => {
    const { event, data } = JSON.parse(line)
    return `id: ${data.seq}\nevent: ${event}\ndata: ${JSON.stringify(data)}\n\n`
  }).join('')

  test.beforeEach(async ({ page }) => {
    const json = (/** @type {any} */ body) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    await page.route(`${API}/**`, (route) => {
      const url = new URL(route.request().url())
      if (url.pathname === '/session/csrf') {
        return route.fulfill(json({ mode: 'account', csrf_token: 'test', expires_at: '2099-01-01T00:00:00Z' }))
      }
      if (url.pathname === '/conversation/messages') return route.fulfill(json({ messages: [], before: null }))
      if (url.pathname === '/agents/chat/stream') {
        return route.fulfill({ status: 200, contentType: 'text/event-stream', body: sse })
      }
      return route.fulfill(json({}))
    })
    // Guest data left in this browser, so the account is offered it (P5.4)
    await page.addInitScript(() => {
      localStorage.setItem('holos.guest.v1', JSON.stringify({
        version: 1, profile: { condition_ids: [], allergen_tags: ['peanut'], diet_tags: [], notes: '' },
        turns: [], pending: [], logs: [], traces: [] }))
    })
  })

  test('the import dialog, the AI notice, the help dialog and the trace panel raise no violation', async ({ page }) => {
    const violations = await watchViolations(page)
    await page.goto('/dashboard')

    const offer = page.getByRole('dialog', { name: 'Save your guest data to this account?' })
    await expect(offer).toBeVisible()
    await offer.getByRole('button', { name: 'Close' }).click()

    await expect(page.getByText("Holos's suggestions are AI-generated.", { exact: false })).toBeVisible()

    await page.getByRole('button', { name: 'Need help now?' }).click()
    await expect(page.getByRole('dialog', { name: 'Need help now?' })).toContainText('Tele-MANAS')
    await page.keyboard.press('Escape')

    await page.getByRole('textbox', { name: 'Message' }).fill('A leg workout, please')
    await page.getByRole('button', { name: 'Send' }).click()
    const toggle = page.getByRole('button', { name: /How this answer was made/ })
    await toggle.click()
    await expect(page.getByText('EX-KNEE-01')).toBeVisible()

    expect(violations).toEqual([])
  })
})

test('"Need help now?" shows the helplines with the backend unreachable', async ({ page }) => {
  await page.route(`${API}/**`, (route) => route.abort('connectionrefused'))
  await page.goto('/')
  await page.getByRole('button', { name: 'Need help now?' }).click()
  const help = page.getByRole('dialog', { name: 'Need help now?' })
  await expect(help).toContainText('Tele-MANAS')
  await expect(help.getByRole('link', { name: '14416' })).toHaveAttribute('href', 'tel:14416')
  await expect(help.getByRole('link', { name: '988' })).toHaveAttribute('href', 'tel:988')
})
