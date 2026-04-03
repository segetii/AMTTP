'use client';

/**
 * War Room Layout
 * 
 * Wrapper for all War Room pages
 * Ensures RBAC context and redirects unauthorized users
 * 
 * Note: Embed mode (embed=true query param) bypasses auth for iframe embedding
 */

import React, { useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth, AuthProvider } from '@/lib/auth-context';
import { AppMode, Role, ROLE_CAPABILITIES, getRoleCapabilities } from '@/types/rbac';
import WarRoomShell from '@/components/shells/WarRoomShell';

function WarRoomGuardContent({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { mode, isAuthenticated, isLoading } = useAuth();
  const [bridgeChecked, setBridgeChecked] = React.useState(false);
  const [bridgeSession, setBridgeSession] = React.useState<any>(null);

  // Read all query params up front (before any conditional returns)
  const isEmbed = searchParams.get('embed') === 'true';
  const roleParam = searchParams.get('role');
  const nameParam = searchParams.get('name');
  const emailParam = searchParams.get('email');
  const nonceParam = searchParams.get('nonce');

  // Session TTL: 4 hours (sessions older than this are considered stale)
  const SESSION_TTL_MS = 4 * 60 * 60 * 1000;

  // Effect 0: Clear stale/expired sessions on mount
  React.useEffect(() => {
    try {
      const raw = localStorage.getItem('amttp_session');
      if (raw) {
        const s = JSON.parse(raw);
        if (!s.createdAt || Date.now() - s.createdAt > SESSION_TTL_MS) {
          localStorage.removeItem('amttp_session');
          window.location.reload();
        }
      }
    } catch { /* ignore parse errors */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Effect 1: Try to restore session from cross-app auth bridge
  React.useEffect(() => {
    if (!isLoading && !isAuthenticated && !bridgeChecked && !isEmbed) {
      import('@/lib/cross-app-auth-bridge').then(async (bridge) => {
        const session = await bridge.getBridgeSession();
        if (session && session.role && session.mode) {
          localStorage.setItem('amttp_session', JSON.stringify({
            userId: session.sub,
            address: session.email,
            displayName: session.name,
            role: session.role,
            mode: session.mode,
            capabilities: {},
            institutionId: '',
            institutionName: '',
            createdAt: Date.now(),
          }));
          setBridgeSession(session);
          setBridgeChecked(true);
          window.location.reload();
        } else {
          setBridgeChecked(true);
        }
      });
    }
  }, [isLoading, isAuthenticated, bridgeChecked, isEmbed]);

  // Effect 2: Provision session from Flutter's query params (role/name/email)
  // SECURITY: Requires a matching nonce cookie set by Flutter before redirect.
  // This prevents unauthenticated access via crafted URLs.
  React.useEffect(() => {
    if (roleParam) {
      // ── Nonce verification ──────────────────────────────────────────
      const cookies = document.cookie.split(';');
      let cookieNonce = '';
      for (const c of cookies) {
        const [k, ...v] = c.trim().split('=');
        if (k === 'amttp_redirect_nonce') cookieNonce = v.join('=');
      }

      if (!nonceParam || !cookieNonce || nonceParam !== cookieNonce) {
        // Invalid or missing nonce — reject this redirect attempt
        console.warn('[WarRoom] Rejected redirect: nonce mismatch');
        // Clear any stale session
        localStorage.removeItem('amttp_session');
        setBridgeChecked(true);
        return;
      }

      // Clear the one-time nonce cookie
      document.cookie = 'amttp_redirect_nonce=; Path=/; max-age=0';

      // ── Create verified session ─────────────────────────────────────
      const roleNames: Record<string, string> = {
        R3_INSTITUTION_OPS: 'Emma Wilson',
        R4_INSTITUTION_COMPLIANCE: 'Michael Rodriguez',
        R5_PLATFORM_ADMIN: 'Sarah Chen',
        R6_SUPER_ADMIN: 'James Park',
      };
      const displayName = nameParam || roleNames[roleParam] || 'War Room User';
      const roleEnum = Role[roleParam as keyof typeof Role] || Role.R3_INSTITUTION_OPS;
      const capabilities = getRoleCapabilities(roleEnum);

      const session = {
        userId: `flutter_${roleParam.toLowerCase()}`,
        address: emailParam || 'ops@amttp.io',
        displayName,
        role: roleParam,
        mode: 'WAR_ROOM' as const,
        capabilities,
        institutionId: 'inst_demo',
        institutionName: 'AMTTP Institution',
        createdAt: Date.now(),
      };
      localStorage.setItem('amttp_session', JSON.stringify(session));
      window.location.replace(window.location.pathname);
    }
  }, [roleParam, nameParam, emailParam, nonceParam]);

  // Effect 3: Redirect unauthenticated users back to Flutter sign-in
  // (no auto-provision — users MUST log in through Flutter first)
  // Skip if session was just cleared (logout sets amttp_session to null) — the
  // logout function handles its own redirect and we must not race with it.
  React.useEffect(() => {
    if (!isLoading && bridgeChecked && !isEmbed &&
        (!isAuthenticated || mode !== AppMode.WAR_ROOM)) {
      // Double-check localStorage is truly empty (not a logout-in-progress race)
      const raw = localStorage.getItem('amttp_session');
      if (raw) return; // Storage still present — auth context hasn't synced yet; wait
      const isDev = window.location.port === '3006' || window.location.port === '3000';
      const flutterUrl = isDev ? 'http://localhost:3010/#/sign-out' : '/#/sign-out';
      window.location.replace(flutterUrl);
    }
  }, [isLoading, bridgeChecked, isAuthenticated, mode, isEmbed]);

  // ── Render logic ──────────────────────────────────────────────

  // Embed mode — render content directly (auth handled by Flutter parent)
  if (isEmbed) {
    return <WarRoomShell>{children}</WarRoomShell>;
  }

  // Role params present AND nonce not yet checked — show loading while Effect 2 provisions
  if (roleParam && !bridgeChecked) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p className="text-mutedText">Entering War Room...</p>
      </div>
    );
  }

  // Still loading auth state or checking bridge
  if (isLoading || (!isAuthenticated && !bridgeChecked)) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-surface flex items-center justify-center">
            <svg className="w-6 h-6 text-indigo-400 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
          </div>
          <p className="text-mutedText">Loading War Room...</p>
        </div>
      </div>
    );
  }

  // Not authenticated — show message while Effect 3 redirects
  if (!isAuthenticated || mode !== AppMode.WAR_ROOM) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <p className="text-mutedText mb-4">You must log in to access the War Room.</p>
          <p className="text-sm text-gray-500">Redirecting to sign in...</p>
        </div>
      </div>
    );
  }

  return <WarRoomShell>{children}</WarRoomShell>;
}

// Wrapper with Suspense for useSearchParams
function WarRoomGuard({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="animate-spin h-8 w-8 border-2 border-cyan-500 border-t-transparent rounded-full"></div>
      </div>
    }>
      <WarRoomGuardContent>{children}</WarRoomGuardContent>
    </Suspense>
  );
}

export default function WarRoomLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthProvider>
      <WarRoomGuard>{children}</WarRoomGuard>
    </AuthProvider>
  );
}
