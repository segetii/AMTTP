'use client';

/**
 * Trust Pillar Card
 * 
 * Displays a single trust pillar with qualitative verdict
 * NO NUMERIC SCORES - only Pass/Review/Fail indicators
 * 
 * Per Ground Truth v2.3:
 * - Users see qualitative verdicts, not numbers
 * - Source transparency
 * - Clear action guidance
 */

import React from 'react';
import { TrustPillar, TrustVerdict, TrustPillarDefinition, TRUST_PILLARS } from '@/types/rbac';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface TrustPillarCardProps {
  pillar: TrustPillar;
  verdict: TrustVerdict;
  source?: string;
  lastUpdated?: string;
  showDetails?: boolean;
  onClick?: () => void;
}

// ═══════════════════════════════════════════════════════════════════════════════
// VERDICT STYLING
// ═══════════════════════════════════════════════════════════════════════════════

const VERDICT_CONFIG: Record<TrustVerdict, {
  label: string;
  color: string;
  bgColor: string;
  borderColor: string;
  icon: React.ReactNode;
}> = {
  [TrustVerdict.PASS]: {
    label: 'Verified',
    color: 'text-green-700',
    bgColor: 'bg-green-50',
    borderColor: 'border-green-200',
    icon: (
      <svg className="w-5 h-5 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
      </svg>
    ),
  },
  [TrustVerdict.REVIEW]: {
    label: 'Needs Review',
    color: 'text-amber-700',
    bgColor: 'bg-amber-50',
    borderColor: 'border-amber-200',
    icon: (
      <svg className="w-5 h-5 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    ),
  },
  [TrustVerdict.FAIL]: {
    label: 'Failed',
    color: 'text-red-700',
    bgColor: 'bg-red-50',
    borderColor: 'border-red-200',
    icon: (
      <svg className="w-5 h-5 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
      </svg>
    ),
  },
  [TrustVerdict.UNKNOWN]: {
    label: 'Unknown',
    color: 'text-gray-700',
    bgColor: 'bg-gray-50',
    borderColor: 'border-gray-200',
    icon: (
      <svg className="w-5 h-5 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
};

// ═══════════════════════════════════════════════════════════════════════════════
// PILLAR ICONS
// ═══════════════════════════════════════════════════════════════════════════════

const PILLAR_ICONS: Record<TrustPillar, React.ReactNode> = {
  [TrustPillar.SANCTIONS]: (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
    </svg>
  ),
  [TrustPillar.NETWORK_BEHAVIOR]: (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
    </svg>
  ),
  [TrustPillar.GEOGRAPHIC]: (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418" />
    </svg>
  ),
  [TrustPillar.COUNTERPARTY]: (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
    </svg>
  ),
  [TrustPillar.TRANSACTION_PATTERN]: (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
    </svg>
  ),
};

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function TrustPillarCard({
  pillar,
  verdict,
  source,
  lastUpdated,
  showDetails = false,
  onClick,
}: TrustPillarCardProps) {
  const definition = TRUST_PILLARS[pillar];
  const verdictConfig = VERDICT_CONFIG[verdict];
  const pillarIcon = PILLAR_ICONS[pillar];
  
  return (
    <button
      onClick={onClick}
      disabled={!onClick}
      className={`
        w-full text-left p-4 rounded-xl border-2 transition-all
        ${verdictConfig.bgColor} ${verdictConfig.borderColor}
        ${onClick ? 'cursor-pointer hover:shadow-md hover:scale-[1.02]' : 'cursor-default'}
        focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500
      `}
    >
      <div className="flex items-start gap-4">
        {/* Pillar Icon */}
        <div className={`${verdictConfig.color} mt-0.5`}>
          {pillarIcon}
        </div>
        
        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <h3 className="font-semibold text-gray-900">
              {definition.label}
            </h3>
            
            {/* Verdict Badge */}
            <div className={`flex items-center gap-1.5 px-2 py-1 rounded-full ${verdictConfig.bgColor}`}>
              {verdictConfig.icon}
              <span className={`text-sm font-medium ${verdictConfig.color}`}>
                {verdictConfig.label}
              </span>
            </div>
          </div>
          
          {/* Description */}
          <p className="mt-1 text-sm text-gray-600">
            {definition.description}
          </p>
          
          {/* Source & Timing */}
          {showDetails && (source || lastUpdated) && (
            <div className="mt-2 flex items-center gap-3 text-xs text-gray-500">
              {source && (
                <span className="flex items-center gap-1">
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M12 5l7 7-7 7" />
                  </svg>
                  Source: {source}
                </span>
              )}
              {lastUpdated && (
                <span className="flex items-center gap-1">
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  {lastUpdated}
                </span>
              )}
            </div>
          )}
        </div>
        
        {/* Expand Arrow (if clickable) */}
        {onClick && (
          <svg className="w-5 h-5 text-gray-400 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        )}
      </div>
    </button>
  );
}
