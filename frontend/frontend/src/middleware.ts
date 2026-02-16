import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

/**
 * Gateway Auth Middleware
 *
 * When the app is served behind the unified Nginx gateway (basePath: '/app'),
 * the gateway handles authentication and sets an `amttp_session` JWT cookie.
 *
 * This middleware detects the gateway session cookie and:
 *  - Redirects `/` and `/login` to `/war-room/dashboard` (skip the internal login page)
 *  - Lets all other requests through (the War Room layout guard handles the rest)
 *
 * Without a gateway cookie, the normal auth flow applies.
 */

const GATEWAY_COOKIE = 'amttp_session';

// Paths that should redirect to War Room when gateway session exists
const LOGIN_PATHS = ['/', '/login'];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasGatewaySession = request.cookies.has(GATEWAY_COOKIE);

  if (hasGatewaySession && LOGIN_PATHS.includes(pathname)) {
    // User authenticated via gateway — skip the internal login page
    const url = request.nextUrl.clone();
    url.pathname = '/war-room';
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

// Only run on these paths (don't interfere with _next, api, etc.)
export const config = {
  matcher: ['/', '/login'],
};
