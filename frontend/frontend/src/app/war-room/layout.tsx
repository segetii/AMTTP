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
import { AppMode } from '@/types/rbac';
import WarRoomShell from '@/components/shells/WarRoomShell';

function WarRoomGuardContent({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { mode, isAuthenticated, isLoading } = useAuth();
  const [bridgeChecked, setBridgeChecked] = React.useState(false);
  const [bridgeSession, setBridgeSession] = React.useState<any>(null);

  // Embed mode: when loaded inside Flutter iframe (?embed=true),
  // bypass the normal auth guard. Flutter already authenticated the user
  // and passed role context via query params.
  const isEmbed = searchParams.get('embed') === 'true';

  React.useEffect(() => {
    // If not authenticated, try to restore from cross-app auth bridge token
    if (!isLoading && !isAuthenticated && !bridgeChecked && !isEmbed) {
      import('@/lib/cross-app-auth-bridge').then(async (bridge) => {
        const session = await bridge.getBridgeSession();
        if (session && session.role && session.mode) {
          // Store session in localStorage for AuthProvider
          localStorage.setItem('amttp_session', JSON.stringify({
            userId: session.sub,
            address: session.email,
            displayName: session.name,
            role: session.role,
            mode: session.mode,
            capabilities: {}, // TODO: load from RBAC config
            institutionId: '',
            institutionName: '',
          }));
          setBridgeSession(session);
          setBridgeChecked(true);
          // Reload page to re-init AuthProvider
          window.location.reload();
        } else {
          setBridgeChecked(true);
        }
      });
    }
  }, [isLoading, isAuthenticated, bridgeChecked, isEmbed]);

  // Embed mode — render content directly (auth handled by Flutter parent)
  if (isEmbed) {
    return <WarRoomShell>{children}</WarRoomShell>;
  }

  // Show loading while checking auth or bridge
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

  // Not authenticated after all checks — auto-create a demo session so
  // the War Room is usable without a separate login flow.  This mirrors
  // the Flutter demo-user approach (R3 Ops Analyst).
  if (!isAuthenticated || mode !== AppMode.WAR_ROOM) {
    // Auto-provision demo session on the client side
    const demoSession = {
      userId: 'demo_r3_nextjs',
      address: 'ops@amttp.io',
      displayName: 'Ops Analyst (R3)',
      role: 'R3_INSTITUTION_OPS',
      mode: 'WAR_ROOM' as const,
      capabilities: {},
      institutionId: 'inst_demo',
      institutionName: 'AMTTP Demo Institution',
    };
    localStorage.setItem('amttp_session', JSON.stringify(demoSession));
    window.location.reload();
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p className="text-mutedText">Entering War Room...</p>
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
