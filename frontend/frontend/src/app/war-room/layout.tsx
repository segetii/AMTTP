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

  // Track if we already processed query-param login to avoid re-processing on re-render
  const processedRef = React.useRef(false);

  // ── Single auth effect: runs once after auth context finishes loading ──
  useEffect(() => {
    if (isEmbed) { setPhase('done'); return; }
    if (isLoading) return; // wait for AuthProvider to finish

    // Already authenticated with correct mode — done
    if (isAuthenticated && mode === AppMode.WAR_ROOM) {
      setPhase('done');
      return;
    }

    // Prevent double-processing of query params
    if (processedRef.current) {
      setPhase('done');
      return;
    }

    setPhase('checking');

    // Step 0: Clear stale sessions (but do NOT reload — AuthProvider handles it)
    try {
      const raw = localStorage.getItem('amttp_session');
      if (raw) {
        const s = JSON.parse(raw);
        if (!s.createdAt || Date.now() - s.createdAt > SESSION_TTL_MS) {
          localStorage.removeItem('amttp_session');
        }
      }
    } catch { localStorage.removeItem('amttp_session'); }

    // Step 1: Flutter query-param redirect
    const validRoles = ['R3_INSTITUTION_OPS', 'R4_INSTITUTION_COMPLIANCE', 'R5_PLATFORM_ADMIN', 'R6_SUPER_ADMIN'];
    if (roleParam && validRoles.includes(roleParam)) {
      let accepted = false;

      if (isDev) {
        accepted = true;
      } else if (nonceParam) {
        const cookies = document.cookie.split(';');
        let cookieNonce = '';
        for (const c of cookies) {
          const [k, ...v] = c.trim().split('=');
          if (k === 'amttp_redirect_nonce') cookieNonce = v.join('=');
        }
        if (cookieNonce && nonceParam === cookieNonce) {
          document.cookie = 'amttp_redirect_nonce=; Path=/; max-age=0';
          accepted = true;
        }
      }

      if (accepted) {
        processedRef.current = true;
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

      console.warn('[WarRoom] Role param present but verification failed — showing login');
    }

    // Step 2: In dev mode, skip bridge check and go straight to DevLogin
    processedRef.current = true;
    if (isDev) {
      setPhase('done');
      return;
    }

    // Production: try cross-app auth bridge cookie (with short timeout)
    const bridgeTimeout = setTimeout(() => setPhase('done'), 1500);
    import('@/lib/cross-app-auth-bridge').then(async (bridge) => {
      try {
        const session = await bridge.getBridgeSession();
        if (session && session.role && session.mode) {
          clearTimeout(bridgeTimeout);
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
          window.location.replace(window.location.pathname);
          return;
        }
      } catch (e) {
        console.warn('[WarRoom] Bridge check failed:', e);
      }
      clearTimeout(bridgeTimeout);
      setPhase('done');
    }).catch(() => { clearTimeout(bridgeTimeout); setPhase('done'); });

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading, isAuthenticated, mode, isEmbed]);

  // Safety timeout: never stay in loading state longer than 2 seconds
  useEffect(() => {
    const t = setTimeout(() => {
      setPhase(prev => prev !== 'done' ? 'done' : prev);
    }, 2000);
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

  // Not authenticated — dev mode: show role picker; prod: auto-login for demo
  if (isDev) {
    return <DevLogin />;
  }

  // Production: auto-login as demo R3 user for public showcase
  if (typeof window !== 'undefined') {
    const caps = getRoleCapabilities(Role.R3_INSTITUTION_OPS);
    localStorage.setItem('amttp_session', JSON.stringify({
      userId: 'demo_r3',
      address: 'demo@amttp.io',
      displayName: 'Demo Analyst',
      role: 'R3_INSTITUTION_OPS',
      mode: 'WAR_ROOM',
      capabilities: caps,
      institutionId: 'inst_demo',
      institutionName: 'AMTTP Demo',
      createdAt: Date.now(),
    }));
    window.location.reload();
  }
  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <p className="text-gray-400">Entering War Room...</p>
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
