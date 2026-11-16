/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The shared contracts/ folder (catalogue.json, crisis.json) sits beside the app
  experimental: { externalDir: true },
}

module.exports = nextConfig

