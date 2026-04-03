'use client';

/**
 * Focus Mode - Trust Check Page
 * 
 * Standalone counterparty verification tool
 * Check any address before transacting
 */

import React, { useState, useCallback } from 'react';
import FocusModeShell from '@/components/shells/FocusModeShell';
import TrustPillarCard from '@/components/trust/TrustPillarCard';
import { TrustPillar, TrustVerdict } from '@/types/rbac';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface TrustCheckResult {
  address: string;
  pillars: {
    pillar: TrustPillar;
    verdict: TrustVerdict;
    source: string;
    lastUpdated: string;
  }[];
  recommendation: 'safe' | 'caution' | 'avoid';
}

// ═══════════════════════════════════════════════════════════════════════════════
// API
// ═══════════════════════════════════════════════════════════════════════════════

async function fetchTrustCheck(address: string): Promise<TrustCheckResult> {
  // In production, this would call the backend
  // For now, return simulated results
  await new Promise(resolve => setTimeout(resolve, 1500));
  
  const hasRisk = address.toLowerCase().includes('risk') || address.startsWith('0xdead');
  const isUnknown = address.toLowerCase().includes('new') || address.length < 20;
  
  const pillars: TrustCheckResult['pillars'] = [
    {
      pillar: TrustPillar.SANCTIONS,
      verdict: hasRisk ? TrustVerdict.FAIL : TrustVerdict.PASS,
      source: 'OFAC SDN List',
      lastUpdated: 'Just now',
    },
    {
      pillar: TrustPillar.NETWORK_BEHAVIOR,
      verdict: hasRisk ? TrustVerdict.REVIEW : isUnknown ? TrustVerdict.UNKNOWN : TrustVerdict.PASS,
      source: 'GraphSAGE Analysis',
      lastUpdated: 'Just now',
    },
    {
      pillar: TrustPillar.GEOGRAPHIC,
      verdict: TrustVerdict.PASS,
      source: 'IP Geolocation',
      lastUpdated: 'Just now',
    },
    {
      pillar: TrustPillar.COUNTERPARTY,
      verdict: isUnknown ? TrustVerdict.UNKNOWN : TrustVerdict.PASS,
      source: 'AMTTP Records',
      lastUpdated: 'Just now',
    },
    {
      pillar: TrustPillar.TRANSACTION_PATTERN,
      verdict: hasRisk ? TrustVerdict.REVIEW : TrustVerdict.PASS,
      source: 'LightGBM Analysis',
      lastUpdated: 'Just now',
    },
  ];
  
  const hasFail = pillars.some(p => p.verdict === TrustVerdict.FAIL);
  const hasReview = pillars.some(p => p.verdict === TrustVerdict.REVIEW);
  
  return {
    address,
    pillars,
    recommendation: hasFail ? 'avoid' : hasReview ? 'caution' : 'safe',
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function FocusTrustPage() {
  const [address, setAddress] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<TrustCheckResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  
  const handleCheck = useCallback(async () => {
    if (!address.trim()) {
      setError('Please enter an address');
      return;
    }
    
    if (!address.startsWith('0x') || address.length !== 42) {
      setError('Please enter a valid Ethereum address (0x...)');
      return;
    }
    
    setIsLoading(true);
    setError(null);
    setResult(null);
    
    try {
      const checkResult = await fetchTrustCheck(address);
      setResult(checkResult);
    } catch (e) {
      setError('Unable to verify address. Please try again.');
    } finally {
      setIsLoading(false);
    }
  }, [address]);
  
  const getRecommendationDisplay = (rec: TrustCheckResult['recommendation']) => {
    switch (rec) {
      case 'safe':
        return {
          label: 'Appears Safe',
          description: 'All trust checks passed. You can transact with confidence.',
          color: 'text-green-700',
          bgColor: 'bg-green-50',
          borderColor: 'border-green-200',
          icon: (
            <svg className="w-6 h-6 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          ),
        };
      case 'caution':
        return {
          label: 'Exercise Caution',
          description: 'Some aspects couldn\'t be fully verified. Consider using escrow.',
          color: 'text-amber-700',
          bgColor: 'bg-amber-50',
          borderColor: 'border-amber-200',
          icon: (
            <svg className="w-6 h-6 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          ),
        };
      case 'avoid':
        return {
          label: 'Not Recommended',
          description: 'Significant trust concerns detected. We recommend avoiding this address.',
          color: 'text-red-700',
          bgColor: 'bg-red-50',
          borderColor: 'border-red-200',
          icon: (
            <svg className="w-6 h-6 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
            </svg>
          ),
        };
    }
  };
  
  return (
    <FocusModeShell>
      <div className="space-y-6">
        {/* Header */}
        <div className="text-center">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-indigo-100 flex items-center justify-center">
            <svg className="w-8 h-8 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Trust Check</h1>
          <p className="text-gray-500 mt-1">
            Verify an address before you transact
          </p>
        </div>
        
        {/* Search Input */}
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Address to Verify
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={address}
              onChange={(e) => {
                setAddress(e.target.value);
                setError(null);
              }}
              placeholder="0x..."
              className="flex-1 px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition-all font-mono text-sm"
              onKeyDown={(e) => e.key === 'Enter' && handleCheck()}
            />
            <button
              onClick={handleCheck}
              disabled={isLoading}
              className="px-6 py-3 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-xl transition-colors disabled:opacity-50"
            >
              {isLoading ? 'Checking...' : 'Check'}
            </button>
          </div>
          
          {error && (
            <p className="mt-2 text-sm text-red-600">{error}</p>
          )}
        </div>
        
        {/* Loading State */}
        {isLoading && (
          <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
            <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-gray-100 flex items-center justify-center">
              <svg className="w-6 h-6 text-gray-400 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
            </div>
            <p className="text-gray-600">Verifying address...</p>
            <p className="text-sm text-gray-400 mt-1">Checking sanctions, network behavior, and more</p>
          </div>
        )}
        
        {/* Results */}
        {result && !isLoading && (
          <div className="space-y-4">
            {/* Overall Recommendation */}
            {(() => {
              const rec = getRecommendationDisplay(result.recommendation);
              return (
                <div className={`${rec.bgColor} border ${rec.borderColor} rounded-xl p-4`}>
                  <div className="flex items-start gap-4">
                    <div className="mt-1">{rec.icon}</div>
                    <div>
                      <h2 className={`text-lg font-semibold ${rec.color}`}>{rec.label}</h2>
                      <p className="text-sm text-gray-600 mt-1">{rec.description}</p>
                    </div>
                  </div>
                </div>
              );
            })()}
            
            {/* Address */}
            <div className="bg-gray-50 rounded-xl p-4">
              <div className="text-sm text-gray-500">Address Checked</div>
              <div className="font-mono text-sm text-gray-900 break-all mt-1">
                {result.address}
              </div>
            </div>
            
            {/* Trust Pillars */}
            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
                Trust Assessment Details
              </h3>
              {result.pillars.map((pillar) => (
                <TrustPillarCard
                  key={pillar.pillar}
                  pillar={pillar.pillar}
                  verdict={pillar.verdict}
                  source={pillar.source}
                  lastUpdated={pillar.lastUpdated}
                  showDetails
                />
              ))}
            </div>
            
            {/* Actions */}
            <div className="flex gap-3 pt-4">
              <button
                onClick={() => {
                  setAddress('');
                  setResult(null);
                }}
                className="flex-1 py-3 border border-gray-300 text-gray-700 font-semibold rounded-xl hover:bg-gray-50 transition-colors"
              >
                Check Another
              </button>
              {result.recommendation !== 'avoid' && (
                <button
                  onClick={() => {
                    // Navigate to transfer with pre-filled address
                    window.location.href = `/focus/transfer?to=${result.address}`;
                  }}
                  className="flex-1 py-3 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-xl transition-colors"
                >
                  Send to This Address
                </button>
              )}
            </div>
          </div>
        )}
        
        {/* Empty State */}
        {!result && !isLoading && (
          <div className="bg-gray-50 rounded-xl p-8 text-center text-gray-500">
            <svg className="w-12 h-12 mx-auto mb-3 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
            </svg>
            <p>Enter an Ethereum address to check its trust status</p>
          </div>
        )}
      </div>
    </FocusModeShell>
  );
}
