'use client';

/**
 * Disputes Page (Focus Mode)
 * 
 * Ground Truth Reference:
 * - "Disputes are evidence-driven, not emotion-driven"
 * - Clear status and deadlines
 * - Both sides can submit evidence
 */

import React, { useState, useCallback, Suspense } from 'react';
import { useRouter } from 'next/navigation';
import dynamic from 'next/dynamic';

// Dynamically import the component that uses useAuth
const DisputesContent = dynamic(() => import('./DisputesContent'), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center min-h-screen bg-slate-900">
      <div className="text-slate-400">Loading disputes...</div>
    </div>
  ),
});

export default function DisputesPage() {
  return <DisputesContent />;
}
