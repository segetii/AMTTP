'use client';

/**
 * What-You-Approve (WYA) Card Component
 * 
 * Ground Truth Reference:
 * - Action summary
 * - Contract + function
 * - UI Snapshot Hash
 * - Integrity Lock
 * - Checkbox required to proceed
 * 
 * Per Ground Truth v2.3:
 * - "Sign" disabled until hash acknowledged
 * - Cannot sign without viewing investigation
 * - Signature bound to snapshot hash
 */

import React, { useState, useCallback } from 'react';
import {
  GovernanceAction,
  WYASummary,
  getActionTypeLabel,
  getStatusColor,
  calculateQuorumProgress,
} from '@/types/governance';
import { useAuth } from '@/lib/auth-context';
import { signGovernanceAction, SigningResult } from '@/lib/governance-service';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface WYAApprovalCardProps {
  action: GovernanceAction;
  wyaSummary: WYASummary;
  onSign: (result: SigningResult) => void;
  onCancel: () => void;
}

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function WYAApprovalCard({
  action,
  wyaSummary,
  onSign,
  onCancel,
}: WYAApprovalCardProps) {
  const { session, role } = useAuth();
  const [hashAcknowledged, setHashAcknowledged] = useState(false);
  const [mfaVerified, setMfaVerified] = useState(false);
  const [signing, setSigning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const quorum = calculateQuorumProgress(action);
  const hasSigned = action.signatures.some(s => s.signerId === session?.userId);
  
  // Handle MFA verification (simulated)
  const handleMFAVerify = useCallback(async () => {
    // In production, this would trigger real MFA
    // For demo, we simulate a delay
    await new Promise(resolve => setTimeout(resolve, 1000));
    setMfaVerified(true);
  }, []);
  
  // Handle signing
  const handleSign = useCallback(async () => {
    if (!session?.userId || !role) return;
    
    setSigning(true);
    setError(null);
    
    try {
      // In production, this would use wallet signing
      const signatureData = `signature_${Date.now()}_${session.userId}`;
      
      const result = await signGovernanceAction(
        {
          actionId: action.id,
          signerId: session.userId,
          signerRole: role,
          signerAddress: session.address || '0x...',
          acknowledgedSnapshotHash: action.uiSnapshotHash,
          mfaMethod: 'biometric',
        },
        signatureData
      );
      
      onSign(result);
    } catch (err: any) {
      setError(err.message || 'Signing failed');
    } finally {
      setSigning(false);
    }
  }, [session, role, action, onSign]);
  
  const canSign = !hasSigned && hashAcknowledged && mfaVerified && !signing;
  
  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden max-w-2xl mx-auto">
      {/* Header */}
      <div className="bg-gradient-to-r from-cyan-600 to-blue-600 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-white">Multisig Approval</h2>
            <p className="text-cyan-100 text-sm">
              Signature {quorum.current + 1} of {quorum.required} required
            </p>
          </div>
          <div className="flex items-center gap-2 bg-white/20 px-3 py-1 rounded-full">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
                d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
            <span className="text-sm text-white font-medium">Integrity Protected</span>
          </div>
        </div>
      </div>
      
      {/* What You Are Approving */}
      <div className="p-6 space-y-6">
        <section>
          <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">
            What You Are Approving (WYA)
          </h3>
          
          <div className="bg-slate-900/50 rounded-lg p-4 space-y-3">
            <div className="flex justify-between">
              <span className="text-slate-400">Action</span>
              <span className="text-white font-medium">{getActionTypeLabel(action.type)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Target</span>
              <code className="text-cyan-400 text-sm">
                {action.targetAddress?.slice(0, 16)}...
              </code>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Scope</span>
              <span className="text-white">{wyaSummary.scopeDescription}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Duration</span>
              <span className="text-white">{wyaSummary.durationDescription}</span>
            </div>
          </div>
        </section>
        
        {/* Risk Context Summary */}
        <section>
          <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">
            Risk Context Summary
          </h3>
          
          <div className="bg-amber-900/20 border border-amber-600/30 rounded-lg p-4">
            <ul className="space-y-2">
              {wyaSummary.riskFactors.map((factor, i) => (
                <li key={i} className="flex items-start gap-2 text-amber-200">
                  <svg className="w-4 h-4 mt-0.5 text-amber-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                  </svg>
                  <span className="text-sm">{factor}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>
        
        {/* Reversibility */}
        <section>
          <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">
            Reversibility
          </h3>
          
          <div className={`rounded-lg p-4 ${
            action.isReversible 
              ? 'bg-green-900/20 border border-green-600/30' 
              : 'bg-red-900/20 border border-red-600/30'
          }`}>
            <p className={action.isReversible ? 'text-green-200' : 'text-red-200'}>
              {wyaSummary.reversibilityDescription}
            </p>
          </div>
        </section>
        
        {/* UI Integrity Verification */}
        <section className="border-t border-slate-700 pt-6">
          <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
            <svg className="w-4 h-4 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
                d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
            UI Integrity Verification
          </h3>
          
          <div className="bg-slate-900/50 rounded-lg p-4">
            <div className="flex items-center justify-between mb-4">
              <span className="text-slate-400">Snapshot Hash:</span>
              <code className="text-cyan-400 font-mono text-sm">
                {action.uiSnapshotHash.slice(0, 16)}...
              </code>
            </div>
            
            <label className="flex items-start gap-3 cursor-pointer group">
              <input
                type="checkbox"
                checked={hashAcknowledged}
                onChange={(e) => setHashAcknowledged(e.target.checked)}
                className="mt-1 w-5 h-5 rounded border-slate-600 bg-slate-700 text-cyan-500 
                         focus:ring-cyan-500 focus:ring-offset-slate-800"
              />
              <span className="text-slate-300 text-sm leading-relaxed">
                I verify that this screen matches the integrity hash and represents the 
                exact information I reviewed during investigation. I understand this 
                acknowledgement will be cryptographically bound to my signature.
              </span>
            </label>
          </div>
        </section>
        
        {/* MFA Verification */}
        <section>
          <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">
            Authentication
          </h3>
          
          {!mfaVerified ? (
            <button
              onClick={handleMFAVerify}
              disabled={!hashAcknowledged}
              className={`w-full py-3 rounded-lg font-medium transition-all ${
                hashAcknowledged
                  ? 'bg-slate-700 hover:bg-slate-600 text-white'
                  : 'bg-slate-800 text-slate-500 cursor-not-allowed'
              }`}
            >
              <span className="flex items-center justify-center gap-2">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
                    d="M12 11c0 3.517-1.009 6.799-2.753 9.571m-3.44-2.04l.054-.09A13.916 13.916 0 008 11a4 4 0 118 0c0 1.017-.07 2.019-.203 3m-2.118 6.844A21.88 21.88 0 0015.171 17m3.839 1.132c.645-2.266.99-4.659.99-7.132A8 8 0 008 4.07M3 15.364c.64-1.319 1-2.8 1-4.364 0-1.457.39-2.823 1.07-4" />
                </svg>
                Verify with Biometric / MFA
              </span>
            </button>
          ) : (
            <div className="bg-green-900/20 border border-green-600/30 rounded-lg p-3 flex items-center gap-2">
              <svg className="w-5 h-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              <span className="text-green-200">MFA Verified</span>
            </div>
          )}
        </section>
        
        {/* Error */}
        {error && (
          <div className="bg-red-900/20 border border-red-600/30 rounded-lg p-3 text-red-200 text-sm">
            {error}
          </div>
        )}
        
        {/* Actions */}
        <div className="flex gap-3 pt-4">
          <button
            onClick={onCancel}
            className="flex-1 py-3 rounded-lg font-medium bg-slate-700 hover:bg-slate-600 
                     text-white transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSign}
            disabled={!canSign}
            className={`flex-1 py-3 rounded-lg font-medium transition-all ${
              canSign
                ? 'bg-gradient-to-r from-cyan-500 to-blue-500 hover:from-cyan-600 hover:to-blue-600 text-white'
                : 'bg-slate-700 text-slate-500 cursor-not-allowed'
            }`}
          >
            {signing ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Signing...
              </span>
            ) : hasSigned ? (
              'Already Signed'
            ) : (
              'Sign Approval'
            )}
          </button>
        </div>
        
        {/* Helper text */}
        <p className="text-xs text-slate-500 text-center">
          Your signature will be cryptographically bound to the snapshot hash above.
          This proves you saw and verified this exact information before approving.
        </p>
      </div>
    </div>
  );
}
