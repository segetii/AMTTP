'use client';

import React, { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { useEscrow } from '@/lib/escrow-service';
import { EscrowContract } from '@/types/escrow';
import EscrowList from '@/components/escrow/EscrowList';
import EscrowDetail from '@/components/escrow/EscrowDetail';

export default function EscrowContent() {
  const router = useRouter();
  const { session, isAuthenticated, isLoading: authLoading } = useAuth();
  const [selectedEscrow, setSelectedEscrow] = useState<EscrowContract | null>(null);
  
  const {
    escrows,
    summaries,
    isLoading,
    error,
    fund,
    requestRelease,
    approveRelease,
    raiseDispute,
    refresh,
  } = useEscrow(session?.address || null);
  
  // Handle escrow selection
  const handleSelectEscrow = useCallback((escrowId: string) => {
    const escrow = escrows.find(e => e.id === escrowId);
    if (escrow) {
      setSelectedEscrow(escrow);
    }
  }, [escrows]);
  
  // Handle actions
  const handleFund = useCallback(async () => {
    if (!selectedEscrow) return;
    const result = await fund({
      escrowId: selectedEscrow.id,
      amount: selectedEscrow.amount,
      token: selectedEscrow.token,
    });
    if (result.success) {
      setSelectedEscrow(result.data || null);
    }
  }, [selectedEscrow, fund]);
  
  const handleRequestRelease = useCallback(async (escrowId?: string) => {
    const id = escrowId || selectedEscrow?.id;
    if (!id) return;
    const result = await requestRelease({ escrowId: id });
    if (result.success && result.data) {
      setSelectedEscrow(result.data);
    }
  }, [selectedEscrow, requestRelease]);
  
  const handleApproveRelease = useCallback(async () => {
    if (!selectedEscrow) return;
    const result = await approveRelease(selectedEscrow.id);
    if (result.success && result.data) {
      setSelectedEscrow(result.data);
    }
  }, [selectedEscrow, approveRelease]);
  
  const handleRaiseDispute = useCallback(async (escrowId?: string) => {
    const id = escrowId || selectedEscrow?.id;
    if (!id) return;
    const result = await raiseDispute({
      escrowId: id,
      reason: 'Transaction dispute',
      evidenceHashes: [],
      requestedOutcome: 'full_refund',
    });
    if (result.success && result.data) {
      setSelectedEscrow(result.data.escrow);
    }
  }, [selectedEscrow, raiseDispute]);
  
  // Loading state
  if (authLoading || isLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 
                    flex items-center justify-center">
        <div className="flex items-center gap-3">
          <div className="animate-spin rounded-full h-6 w-6 border-2 border-cyan-500 border-t-transparent" />
          <span className="text-slate-400">Loading escrows...</span>
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
              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
          <h2 className="text-xl font-bold text-white mb-2">Connect Wallet</h2>
          <p className="text-slate-400 mb-6">
            Connect your wallet to view escrow contracts.
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
                <h1 className="text-xl font-bold text-white">Protected Transfers</h1>
                <p className="text-sm text-slate-400">Escrow contracts for secure transactions</p>
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
        <div className="grid grid-cols-3 gap-4 mb-8">
          {[
            { 
              label: 'Active', 
              value: summaries.filter(s => ['PENDING_FUNDING', 'FUNDED', 'RELEASE_REQUESTED'].includes(s.status)).length,
              color: 'blue'
            },
            { 
              label: 'In Dispute', 
              value: summaries.filter(s => ['DISPUTE_RAISED', 'IN_ARBITRATION'].includes(s.status)).length,
              color: 'orange'
            },
            { 
              label: 'Completed', 
              value: summaries.filter(s => ['RELEASED', 'RESOLVED_TO_SENDER', 'RESOLVED_TO_RECIPIENT'].includes(s.status)).length,
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
        
        {/* Escrow List */}
        <EscrowList
          escrows={summaries}
          onSelect={handleSelectEscrow}
          onRequestRelease={handleRequestRelease}
          onRaiseDispute={handleRaiseDispute}
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
              <h4 className="font-medium text-white mb-1">About Protected Transfers</h4>
              <p className="text-sm text-slate-400">
                When a transfer involves elevated risk, funds are held in escrow for a lock period.
                This protects both parties while allowing time to verify the transaction.
                You can raise a dispute during the lock period if something seems wrong.
              </p>
            </div>
          </div>
        </div>
      </main>
      
      {/* Escrow Detail Modal */}
      {selectedEscrow && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div 
            className="absolute inset-0 bg-black/80 backdrop-blur-sm"
            onClick={() => setSelectedEscrow(null)}
          />
          <div className="relative z-10">
            <EscrowDetail
              escrow={selectedEscrow}
              userAddress={session.address}
              onFund={handleFund}
              onRequestRelease={() => handleRequestRelease()}
              onApproveRelease={handleApproveRelease}
              onRaiseDispute={() => handleRaiseDispute()}
              onClose={() => setSelectedEscrow(null)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
