import nextCoreWebVitals from 'eslint-config-next/core-web-vitals'

// Next's config already lints .jsx and skips .next/; node_modules/ is skipped by ESLint itself
const config = [
  ...nextCoreWebVitals,
  // Downloads/ holds third-party source kept only as a reference while porting (R7)
  { ignores: ['coverage/', 'Downloads/'] },
]

export default config
