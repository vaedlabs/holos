const path = require('node:path')

// The shared contracts/ folder (catalogue.json, crisis.json) sits beside the app; Turbopack
// resolves files only under its root, so the root is the repo, not frontend/
const repoRoot = path.join(__dirname, '..')

// Testing on a phone: the app and the API run on this machine's network address (both .env
// files), and the dev server only serves its scripts to localhost unless that host is allowed.
// It's the API's host, so the address is written once, in .env.local; dev only.
const apiHost = new URL(process.env.NEXT_PUBLIC_API_URL || 'http://localhost').hostname
const devHosts = apiHost === 'localhost' ? [] : [apiHost]

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  allowedDevOrigins: devHosts,
  turbopack: { root: repoRoot },
  outputFileTracingRoot: repoRoot,
  // next dev would write frontend/AGENTS.md; the agent rules live in CLAUDE.md and docs/rules/
  agentRules: false,
  // The e2e tests build into a folder of their own, against their own API port, so a test run
  // never replaces the build or the dev server's files (P5.5)
  distDir: process.env.NEXT_DIST_DIR || '.next',
}

module.exports = nextConfig
