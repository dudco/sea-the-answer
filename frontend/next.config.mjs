import { fileURLToPath } from 'node:url';
import { networkInterfaces } from 'node:os';
import { readFileSync } from 'node:fs';
import { parseEnv } from 'node:util';
import { PHASE_DEVELOPMENT_SERVER } from 'next/constants.js';

// Next.js is the public entry point. `/api/*` is proxied to the internal API
// server by src/proxy.js at request time (docs/adr/0006, 0007).
// Only HAEDAP_API_ORIGIN is read from the project-root .env (no secrets enter Next.js).
function rootEnv(name) {
  try {
    return parseEnv(readFileSync(new URL('../.env', import.meta.url), 'utf8'))[name];
  } catch {
    return undefined;
  }
}
// This file runs whenever `next dev` / `next start` starts, so a change in .env
// takes effect on restart without rebuilding. src/proxy.js reads process.env.
process.env.HAEDAP_API_ORIGIN ||= rootEnv('HAEDAP_API_ORIGIN') || 'http://127.0.0.1:8000';

// LAN addresses of this PC, so `next dev -H 0.0.0.0` accepts them for dev assets/HMR.
const lanHosts = () =>
  Object.values(networkInterfaces())
    .flat()
    .filter((e) => e && (e.family === 'IPv4' || e.family === 4) && !e.internal)
    .map((e) => e.address);

/** @type {(phase: string) => import('next').NextConfig} */
export default function config(phase) {
  const dev = phase === PHASE_DEVELOPMENT_SERVER;
  return {
    reactStrictMode: true,
    devIndicators: { position: 'bottom-right' },
    poweredByHeader: false,
    outputFileTracingRoot: fileURLToPath(new URL('../', import.meta.url)),
    // Development and production builds use separate output folders.
    distDir: process.env.HAEDAP_NEXT_DIST || (dev ? '.next-dev' : '.next'),
    ...(dev ? { allowedDevOrigins: lanHosts() } : {}),
    experimental: {
      cpus: 2,
      // Proxied request bodies: PDF document saves (≤38MB) and backup imports (≤100MB).
      proxyClientMaxBodySize: '101mb',
      // Proxy timeout for /api (default 30s); grounded LLM answers can take ~25s+.
      proxyTimeout: 60000,
    },
  };
}
