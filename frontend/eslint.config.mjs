import nextCoreWebVitals from 'eslint-config-next/core-web-vitals'

// Next's config already lints .jsx and skips .next/; node_modules/ is skipped by ESLint itself
const config = [
  ...nextCoreWebVitals,
  { ignores: ['coverage/'] },
  // react-hooks 7 (Next 16) flags 6 places in the components R7 rewrites; warnings until R7 fixes them
  {
    rules: {
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/immutability': 'warn',
    },
  },
]

export default config
