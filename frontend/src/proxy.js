// Forwards /api/* to the internal API server, decided at request time (not at build time).
// The target is HAEDAP_API_ORIGIN: process environment, or the project-root .env
// (loaded by next.config.mjs when `next dev` / `next start` starts). See docs/adr/0007.
import { NextResponse } from 'next/server';

export function proxy(request) {
  const origin = process.env.HAEDAP_API_ORIGIN || 'http://127.0.0.1:8000';
  const { pathname, search } = request.nextUrl;
  // Next.js sets X-Forwarded-Host to the real Host; the API server checks it.
  return NextResponse.rewrite(new URL(pathname + search, origin));
}

export const config = { matcher: '/api/:path*' };
