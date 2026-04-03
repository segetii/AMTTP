'use client';

/**
 * Disputes Content Component
 * Separated to enable dynamic import with ssr: false
 */

import React, { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { useDispute } from '@/lib/dispute-service';
import { Dispute } from '@/types/dispute';
import DisputeList from '@/components/dispute/DisputeList';
import DisputeDetail from '@/components/dispute/DisputeDetail';

export default function DisputesContent() {
  const router = useRouter();
  const { session, isAuthenticated, isLoading: authLoading } = useAuth();
  const [selectedDispute, setSelectedDispute] = useState<Dispute | null>(null);
  
  const {
    disputes,
    summaries,
    isLoading,
    error,
    submitEvidence,
    respond,
    requestArbitration,
    appeal,
    refresh,
  } = useDispute(session?.address || null);
  
  // Handle dispute selection
  const handleSelectDispute = useCallback((disputeId: string) => {
    const dispute = disputes.find(d => d.id === disputeId);
    if (dispute) {
      setSelectedDispute(dispute);
    }
  }, [disputes]);
  
  // Handle submit evidence (simplified - would show modal in production)
  const handleSubmitEvidence = useCallback(async (disputeId?: string) => {
    const id = disputeId || selectedDispute?.id;
    if (!id) return;
    
    // In production, would show evidence upload modal
    const result = await submitEvidence({
      disputeId: id,
      title: 'Additional Evidence',
      description: 'Evidence supporting my case',
      category: 'document',
      files: [],
    });
    
    if (result.success && selectedDispute) {
      // Refresh to get updated dispute
      await refresh();
      const updated = disputes.find(d => d.id === id);
      if (updated) setSelectedDispute(updated);
    }
  }, [selectedDispute, submitEvidence, refresh, disputes]);
  
  // Handle respond
  const handleRespond = useCallback(async (disputeId?: string) => {
    const id = disputeId || selectedDispute?.id;
    if (!id) return;
    
    // In production, would show response form modal
    const result = await respond({
      disputeId: id,
      summary: 'I disagree with this claim.',
    });
    
    if (result.success && result.data) {
      setSelectedDispute(result.data);
    }
  }, [selectedDispute, respond]);
  
  // Handle request arbitration
  const handleRequestArbitration = useCallback(async () => {
    if (!selectedDispute) return;
    
    const result = await requestArbitration(selectedDispute.id);
    if (result.success && result.data) {
      setSelectedDispute(result.data);
    }
  }, [selectedDispute, requestArbitration]);
  
  // Handle appeal
  const handleAppeal = useCallback(async () => {
    if (!selectedDispute) return;
    
    const result = await appeal({
      disputeId: selectedDispute.id,
      reason: 'I believe the decision was incorrect.',
    });
    
    if (result.success && result.data) {
      setSelectedDispute(result.data);
    }
  }, [selectedDispute, appeal]);
  
  // Loading state
  if (authLoading || isLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 
                    flex items-center justify-center">
        <div className="flex items-center gap-3">
          <div className="animate-spin rounded-full h-6 w-6 border-2 border-cyan-500 border-t-transparent" />
          <span className="text-slate-400">Loading disputes...</span>
        </div>
      </div>
    );
  }
  
  // Not authenticated
  if (!isAuthenticated || !session) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 
                    flex items-center justify-center">
        <div className="bg-slate-800/50 rounded-xl border border-slate-700 p-8 max-w-md text-center">
          <svg className="w-16 h-16 text-slate-600 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3" />
          </svg>
          <h2 className="text-xl font-bold text-white mb-2">Connect Wallet</h2>
          <p className="text-slate-400 mb-6">
            Connect your wallet to view your disputes.
          </p>
          <button
            onClick={() => router.push('/')}
            className="px-6 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg transition-colors"
          >
            Go to Dashboard
          </button>
        </div>
      </div>
    );
  }
  
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-white">
      {/* Header */}
      <header className="border-b border-slate-700 bg-slate-900/50">
        <div className="max-w-4xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => router.push('/')}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                </svg>
              </button>
              <div>
                <h1 className="text-xl font-bold text-white">Dispute Resolution</h1>
                <p className="text-sm text-slate-400">Evidence-based dispute handling</p>
              </div>
            </div>
            
            <button
              onClick={refresh}
              className="p-2 hover:bg-slate-800 rounded-lg transition-colors text-slate-400 hover:text-white"
              title="Refresh"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
          </div>
        </div>
      </header>
      
      {/* Main Content */}
      <main className="max-w-4xl mx-auto px-6 py-8">
        {/* Stats Strip */}
        <div className="grid grid-cols-4 gap-4 mb-8">
          {[
            { 
              label: 'You Filed', 
              value: summaries.filter(s => s.isClaimant).length,
              color: 'blue'
            },
            { 
              label: 'Against You', 
              value: summaries.filter(s => !s.isClaimant).length,
              color: 'orange'
            },
            { 
              label: 'In Progress', 
              value: summaries.filter(s => !['RESOLVED', 'WITHDRAWN'].includes(s.status)).length,
              color: 'yellow'
            },
            { 
              label: 'Resolved', 
              value: summaries.filter(s => s.status === 'RESOLVED').length,
              color: 'green'
            },
          ].map((stat) => (
            <div key={stat.label} className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
              <p className="text-sm text-slate-400">{stat.label}</p>
              <p className={`text-2xl font-bold text-${stat.color}-400`}>{stat.value}</p>
            </div>
          ))}
        </div>
        
        {/* Error Message */}
        {error && (
          <div className="mb-6 bg-red-900/20 border border-red-600/30 rounded-lg p-4">
            <p className="text-red-300">{error}</p>
          </div>
        )}
        
        {/* Dispute List */}
        <DisputeList
          disputes={summaries}
          onSelect={handleSelectDispute}
          onSubmitEvidence={handleSubmitEvidence}
          onRespond={handleRespond}
          isLoading={isLoading}
        />
        
        {/* Info Card */}
        <div className="mt-8 bg-slate-800/30 rounded-lg p-4 border border-slate-700">
          <div className="flex items-start gap-3">
            <svg className="w-5 h-5 text-cyan-400 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div>
              <h4 className="font-medium text-white mb-1">About Disputes</h4>
              <p className="text-sm text-slate-400">
                Disputes are resolved through evidence submission and decentralized arbitration via Kleros.
                Both parties can submit evidence during the evidence period. After that, arbitrators will
                review the case and make a binding decision. You can appeal if you believe the decision was unfair.
              </p>
            </div>
          </div>
        </div>
      </main>
      
      {/* Dispute Detail Modal */}
      {selectedDispute && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div 
            className="absolute inset-0 bg-black/80 backdrop-blur-sm"
            onClick={() => setSelectedDispute(null)}
          />
          <div className="relative z-10">
            <DisputeDetail
              dispute={selectedDispute}
              userAddress={session.address}
              onSubmitEvidence={() => handleSubmitEvidence()}
              onRespond={() => handleRespond()}
              onRequestArbitration={handleRequestArbitration}
              onAppeal={handleAppeal}
              onClose={() => setSelectedDispute(null)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
