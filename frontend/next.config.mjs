import { fileURLToPath } from 'node:url';
import { PHASE_DEVELOPMENT_SERVER } from 'next/constants.js';

// Development (`next dev`) and production builds use separate output folders,
// so a dev session never overwrites the build used by `npm start`.
/** @type {(phase: string) => import('next').NextConfig} */
export default function config(phase) {
  return {
    reactStrictMode: true,
    devIndicators: { position: 'bottom-right' },
    poweredByHeader: false,
    outputFileTracingRoot: fileURLToPath(new URL('../', import.meta.url)),
    experimental: { cpus: 2 },
    distDir:
      process.env.HAEDAP_NEXT_DIST ||
      (phase === PHASE_DEVELOPMENT_SERVER ? '.next-dev' : '.next'),
  };
}
