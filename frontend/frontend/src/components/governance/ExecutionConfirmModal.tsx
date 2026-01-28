'use client';

/**
 * ExecutionConfirmModal
 * 
 * Final confirmation before executing an on-chain action after quorum is reached.
 * 
 * Ground Truth Reference:
 * - "Execution is the ceremony's climax"
 * - Shows transaction simulation results
 * - Displays gas estimates and warnings
 * - Requires final confirmation before broadcast
 */

import React, { useState, useCallback, useEffect } from 'react';
import { GovernanceAction, getActionTypeLabel, GovernanceActionType } from '@/types/governance';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface SimulationResult {
  success: boolean;
  gasEstimate: bigint;
  warnings: string[];
  stateChanges: {
    target: string;
    property: string;
    from: string;
    to: string;
  }[];
}

interface ExecutionConfirmModalProps {
  action: GovernanceAction;
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => Promise<void>;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SIMULATION
// ═══════════════════════════════════════════════════════════════════════════════

async function simulateExecution(action: GovernanceAction): Promise<SimulationResult> {
  // In production, this would call eth_estimateGas and trace_call
  await new Promise(resolve => setTimeout(resolve, 1500));
  
  const stateChanges: SimulationResult['stateChanges'] = [];
  const warnings: string[] = [];
  
  switch (action.type) {
    case GovernanceActionType.WALLET_PAUSE:
      stateChanges.push({
        target: action.targetAddress || '0x...',
        property: 'frozen',
        from: 'false',
        to: 'true',
      });
      break;
      
    case GovernanceActionType.WALLET_UNPAUSE:
      stateChanges.push({
        target: action.targetAddress || '0x...',
        property: 'frozen',
        from: 'true',
        to: 'false',
      });
      break;
      
    case GovernanceActionType.POLICY_UPDATE:
      stateChanges.push({
        target: 'PolicyEngine',
        property: 'policyVersion',
        from: '1.4.2',
        to: '1.5.0',
      });
      break;
      
    case GovernanceActionType.THRESHOLD_CHANGE:
      stateChanges.push({
        target: 'AMTTPCore',
        property: 'riskThreshold',
        from: '75',
        to: '80',
      });
      break;
      
    case GovernanceActionType.EMERGENCY_OVERRIDE:
      stateChanges.push({
        target: 'AMTTPCore',
        property: 'paused',
        from: 'false',
        to: 'true',
      });
      warnings.push('CRITICAL: All transfers will be blocked system-wide');
      break;
      
    case GovernanceActionType.ASSET_BLOCK:
      stateChanges.push({
        target: 'Blacklist',
        property: `entry[${action.targetAddress?.slice(0, 10)}...]`,
        from: 'not present',
        to: 'blocked',
      });
      break;
  }
  
  // Simulate gas estimation
  const gasEstimate = BigInt(Math.floor(150000 + Math.random() * 100000));
  
  return {
    success: true,
    gasEstimate,
    warnings,
    stateChanges,
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function ExecutionConfirmModal({
  action,
  isOpen,
  onClose,
  onConfirm,
}: ExecutionConfirmModalProps) {
  const [isSimulating, setIsSimulating] = useState(true);
  const [simulation, setSimulation] = useState<SimulationResult | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);
  const [confirmChecked, setConfirmChecked] = useState(false);
  
  // Run simulation when modal opens
  useEffect(() => {
    if (isOpen) {
      setIsSimulating(true);
      setSimulation(null);
      setConfirmChecked(false);
      
      simulateExecution(action).then(result => {
        setSimulation(result);
        setIsSimulating(false);
      });
    }
  }, [isOpen, action]);
  
  const handleConfirm = useCallback(async () => {
    setIsExecuting(true);
    try {
      await onConfirm();
    } finally {
      setIsExecuting(false);
    }
  }, [onConfirm]);
  
  if (!isOpen) return null;
  
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/80 backdrop-blur-sm"
        onClick={onClose}
      />
      
      {/* Modal */}
      <div className="relative bg-slate-900 rounded-xl border border-slate-700 shadow-2xl max-w-xl w-full mx-4 overflow-hidden">
        {/* Header */}
        <div className="bg-gradient-to-r from-amber-600 to-orange-600 px-6 py-4">
          <div className="flex items-center gap-3">
            <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <div>
              <h2 className="text-lg font-bold text-white">Execute On-Chain Action</h2>
              <p className="text-sm text-amber-100">Final confirmation required</p>
            </div>
          </div>
        </div>
        
        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Action Summary */}
          <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
            <p className="text-sm text-slate-400 mb-1">Action</p>
            <p className="font-medium text-white">{getActionTypeLabel(action.type)}</p>
            {action.targetAddress && (
              <div className="mt-2">
                <p className="text-sm text-slate-400">Target</p>
                <code className="text-cyan-400 text-sm">{action.targetAddress}</code>
              </div>
            )}
          </div>
          
          {/* Simulation Results */}
          {isSimulating ? (
            <div className="flex items-center justify-center py-8">
              <div className="flex items-center gap-3">
                <div className="animate-spin rounded-full h-5 w-5 border-2 border-cyan-500 border-t-transparent" />
                <span className="text-slate-400">Simulating transaction...</span>
              </div>
            </div>
          ) : simulation ? (
            <div className="space-y-4">
              {/* State Changes */}
              <div>
                <h3 className="text-sm font-medium text-slate-300 mb-2">State Changes</h3>
                <div className="bg-slate-800/50 rounded-lg border border-slate-700 overflow-hidden">
                  {simulation.stateChanges.map((change, idx) => (
                    <div 
                      key={idx}
                      className={`px-4 py-3 ${idx > 0 ? 'border-t border-slate-700' : ''}`}
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm text-slate-400">{change.target}</p>
                          <p className="font-mono text-sm text-white">{change.property}</p>
                        </div>
                        <div className="text-right">
                          <span className="text-red-400 text-sm">{change.from}</span>
                          <span className="text-slate-500 mx-2">→</span>
                          <span className="text-green-400 text-sm">{change.to}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              
              {/* Gas Estimate */}
              <div className="flex items-center justify-between bg-slate-800/50 rounded-lg px-4 py-3 border border-slate-700">
                <span className="text-slate-400">Gas Estimate</span>
                <span className="font-mono text-white">{simulation.gasEstimate.toLocaleString()} gas</span>
              </div>
              
              {/* Warnings */}
              {simulation.warnings.length > 0 && (
                <div className="bg-red-900/20 border border-red-600/30 rounded-lg p-4">
                  <h4 className="text-sm font-medium text-red-200 mb-2">⚠️ Warnings</h4>
                  <ul className="text-sm text-red-300 space-y-1">
                    {simulation.warnings.map((warning, idx) => (
                      <li key={idx}>{warning}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <div className="bg-red-900/20 border border-red-600/30 rounded-lg p-4">
              <p className="text-red-300">Simulation failed. Cannot proceed.</p>
            </div>
          )}
          
          {/* Confirmation Checkbox */}
          {simulation?.success && (
            <label className="flex items-start gap-3 cursor-pointer group">
              <input
                type="checkbox"
                checked={confirmChecked}
                onChange={(e) => setConfirmChecked(e.target.checked)}
                className="mt-1 h-4 w-4 rounded border-slate-500 bg-slate-800 text-amber-500 
                         focus:ring-amber-500 focus:ring-offset-slate-900"
              />
              <span className="text-sm text-slate-300 group-hover:text-white">
                I understand this action will be executed on-chain and is irreversible. 
                I have verified the state changes above match my expectations.
              </span>
            </label>
          )}
        </div>
        
        {/* Footer */}
        <div className="bg-slate-800/50 px-6 py-4 flex items-center justify-end gap-3 border-t border-slate-700">
          <button
            onClick={onClose}
            disabled={isExecuting}
            className="px-4 py-2 text-slate-300 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={!simulation?.success || !confirmChecked || isExecuting}
            className="px-6 py-2 bg-gradient-to-r from-amber-600 to-orange-600 
                     hover:from-amber-500 hover:to-orange-500 
                     disabled:from-slate-600 disabled:to-slate-600 disabled:cursor-not-allowed
                     text-white font-medium rounded-lg transition-all flex items-center gap-2"
          >
            {isExecuting ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                <span>Executing...</span>
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                <span>Execute Now</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
