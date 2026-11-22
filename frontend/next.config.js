const path = require('node:path')

// The shared contracts/ folder (catalogue.json, crisis.json) sits beside the app; Turbopack
// resolves files only under its root, so the root is the repo, not frontend/
const repoRoot = path.join(__dirname, '..')

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  turbopack: { root: repoRoot },
  outputFileTracingRoot: repoRoot,
  // next dev would write frontend/AGENTS.md; the agent rules live in CLAUDE.md and docs/rules/
  agentRules: false,
}

module.exports = nextConfig
