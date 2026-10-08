import { fileURLToPath } from 'node:url';

/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  devIndicators: { position: 'bottom-right' },
  poweredByHeader: false,
  outputFileTracingRoot: fileURLToPath(new URL('../', import.meta.url)),
  experimental: { cpus: 2 },
  distDir: process.env.HAEDAP_NEXT_DIST || '.next',
};
export default config;
