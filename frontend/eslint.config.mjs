import nextCoreWebVitals from 'eslint-config-next/core-web-vitals'

// Next's config already lints .jsx and skips .next/; node_modules/ is skipped by ESLint itself
const config = [
  ...nextCoreWebVitals,
  // Downloads/ holds third-party source kept only as a reference while porting (R7)
  // The e2e build (.next-e2e, P5.5) and Playwright's results are output, like .next/
  { ignores: ['coverage/', 'Downloads/', '.next-e2e/', 'test-results/', 'playwright-report/'] },
]

export default config
