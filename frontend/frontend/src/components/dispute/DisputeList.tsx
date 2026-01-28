'use client';

/**
 * DisputeList Component
 * 
 * Focus Mode view of user's disputes
 * 
 * Ground Truth Reference:
 * - Disputes are evidence-driven
 * - Clear status and next actions
 * - Timeline-aware (deadlines visible)
 */

import React from 'react';
import { DisputeSummary, DisputeStatus } from '@/types/dispute';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface DisputeListProps {
  disputes: DisputeSummary[];
  onSelect: (disputeId: string) => void;
  onSubmitEvidence?: (disputeId: string) => void;
  onRespond?: (disputeId: string) => void;
  isLoading?: boolean;
}

// ═══════════════════════════════════════════════════════════════════════════════
// STATUS BADGE
// ═══════════════════════════════════════════════════════════════════════════════

function StatusBadge({ label, color }: { label: string; color: string }) {
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
// DISPUTE CARD
// ═══════════════════════════════════════════════════════════════════════════════

function DisputeCard({ 
  dispute, 
  onSelect, 
  onSubmitEvidence, 
  onRespond 
}: { 
  dispute: DisputeSummary; 
  onSelect: () => void;
  onSubmitEvidence?: () => void;
  onRespond?: () => void;
}) {
  return (
    <div 
      className="bg-slate-800/50 rounded-xl border border-slate-700 hover:border-slate-600 
                 transition-all cursor-pointer overflow-hidden"
      onClick={onSelect}
    >
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-700 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-full flex items-center justify-center 
                        ${dispute.isClaimant ? 'bg-blue-900/50 text-blue-400' : 'bg-orange-900/50 text-orange-400'}`}>
            {dispute.isClaimant ? '⚖️' : '🛡️'}
          </div>
          <div>
            <p className="font-medium text-white">{dispute.counterparty}</p>
            <p className="text-xs text-slate-400">
              {dispute.isClaimant ? 'You filed' : 'Against you'} • {dispute.filedDate}
            </p>
          </div>
        </div>
        <StatusBadge label={dispute.statusLabel} color={dispute.statusColor} />
      </div>
      
      {/* Content */}
      <div className="px-4 py-4">
        {/* Amount */}
        <div className="flex items-baseline gap-2 mb-2">
          <span className="text-2xl font-bold text-white">{dispute.amount}</span>
          <span className="text-slate-400">{dispute.token}</span>
        </div>
        
        {/* Category */}
        <p className="text-sm text-slate-400 mb-2">{dispute.category}</p>
        
        {/* Deadline */}
        {dispute.deadline && (
          <div className="flex items-center gap-2 text-sm">
            <svg className="w-4 h-4 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
                d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="text-amber-400">Deadline: {dispute.deadline}</span>
          </div>
        )}
      </div>
      
      {/* Actions */}
      {(dispute.canSubmitEvidence || dispute.canRespond || dispute.canAppeal) && (
        <div className="px-4 py-3 bg-slate-900/50 border-t border-slate-700 flex gap-2">
          {dispute.canSubmitEvidence && onSubmitEvidence && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onSubmitEvidence();
              }}
              className="flex-1 py-2 bg-cyan-600 hover:bg-cyan-500 text-white text-sm 
                       font-medium rounded-lg transition-colors"
            >
              Submit Evidence
            </button>
          )}
          {dispute.canRespond && onRespond && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onRespond();
              }}
              className="flex-1 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm 
                       font-medium rounded-lg transition-colors"
            >
              Respond
            </button>
          )}
          {dispute.canAppeal && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onSelect();
              }}
              className="flex-1 py-2 bg-orange-600 hover:bg-orange-500 text-white text-sm 
                       font-medium rounded-lg transition-colors"
            >
              Appeal
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

export default function DisputeList({
  disputes,
  onSelect,
  onSubmitEvidence,
  onRespond,
  isLoading = false,
}: DisputeListProps) {
  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2].map((i) => (
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
  
  if (disputes.length === 0) {
    return (
      <div className="bg-slate-800/30 rounded-xl border border-slate-700 p-8 text-center">
        <svg className="w-12 h-12 text-slate-600 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3" />
        </svg>
        <h3 className="text-lg font-medium text-slate-300 mb-2">No Disputes</h3>
        <p className="text-sm text-slate-500">
          You have no active or past disputes.
        </p>
      </div>
    );
  }
  
  // Group by status
  const active = disputes.filter(d => 
    [DisputeStatus.FILED, DisputeStatus.EVIDENCE_PERIOD, DisputeStatus.AWAITING_ARBITRATION, 
     DisputeStatus.IN_ARBITRATION].includes(d.status as DisputeStatus)
  );
  const appeal = disputes.filter(d => 
    [DisputeStatus.APPEAL_PERIOD, DisputeStatus.APPEALED].includes(d.status as DisputeStatus)
  );
  const resolved = disputes.filter(d => 
    [DisputeStatus.RESOLVED, DisputeStatus.WITHDRAWN].includes(d.status as DisputeStatus)
  );
  
  return (
    <div className="space-y-6">
      {/* Active Disputes */}
      {active.length > 0 && (
        <section>
          <h3 className="text-sm font-medium text-slate-400 mb-3 flex items-center gap-2">
            <span className="w-2 h-2 bg-blue-400 rounded-full" />
            Active ({active.length})
          </h3>
          <div className="space-y-3">
            {active.map((dispute) => (
              <DisputeCard
                key={dispute.id}
                dispute={dispute}
                onSelect={() => onSelect(dispute.id)}
                onSubmitEvidence={onSubmitEvidence ? () => onSubmitEvidence(dispute.id) : undefined}
                onRespond={onRespond ? () => onRespond(dispute.id) : undefined}
              />
            ))}
          </div>
        </section>
      )}
      
      {/* Appeal Period */}
      {appeal.length > 0 && (
        <section>
          <h3 className="text-sm font-medium text-slate-400 mb-3 flex items-center gap-2">
            <span className="w-2 h-2 bg-orange-400 rounded-full" />
            Appeals ({appeal.length})
          </h3>
          <div className="space-y-3">
            {appeal.map((dispute) => (
              <DisputeCard
                key={dispute.id}
                dispute={dispute}
                onSelect={() => onSelect(dispute.id)}
              />
            ))}
          </div>
        </section>
      )}
      
      {/* Resolved */}
      {resolved.length > 0 && (
        <section>
          <h3 className="text-sm font-medium text-slate-400 mb-3 flex items-center gap-2">
            <span className="w-2 h-2 bg-slate-500 rounded-full" />
            Resolved ({resolved.length})
          </h3>
          <div className="space-y-3">
            {resolved.map((dispute) => (
              <DisputeCard
                key={dispute.id}
                dispute={dispute}
                onSelect={() => onSelect(dispute.id)}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
