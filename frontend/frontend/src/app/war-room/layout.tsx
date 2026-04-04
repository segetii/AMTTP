'use client';

/**
 * War Room Layout
 * 
 * Wrapper for all War Room pages
 * Ensures RBAC context and redirects unauthorized users
 * 
 * Note: Embed mode (embed=true query param) bypasses auth for iframe embedding
 * Dev mode (port 3006/3000): shows quick role selector if unauthenticated
 */

import React, { useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { useAuth, AuthProvider } from '@/lib/auth-context';
import { AppMode, Role, getRoleCapabilities } from '@/types/rbac';
import WarRoomShell from '@/components/shells/WarRoomShell';

// ── Dev-mode quick role selector ──────────────────────────────────
function DevLogin() {
  const [busy, setBusy] = React.useState(false);
  const pick = (role: string, name: string) => {
    setBusy(true);
    const caps = getRoleCapabilities(Role[role as keyof typeof Role] || Role.R3_INSTITUTION_OPS);
    localStorage.setItem('amttp_session', JSON.stringify({
      userId: `dev_${role.toLowerCase()}`,
      address: 'dev@amttp.io',
      displayName: name,
      role,
      mode: 'WAR_ROOM',
      capabilities: caps,
      institutionId: 'inst_demo',
      institutionName: 'AMTTP Demo',
      createdAt: Date.now(),
    }));
    window.location.reload();
  };
  const roles = [
    { key: 'R3_INSTITUTION_OPS', label: 'R3 — Ops Analyst', name: 'Emma Wilson' },
    { key: 'R4_INSTITUTION_COMPLIANCE', label: 'R4 — Compliance', name: 'Michael Rodriguez' },
    { key: 'R5_PLATFORM_ADMIN', label: 'R5 — Admin', name: 'Sarah Chen' },
    { key: 'R6_SUPER_ADMIN', label: 'R6 — Super Admin', name: 'James Park' },
  ];
  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 max-w-sm w-full">
        <h2 className="text-white text-lg font-semibold mb-1">War Room — Dev Login</h2>
        <p className="text-gray-400 text-sm mb-6">Select a role to enter:</p>
        <div className="space-y-2">
          {roles.map(r => (
            <button
              key={r.key}
              disabled={busy}
              onClick={() => pick(r.key, r.name)}
              className="w-full text-left px-4 py-3 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-200 text-sm transition-colors disabled:opacity-50"
            >
              {r.label}
            </button>
          ))}
        </div>
        <p className="text-gray-600 text-xs mt-4 text-center">Development mode only</p>
      </div>
    </div>
  );
}

// ── Auth guard ────────────────────────────────────────────────────
function WarRoomGuardContent({ children }: { children: React.ReactNode }) {
  const searchParams = useSearchParams();
  const { mode, isAuthenticated, isLoading } = useAuth();
  const [phase, setPhase] = React.useState<'init' | 'checking' | 'done'>('init');

  const isEmbed = searchParams.get('embed') === 'true';
  const roleParam = searchParams.get('role');
  const nameParam = searchParams.get('name');
  const emailParam = searchParams.get('email');
  const nonceParam = searchParams.get('nonce');

  const SESSION_TTL_MS = 4 * 60 * 60 * 1000;
  const isDev = typeof window !== 'undefined' &&
    (window.location.port === '3006' || window.location.port === '3000');

  // ── Single auth effect: runs once after auth context finishes loading ──
  useEffect(() => {
    if (isEmbed) { setPhase('done'); return; }
    if (isLoading) return; // wait for AuthProvider to finish

    // Already authenticated
    if (isAuthenticated && mode === AppMode.WAR_ROOM) {
      setPhase('done');
      return;
    }

    setPhase('checking');

    // Step 0: Clear stale sessions
    try {
      const raw = localStorage.getItem('amttp_session');
      if (raw) {
        const s = JSON.parse(raw);
        if (!s.createdAt || Date.now() - s.createdAt > SESSION_TTL_MS) {
          localStorage.removeItem('amttp_session');
        } else {
          // Session exists but auth context didn't pick it up yet — reload
          window.location.reload();
          return;
        }
      }
    } catch { localStorage.removeItem('amttp_session'); }

    // Step 1: Flutter query-param redirect with nonce verification
    if (roleParam && nonceParam) {
      const cookies = document.cookie.split(';');
      let cookieNonce = '';
      for (const c of cookies) {
        const [k, ...v] = c.trim().split('=');
        if (k === 'amttp_redirect_nonce') cookieNonce = v.join('=');
      }
      if (nonceParam && cookieNonce && nonceParam === cookieNonce) {
        document.cookie = 'amttp_redirect_nonce=; Path=/; max-age=0';
        const roleNames: Record<string, string> = {
          R3_INSTITUTION_OPS: 'Emma Wilson',
          R4_INSTITUTION_COMPLIANCE: 'Michael Rodriguez',
          R5_PLATFORM_ADMIN: 'Sarah Chen',
          R6_SUPER_ADMIN: 'James Park',
        };
        const displayName = nameParam || roleNames[roleParam] || 'War Room User';
        const roleEnum = Role[roleParam as keyof typeof Role] || Role.R3_INSTITUTION_OPS;
        const capabilities = getRoleCapabilities(roleEnum);
        localStorage.setItem('amttp_session', JSON.stringify({
          userId: `flutter_${roleParam.toLowerCase()}`,
          address: emailParam || 'ops@amttp.io',
          displayName,
          role: roleParam,
          mode: 'WAR_ROOM',
          capabilities,
          institutionId: 'inst_demo',
          institutionName: 'AMTTP Institution',
          createdAt: Date.now(),
        }));
        window.location.replace(window.location.pathname);
        return;
      }
      // Nonce mismatch — strip stale params, fall through
      console.warn('[WarRoom] Nonce mismatch — falling through to login');
    }

    // Step 2: Try cross-app auth bridge cookie
    import('@/lib/cross-app-auth-bridge').then(async (bridge) => {
      try {
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
          window.location.reload();
          return;
        }
      } catch (e) {
        console.warn('[WarRoom] Bridge check failed:', e);
      }
      setPhase('done');
    }).catch(() => setPhase('done'));

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading, isAuthenticated, mode, isEmbed]);

  // Safety timeout: never stay in loading state longer than 4 seconds
  useEffect(() => {
    const t = setTimeout(() => {
      setPhase(prev => prev !== 'done' ? 'done' : prev);
    }, 4000);
    return () => clearTimeout(t);
  }, []);

  // ── Render ──────────────────────────────────────────────────────

  if (isEmbed) return <WarRoomShell>{children}</WarRoomShell>;

  if (isAuthenticated && mode === AppMode.WAR_ROOM) {
    return <WarRoomShell>{children}</WarRoomShell>;
  }

  // Still checking auth
  if (phase !== 'done') {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-gray-900 flex items-center justify-center">
            <svg className="w-6 h-6 text-indigo-400 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
          </div>
          <p className="text-gray-400">Loading War Room...</p>
        </div>
      </div>
    );
  }

  // Not authenticated — dev mode: show role picker; prod: redirect to Flutter
  if (isDev) {
    return <DevLogin />;
  }

  // Production: redirect to Flutter sign-in
  if (typeof window !== 'undefined') {
    window.location.replace('/#/sign-out');
  }
  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <p className="text-gray-400">Redirecting to sign in...</p>
    </div>
  );
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
