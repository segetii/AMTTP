'use client';

/**
 * EscrowList Component
 * 
 * Focus Mode view of user's escrow contracts
 * 
 * Ground Truth Reference:
 * - Focus Mode: simplified status, clear actions
 * - Shows what user CAN do, not technical details
 * - Color-coded status for instant comprehension
 */

import React from 'react';
import {
  EscrowSummary,
  EscrowStatus,
} from '@/types/escrow';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface EscrowListProps {
  escrows: EscrowSummary[];
  onSelect: (escrowId: string) => void;
  onRequestRelease?: (escrowId: string) => void;
  onRaiseDispute?: (escrowId: string) => void;
  isLoading?: boolean;
}

// ═══════════════════════════════════════════════════════════════════════════════
// STATUS BADGE
// ═══════════════════════════════════════════════════════════════════════════════

function StatusBadge({ status, label, color }: { status: EscrowStatus; label: string; color: string }) {
  const colorClasses: Record<string, string> = {
    green: 'bg-green-900/30 text-green-300 border-green-600/30',
    yellow: 'bg-yellow-900/30 text-yellow-300 border-yellow-600/30',
    orange: 'bg-orange-900/30 text-orange-300 border-orange-600/30',
    red: 'bg-red-900/30 text-red-300 border-red-600/30',
    blue: 'bg-blue-900/30 text-blue-300 border-blue-600/30',
    gray: 'bg-slate-700/30 text-slate-300 border-slate-600/30',
  };
  
  return (
    <span className={`px-2 py-1 text-xs font-medium rounded-full border ${colorClasses[color]}`}>
      {label}
    </span>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// ESCROW CARD
// ═══════════════════════════════════════════════════════════════════════════════

function EscrowCard({ 
  escrow, 
  onSelect, 
  onRequestRelease, 
  onRaiseDispute 
}: { 
  escrow: EscrowSummary; 
  onSelect: () => void;
  onRequestRelease?: () => void;
  onRaiseDispute?: () => void;
}) {
  const riskColors = {
    low: 'text-green-400',
    medium: 'text-yellow-400',
    high: 'text-red-400',
  };
  
  return (
    <div 
      className="bg-slate-800/50 rounded-xl border border-slate-700 hover:border-slate-600 
                 transition-all cursor-pointer overflow-hidden"
      onClick={onSelect}
    >
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-700 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 
                        flex items-center justify-center text-white font-bold">
            {escrow.counterparty.slice(0, 2).toUpperCase()}
          </div>
          <div>
            <p className="font-medium text-white">{escrow.counterparty}</p>
            <p className="text-xs text-slate-400">{escrow.createdDate}</p>
          </div>
        </div>
        <StatusBadge 
          status={escrow.status} 
          label={escrow.statusLabel} 
          color={escrow.statusColor} 
        />
      </div>
      
      {/* Amount */}
      <div className="px-4 py-4">
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-bold text-white">{escrow.amount}</span>
          <span className="text-slate-400">{escrow.token}</span>
        </div>
        
        {/* Timeline */}
        {escrow.timeRemaining && (
          <div className="mt-2 flex items-center gap-2 text-sm">
            <svg className="w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
                d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="text-slate-400">{escrow.timeRemaining}</span>
          </div>
        )}
        
        {/* Risk indicator */}
        <div className="mt-2 flex items-center gap-2 text-sm">
          <span className="text-slate-500">Risk:</span>
          <span className={`font-medium ${riskColors[escrow.riskLevel]}`}>
            {escrow.riskLevel.toUpperCase()}
          </span>
        </div>
      </div>
      
      {/* Actions */}
      {(escrow.canRequestRelease || escrow.canRaiseDispute) && (
        <div className="px-4 py-3 bg-slate-900/50 border-t border-slate-700 flex gap-2">
          {escrow.canRequestRelease && onRequestRelease && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onRequestRelease();
              }}
              className="flex-1 py-2 bg-green-600 hover:bg-green-500 text-white text-sm 
                       font-medium rounded-lg transition-colors"
            >
              Request Release
            </button>
          )}
          {escrow.canRaiseDispute && onRaiseDispute && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onRaiseDispute();
              }}
              className="flex-1 py-2 bg-orange-600 hover:bg-orange-500 text-white text-sm 
                       font-medium rounded-lg transition-colors"
            >
              Raise Dispute
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function EscrowList({
  escrows,
  onSelect,
  onRequestRelease,
  onRaiseDispute,
  isLoading = false,
}: EscrowListProps) {
  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-slate-800/50 rounded-xl border border-slate-700 p-4 animate-pulse">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-slate-700" />
              <div className="flex-1">
                <div className="h-4 bg-slate-700 rounded w-1/3 mb-2" />
                <div className="h-3 bg-slate-700 rounded w-1/4" />
              </div>
            </div>
            <div className="h-8 bg-slate-700 rounded w-1/2" />
          </div>
        ))}
      </div>
    );
  }
  
  if (escrows.length === 0) {
    return (
      <div className="bg-slate-800/30 rounded-xl border border-slate-700 p-8 text-center">
        <svg className="w-12 h-12 text-slate-600 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
        </svg>
        <h3 className="text-lg font-medium text-slate-300 mb-2">No Escrows</h3>
        <p className="text-sm text-slate-500">
          Escrow contracts will appear here when transfers require additional protection.
        </p>
      </div>
    );
  }
  
  // Group by status
  const active = escrows.filter(e => 
    [EscrowStatus.PENDING_FUNDING, EscrowStatus.FUNDED, EscrowStatus.RELEASE_REQUESTED, EscrowStatus.RELEASING]
      .includes(e.status as EscrowStatus)
  );
  const disputed = escrows.filter(e => 
    [EscrowStatus.DISPUTE_RAISED, EscrowStatus.IN_ARBITRATION].includes(e.status as EscrowStatus)
  );
  const completed = escrows.filter(e => 
    [EscrowStatus.RELEASED, EscrowStatus.RESOLVED_TO_SENDER, EscrowStatus.RESOLVED_TO_RECIPIENT, 
     EscrowStatus.RESOLVED_SPLIT, EscrowStatus.EXPIRED, EscrowStatus.CANCELLED].includes(e.status as EscrowStatus)
  );
  
  return (
    <div className="space-y-6">
      {/* Active Escrows */}
      {active.length > 0 && (
        <section>
          <h3 className="text-sm font-medium text-slate-400 mb-3 flex items-center gap-2">
            <span className="w-2 h-2 bg-blue-400 rounded-full" />
            Active ({active.length})
          </h3>
          <div className="space-y-3">
            {active.map((escrow) => (
              <EscrowCard
                key={escrow.id}
                escrow={escrow}
                onSelect={() => onSelect(escrow.id)}
                onRequestRelease={onRequestRelease ? () => onRequestRelease(escrow.id) : undefined}
                onRaiseDispute={onRaiseDispute ? () => onRaiseDispute(escrow.id) : undefined}
              />
            ))}
          </div>
        </section>
      )}
      
      {/* Disputed */}
      {disputed.length > 0 && (
        <section>
          <h3 className="text-sm font-medium text-slate-400 mb-3 flex items-center gap-2">
            <span className="w-2 h-2 bg-orange-400 rounded-full" />
            Under Dispute ({disputed.length})
          </h3>
          <div className="space-y-3">
            {disputed.map((escrow) => (
              <EscrowCard
                key={escrow.id}
                escrow={escrow}
                onSelect={() => onSelect(escrow.id)}
              />
            ))}
          </div>
        </section>
      )}
      
      {/* Completed */}
      {completed.length > 0 && (
        <section>
          <h3 className="text-sm font-medium text-slate-400 mb-3 flex items-center gap-2">
            <span className="w-2 h-2 bg-slate-500 rounded-full" />
            Completed ({completed.length})
          </h3>
          <div className="space-y-3">
            {completed.map((escrow) => (
              <EscrowCard
                key={escrow.id}
                escrow={escrow}
                onSelect={() => onSelect(escrow.id)}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
