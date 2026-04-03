'use client';

/**
 * Escrow Page (Focus Mode)
 * 
 * Ground Truth Reference:
 * - "Escrow is risk mitigation, not a payment rail"
 * - Simple status view for end users
 * - Clear actions when available
 */

import dynamic from 'next/dynamic';

const EscrowContent = dynamic(() => import('./EscrowContent'), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center min-h-screen bg-slate-900">
      <div className="text-slate-400">Loading escrow...</div>
    </div>
  ),
});

export default function EscrowPage() {
  return <EscrowContent />;
}
