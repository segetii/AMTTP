'use client';

/**
 * EscrowDetail Component
 * 
 * Detailed view of a single escrow contract
 * Shows full timeline, conditions, and available actions
 * 
 * Ground Truth Reference:
 * - Clear lifecycle visualization
 * - Actions only shown when available
 * - Risk context visible but not alarming
 */

import React, { useState } from 'react';
import {
  EscrowContract,
  EscrowStatus,
  getStatusLabel,
  getStatusColor,
  getTriggerLabel,
  calculateTimeRemaining,
  canPerformAction,
} from '@/types/escrow';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface EscrowDetailProps {
  escrow: EscrowContract;
  userAddress: string;
  onFund?: () => void;
  onRequestRelease?: () => void;
  onApproveRelease?: () => void;
  onRaiseDispute?: () => void;
  onCancel?: () => void;
  onClose: () => void;
}

// ═══════════════════════════════════════════════════════════════════════════════
// TIMELINE COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

function Timeline({ escrow }: { escrow: EscrowContract }) {
  const events = [
    { date: escrow.createdAt, label: 'Created', icon: '📝', completed: true },
    { date: escrow.fundedAt, label: 'Funded', icon: '💰', completed: !!escrow.fundedAt },
    { date: escrow.releaseRequestedAt, label: 'Release Requested', icon: '📤', completed: !!escrow.releaseRequestedAt },
    { date: escrow.releasedAt, label: 'Released', icon: '✅', completed: !!escrow.releasedAt },
  ].filter(e => e.completed || e.label === 'Created');
  
  return (
    <div className="relative">
      {/* Line */}
      <div className="absolute left-4 top-6 bottom-6 w-0.5 bg-slate-700" />
      
      {/* Events */}
      <div className="space-y-4">
        {events.map((event, idx) => (
          <div key={idx} className="flex items-start gap-4">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center z-10
                          ${event.completed ? 'bg-green-900/50 border-green-500' : 'bg-slate-800 border-slate-600'} 
                          border text-lg`}>
              {event.icon}
            </div>
            <div className="flex-1 pt-1">
              <p className={`font-medium ${event.completed ? 'text-white' : 'text-slate-500'}`}>
                {event.label}
              </p>
              {event.date && (
                <p className="text-sm text-slate-400">
                  {new Date(event.date).toLocaleString()}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// CONDITIONS CHECKLIST
// ═══════════════════════════════════════════════════════════════════════════════

function ConditionsChecklist({ escrow }: { escrow: EscrowContract }) {
  return (
    <div className="space-y-2">
      {escrow.releaseConditions.map((condition) => (
        <div 
          key={condition.id}
          className={`flex items-start gap-3 p-3 rounded-lg border
                    ${condition.met 
                      ? 'bg-green-900/20 border-green-600/30' 
                      : 'bg-slate-800/50 border-slate-700'}`}
        >
          <div className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5
                        ${condition.met ? 'bg-green-500' : 'bg-slate-700'}`}>
            {condition.met ? (
              <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
              </svg>
            ) : (
              <span className="w-2 h-2 bg-slate-500 rounded-full" />
            )}
          </div>
          <div className="flex-1">
            <p className={condition.met ? 'text-green-200' : 'text-slate-300'}>
              {condition.description}
            </p>
            {condition.metAt && (
              <p className="text-xs text-slate-500 mt-1">
                Completed: {new Date(condition.metAt).toLocaleString()}
              </p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function EscrowDetail({
  escrow,
  userAddress,
  onFund,
  onRequestRelease,
  onApproveRelease,
  onRaiseDispute,
  onCancel,
  onClose,
}: EscrowDetailProps) {
  const [activeTab, setActiveTab] = useState<'overview' | 'timeline' | 'conditions'>('overview');
  
  const isSender = escrow.sender.address.toLowerCase() === userAddress.toLowerCase();
  const statusColor = getStatusColor(escrow.status);
  
  const colorClasses: Record<string, string> = {
    green: 'from-green-600 to-emerald-600',
    yellow: 'from-yellow-600 to-amber-600',
    orange: 'from-orange-600 to-red-600',
    red: 'from-red-600 to-rose-600',
    blue: 'from-blue-600 to-cyan-600',
    gray: 'from-slate-600 to-slate-700',
  };
  
  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700 overflow-hidden max-w-2xl w-full">
      {/* Header */}
      <div className={`bg-gradient-to-r ${colorClasses[statusColor]} px-6 py-4`}>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-white/70">Escrow Contract</p>
            <h2 className="text-xl font-bold text-white">{getStatusLabel(escrow.status)}</h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/10 rounded-lg transition-colors"
          >
            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>
      
      {/* Amount Card */}
      <div className="px-6 py-4 border-b border-slate-700">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-slate-400">Amount Held</p>
            <p className="text-3xl font-bold text-white">
              {escrow.amount} <span className="text-lg text-slate-400">{escrow.token}</span>
            </p>
            <p className="text-sm text-slate-500">≈ ${escrow.amountUSD.toLocaleString()} USD</p>
          </div>
          
          {escrow.status !== EscrowStatus.RELEASED && escrow.status !== EscrowStatus.CANCELLED && (
            <div className="text-right">
              <p className="text-sm text-slate-400">Time Remaining</p>
              <p className="text-lg font-medium text-amber-400">
                {calculateTimeRemaining(escrow.expiresAt)}
              </p>
            </div>
          )}
        </div>
      </div>
      
      {/* Tabs */}
      <div className="border-b border-slate-700">
        <nav className="flex">
          {(['overview', 'timeline', 'conditions'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors
                        ${activeTab === tab 
                          ? 'border-cyan-400 text-cyan-400' 
                          : 'border-transparent text-slate-400 hover:text-white'}`}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </nav>
      </div>
      
      {/* Content */}
      <div className="p-6">
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* Parties */}
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
                <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Sender</p>
                <p className="font-medium text-white">
                  {escrow.sender.name || escrow.sender.address.slice(0, 10) + '...'}
                </p>
                {isSender && (
                  <span className="inline-block mt-1 px-2 py-0.5 text-xs bg-cyan-900/50 text-cyan-300 rounded">
                    You
                  </span>
                )}
              </div>
              <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
                <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Recipient</p>
                <p className="font-medium text-white">
                  {escrow.recipient.name || escrow.recipient.address.slice(0, 10) + '...'}
                </p>
                {!isSender && (
                  <span className="inline-block mt-1 px-2 py-0.5 text-xs bg-cyan-900/50 text-cyan-300 rounded">
                    You
                  </span>
                )}
              </div>
            </div>
            
            {/* Trigger Reason */}
            <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
              <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Why Escrow?</p>
              <p className="font-medium text-amber-300">{getTriggerLabel(escrow.trigger)}</p>
              <p className="text-sm text-slate-400 mt-1">{escrow.triggerReason}</p>
            </div>
            
            {/* Risk Score */}
            <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wide mb-1">Risk Score at Creation</p>
                  <p className="text-2xl font-bold text-white">{escrow.riskScoreAtCreation}</p>
                </div>
                <div className={`w-16 h-16 rounded-full flex items-center justify-center
                              ${escrow.riskScoreAtCreation > 70 ? 'bg-red-900/30 text-red-400' :
                                escrow.riskScoreAtCreation > 40 ? 'bg-yellow-900/30 text-yellow-400' :
                                'bg-green-900/30 text-green-400'}`}>
                  <span className="text-xs font-medium">
                    {escrow.riskScoreAtCreation > 70 ? 'HIGH' :
                     escrow.riskScoreAtCreation > 40 ? 'MED' : 'LOW'}
                  </span>
                </div>
              </div>
            </div>
            
            {/* Contract Info */}
            <div className="text-sm text-slate-500 space-y-1">
              <div className="flex justify-between">
                <span>Contract:</span>
                <code className="text-slate-400">{escrow.contractAddress.slice(0, 20)}...</code>
              </div>
              <div className="flex justify-between">
                <span>TX Hash:</span>
                <code className="text-slate-400">{escrow.txHash.slice(0, 20)}...</code>
              </div>
              <div className="flex justify-between">
                <span>Chain ID:</span>
                <span className="text-slate-400">{escrow.chainId}</span>
              </div>
            </div>
          </div>
        )}
        
        {activeTab === 'timeline' && (
          <Timeline escrow={escrow} />
        )}
        
        {activeTab === 'conditions' && (
          <ConditionsChecklist escrow={escrow} />
        )}
      </div>
      
      {/* Actions */}
      <div className="px-6 py-4 bg-slate-800/50 border-t border-slate-700">
        <div className="flex flex-wrap gap-3">
          {canPerformAction(escrow, 'fund', userAddress) && onFund && (
            <button
              onClick={onFund}
              className="flex-1 py-3 bg-gradient-to-r from-green-600 to-emerald-600 
                       hover:from-green-500 hover:to-emerald-500 text-white font-medium 
                       rounded-lg transition-all"
            >
              Fund Escrow
            </button>
          )}
          
          {canPerformAction(escrow, 'request_release', userAddress) && onRequestRelease && (
            <button
              onClick={onRequestRelease}
              className="flex-1 py-3 bg-gradient-to-r from-blue-600 to-cyan-600 
                       hover:from-blue-500 hover:to-cyan-500 text-white font-medium 
                       rounded-lg transition-all"
            >
              Request Release
            </button>
          )}
          
          {canPerformAction(escrow, 'approve_release', userAddress) && onApproveRelease && (
            <button
              onClick={onApproveRelease}
              className="flex-1 py-3 bg-gradient-to-r from-green-600 to-emerald-600 
                       hover:from-green-500 hover:to-emerald-500 text-white font-medium 
                       rounded-lg transition-all"
            >
              Approve Release
            </button>
          )}
          
          {canPerformAction(escrow, 'raise_dispute', userAddress) && onRaiseDispute && (
            <button
              onClick={onRaiseDispute}
              className="flex-1 py-3 bg-gradient-to-r from-orange-600 to-red-600 
                       hover:from-orange-500 hover:to-red-500 text-white font-medium 
                       rounded-lg transition-all"
            >
              Raise Dispute
            </button>
          )}
          
          {canPerformAction(escrow, 'cancel', userAddress) && onCancel && (
            <button
              onClick={onCancel}
              className="flex-1 py-3 bg-slate-700 hover:bg-slate-600 text-white font-medium 
                       rounded-lg transition-all"
            >
              Cancel
            </button>
          )}
          
          {/* If no actions available */}
          {!canPerformAction(escrow, 'fund', userAddress) &&
           !canPerformAction(escrow, 'request_release', userAddress) &&
           !canPerformAction(escrow, 'approve_release', userAddress) &&
           !canPerformAction(escrow, 'raise_dispute', userAddress) &&
           !canPerformAction(escrow, 'cancel', userAddress) && (
            <p className="text-sm text-slate-500 w-full text-center py-2">
              No actions available at this time
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
