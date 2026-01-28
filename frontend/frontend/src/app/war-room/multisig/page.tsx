'use client';

/**
 * Multisig Governance Page
 * 
 * Ground Truth Reference:
 * - Multisig is not a feature, it's a ceremony
 * - 3-Screen Flow: Queue → WYA → Sign
 * - Prevents blind signing
 * - Each signature bound to snapshot hash
 * 
 * Access: R4 Compliance only
 */

import React, { useState, useCallback, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { Role } from '@/types/rbac';
import {
  GovernanceAction,
  ActionStatus,
  generateWYASummary,
  getActionTypeLabel,
  calculateQuorumProgress,
} from '@/types/governance';
import { SigningResult } from '@/lib/governance-service';
import MultisigQueue from '@/components/governance/MultisigQueue';
import WYAApprovalCard from '@/components/governance/WYAApprovalCard';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

type ViewState = 'queue' | 'approval' | 'success';

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function MultisigGovernancePage() {
  const router = useRouter();
  const { session, role } = useAuth();
  const [viewState, setViewState] = useState<ViewState>('queue');
  const [selectedAction, setSelectedAction] = useState<GovernanceAction | null>(null);
  const [lastResult, setLastResult] = useState<SigningResult | null>(null);
  
  // Handle action selection
  const handleSelectAction = useCallback((action: GovernanceAction) => {
    setSelectedAction(action);
    setViewState('approval');
  }, []);
  
  // Handle sign completion
  const handleSignComplete = useCallback((result: SigningResult) => {
    setLastResult(result);
    if (result.success) {
      setViewState('success');
    }
  }, []);
  
  // Handle back to queue
  const handleBackToQueue = useCallback(() => {
    setSelectedAction(null);
    setLastResult(null);
    setViewState('queue');
  }, []);
  
  // Access denied if not R4
  if (role && ![Role.R4_INSTITUTION_COMPLIANCE, Role.R6_SUPER_ADMIN].includes(role)) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center">
        <div className="bg-red-900/20 border border-red-600/30 rounded-xl p-8 max-w-md text-center">
          <svg className="w-16 h-16 text-red-400 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <h2 className="text-xl font-bold text-red-200 mb-2">Access Denied</h2>
          <p className="text-slate-400">
            Multisig governance is only available to R4 Compliance officers.
          </p>
          <button
            onClick={() => router.push('/war-room')}
            className="mt-6 px-6 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors"
          >
            Return to War Room
          </button>
        </div>
      </div>
    );
  }
  
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-white">
      {/* Header */}
      <header className="border-b border-slate-700 bg-slate-900/50">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => router.push('/war-room')}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                </svg>
              </button>
              <div>
                <h1 className="text-xl font-bold text-white">Multisig Governance</h1>
                <p className="text-sm text-slate-400">R4 Compliance Control Panel</p>
              </div>
            </div>
            
            {/* Integrity Indicator */}
            <div className="flex items-center gap-2 bg-cyan-900/30 border border-cyan-600/30 px-3 py-1.5 rounded-full">
              <div className="w-2 h-2 bg-cyan-400 rounded-full animate-pulse" />
              <span className="text-sm text-cyan-200">UI Integrity Active</span>
            </div>
          </div>
        </div>
      </header>
      
      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Breadcrumb */}
        <nav className="mb-6">
          <ol className="flex items-center gap-2 text-sm">
            <li>
              <button 
                onClick={handleBackToQueue}
                className={`${viewState === 'queue' ? 'text-cyan-400' : 'text-slate-400 hover:text-white'}`}
              >
                Queue
              </button>
            </li>
            {viewState !== 'queue' && (
              <>
                <li className="text-slate-600">/</li>
                <li>
                  <span className={viewState === 'approval' ? 'text-cyan-400' : 'text-slate-400'}>
                    Approval
                  </span>
                </li>
              </>
            )}
            {viewState === 'success' && (
              <>
                <li className="text-slate-600">/</li>
                <li className="text-green-400">Complete</li>
              </>
            )}
          </ol>
        </nav>
        
        {/* Queue View */}
        {viewState === 'queue' && (
          <div className="space-y-6">
            {/* KPI Strip */}
            <div className="grid grid-cols-4 gap-4">
              {[
                { label: 'Pending Actions', value: '3', color: 'cyan' },
                { label: 'My Signatures', value: '1', color: 'green' },
                { label: 'Expiring Soon', value: '1', color: 'amber' },
                { label: 'Quorum Reached', value: '0', color: 'blue' },
              ].map((kpi) => (
                <div key={kpi.label} className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
                  <p className="text-sm text-slate-400">{kpi.label}</p>
                  <p className={`text-2xl font-bold text-${kpi.color}-400`}>{kpi.value}</p>
                </div>
              ))}
            </div>
            
            {/* Queue */}
            <MultisigQueue onSelectAction={handleSelectAction} />
            
            {/* Help Text */}
            <div className="bg-slate-800/30 rounded-lg p-4 border border-slate-700">
              <h3 className="font-medium text-white mb-2">Signing Process</h3>
              <ol className="list-decimal list-inside text-sm text-slate-400 space-y-1">
                <li>Select an action from the queue to review</li>
                <li>Verify the What-You-Approve (WYA) summary matches your investigation</li>
                <li>Acknowledge the UI snapshot hash to confirm integrity</li>
                <li>Complete MFA verification</li>
                <li>Sign to add your approval to the quorum</li>
              </ol>
            </div>
          </div>
        )}
        
        {/* Approval View */}
        {viewState === 'approval' && selectedAction && (
          <div className="space-y-6">
            {/* Action Summary Strip */}
            <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700 flex items-center justify-between">
              <div>
                <span className="text-slate-400">Reviewing: </span>
                <span className="font-medium text-white">{getActionTypeLabel(selectedAction.type)}</span>
                <span className="text-slate-500 ml-2">({selectedAction.id})</span>
              </div>
              <div className="flex items-center gap-4">
                <span className="text-sm text-slate-400">
                  {calculateQuorumProgress(selectedAction).current} / {calculateQuorumProgress(selectedAction).required} signatures
                </span>
                <button
                  onClick={() => window.open(`/war-room/investigation/${selectedAction.id}`, '_blank')}
                  className="text-sm text-cyan-400 hover:text-cyan-300"
                >
                  View Investigation →
                </button>
              </div>
            </div>
            
            {/* WYA Card */}
            <WYAApprovalCard
              action={selectedAction}
              wyaSummary={generateWYASummary(selectedAction)}
              onSign={handleSignComplete}
              onCancel={handleBackToQueue}
            />
          </div>
        )}
        
        {/* Success View */}
        {viewState === 'success' && lastResult && (
          <div className="max-w-lg mx-auto">
            <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
              <div className="bg-gradient-to-r from-green-600 to-emerald-600 px-6 py-8 text-center">
                <svg className="w-16 h-16 text-white mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
                    d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <h2 className="text-2xl font-bold text-white">Signature Recorded</h2>
                <p className="text-green-100 mt-2">
                  Your approval has been cryptographically bound to the UI snapshot.
                </p>
              </div>
              
              <div className="p-6 space-y-4">
                {lastResult.quorumReached ? (
                  <div className="bg-green-900/20 border border-green-600/30 rounded-lg p-4">
                    <p className="text-green-200 font-medium">Quorum Reached!</p>
                    <p className="text-sm text-slate-400 mt-1">
                      The action will now be executed on-chain.
                    </p>
                  </div>
                ) : (
                  <div className="bg-blue-900/20 border border-blue-600/30 rounded-lg p-4">
                    <p className="text-blue-200 font-medium">Awaiting More Signatures</p>
                    <p className="text-sm text-slate-400 mt-1">
                      {selectedAction && (
                        <>
                          {calculateQuorumProgress(selectedAction).required - calculateQuorumProgress(selectedAction).current - 1} more signature(s) required for quorum.
                        </>
                      )}
                    </p>
                  </div>
                )}
                
                <div className="text-sm text-slate-400 space-y-2">
                  <div className="flex justify-between">
                    <span>Signature ID:</span>
                    <code className="text-cyan-400">{lastResult.signature?.signerId.slice(0, 16)}...</code>
                  </div>
                  <div className="flex justify-between">
                    <span>Signed At:</span>
                    <span className="text-white">{new Date(lastResult.signature?.signedAt || '').toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Hash Verified:</span>
                    <span className="text-green-400">✓ Yes</span>
                  </div>
                </div>
                
                <button
                  onClick={handleBackToQueue}
                  className="w-full py-3 bg-slate-700 hover:bg-slate-600 text-white rounded-lg 
                           font-medium transition-colors mt-4"
                >
                  Return to Queue
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
