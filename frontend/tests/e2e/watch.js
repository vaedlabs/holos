// @ts-check
/**
 * Every CSP violation a page reports, from its first script on: the browser's
 * `securitypolicyviolation` events, and the console's "Content Security Policy" errors (P5.5).
 * @param {import('@playwright/test').Page} page
 */
async function watchViolations(page) {
  /** @type {string[]} */
  const seen = []
  await page.exposeFunction('__cspViolation', (/** @type {string} */ v) => { seen.push(v) })
  await page.addInitScript(() => {
    document.addEventListener('securitypolicyviolation', (e) => {
      // @ts-ignore: exposed above
      window.__cspViolation(`${e.violatedDirective} ${e.blockedURI || 'inline'}`)
    })
  })
  page.on('console', (m) => {
    if (m.type() === 'error' && /Content Security Policy/i.test(m.text())) seen.push(m.text())
  })
  return seen
}

module.exports = { watchViolations }
