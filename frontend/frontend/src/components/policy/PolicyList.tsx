'use client';

/**
 * PolicyList Component
 * 
 * War Room view of all policies
 * 
 * Ground Truth Reference:
 * - Policies are rules, not suggestions
 * - Clear status and activation state
 * - Statistics visible for monitoring
 */

import React from 'react';
import {
  Policy,
  PolicyStatus,
  PolicyType,
  getPolicyTypeLabel,
  getPolicyStatusColor,
} from '@/types/policy-engine';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface PolicyListProps {
  policies: Policy[];
  onSelect: (policyId: string) => void;
  onActivate?: (policyId: string) => void;
  onSuspend?: (policyId: string) => void;
  isLoading?: boolean;
  selectedId?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// STATUS BADGE
// ═══════════════════════════════════════════════════════════════════════════════

function StatusBadge({ status }: { status: PolicyStatus }) {
  const color = getPolicyStatusColor(status);
  const colorClasses: Record<string, string> = {
    green: 'bg-green-900/30 text-green-300 border-green-600/30',
    yellow: 'bg-yellow-900/30 text-yellow-300 border-yellow-600/30',
    orange: 'bg-orange-900/30 text-orange-300 border-orange-600/30',
    red: 'bg-red-900/30 text-red-300 border-red-600/30',
    gray: 'bg-slate-700/30 text-slate-300 border-slate-600/30',
    slate: 'bg-slate-800/30 text-slate-400 border-slate-600/30',
  };
  
  return (
    <span className={`px-2 py-0.5 text-xs font-medium rounded border ${colorClasses[color]}`}>
      {status}
    </span>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// POLICY CARD
// ═══════════════════════════════════════════════════════════════════════════════

function PolicyCard({
  policy,
  onSelect,
  onActivate,
  onSuspend,
  isSelected,
}: {
  policy: Policy;
  onSelect: () => void;
  onActivate?: () => void;
  onSuspend?: () => void;
  isSelected: boolean;
}) {
  const typeIcons: Record<PolicyType, string> = {
    [PolicyType.TRANSFER_LIMIT]: '💰',
    [PolicyType.VELOCITY_CHECK]: '⚡',
    [PolicyType.COUNTERPARTY_RISK]: '👤',
    [PolicyType.GEOGRAPHIC_RESTRICTION]: '🌍',
    [PolicyType.ASSET_RESTRICTION]: '🪙',
    [PolicyType.TIME_RESTRICTION]: '🕐',
    [PolicyType.KYC_REQUIREMENT]: '📋',
    [PolicyType.AML_CHECK]: '🔍',
    [PolicyType.ESCROW_TRIGGER]: '🔒',
    [PolicyType.CUSTOM]: '⚙️',
  };
  
  return (
    <div
      onClick={onSelect}
      className={`bg-slate-800/50 rounded-lg border p-4 cursor-pointer transition-all
                ${isSelected 
                  ? 'border-cyan-500 bg-slate-800' 
                  : 'border-slate-700 hover:border-slate-600'}`}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-xl">{typeIcons[policy.type]}</span>
          <div>
            <h3 className="font-medium text-white">{policy.name}</h3>
            <p className="text-xs text-slate-400">{getPolicyTypeLabel(policy.type)}</p>
          </div>
        </div>
        <StatusBadge status={policy.status} />
      </div>
      
      <p className="text-sm text-slate-400 mb-3 line-clamp-2">{policy.description}</p>
      
      {/* Stats */}
      <div className="grid grid-cols-3 gap-2 text-center mb-3">
        <div className="bg-slate-900/50 rounded p-2">
          <p className="text-lg font-bold text-white">{policy.stats?.evaluations.toLocaleString() || 0}</p>
          <p className="text-xs text-slate-500">Evaluations</p>
        </div>
        <div className="bg-slate-900/50 rounded p-2">
          <p className="text-lg font-bold text-amber-400">{policy.stats?.triggers.toLocaleString() || 0}</p>
          <p className="text-xs text-slate-500">Triggers</p>
        </div>
        <div className="bg-slate-900/50 rounded p-2">
          <p className="text-lg font-bold text-cyan-400">v{policy.version}</p>
          <p className="text-xs text-slate-500">Version</p>
        </div>
      </div>
      
      {/* Rules count */}
      <div className="flex items-center justify-between text-sm">
        <span className="text-slate-500">
          {policy.rules.length} rule{policy.rules.length !== 1 ? 's' : ''}
          {policy.rules.filter(r => r.enabled).length < policy.rules.length && 
            ` (${policy.rules.filter(r => r.enabled).length} active)`}
        </span>
        
        {/* Quick actions */}
        {(onActivate || onSuspend) && (
          <div className="flex gap-2" onClick={e => e.stopPropagation()}>
            {policy.status === PolicyStatus.DRAFT && onActivate && (
              <button
                onClick={onActivate}
                className="px-2 py-1 text-xs bg-green-600/20 text-green-400 rounded hover:bg-green-600/30"
              >
                Activate
              </button>
            )}
            {policy.status === PolicyStatus.ACTIVE && onSuspend && (
              <button
                onClick={onSuspend}
                className="px-2 py-1 text-xs bg-orange-600/20 text-orange-400 rounded hover:bg-orange-600/30"
              >
                Suspend
              </button>
            )}
            {policy.status === PolicyStatus.SUSPENDED && onActivate && (
              <button
                onClick={onActivate}
                className="px-2 py-1 text-xs bg-green-600/20 text-green-400 rounded hover:bg-green-600/30"
              >
                Reactivate
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function PolicyList({
  policies,
  onSelect,
  onActivate,
  onSuspend,
  isLoading = false,
  selectedId,
}: PolicyListProps) {
  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-slate-800/50 rounded-lg border border-slate-700 p-4 animate-pulse">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-8 h-8 bg-slate-700 rounded" />
              <div className="flex-1">
                <div className="h-4 bg-slate-700 rounded w-1/2 mb-2" />
                <div className="h-3 bg-slate-700 rounded w-1/3" />
              </div>
            </div>
            <div className="h-10 bg-slate-700 rounded mb-3" />
            <div className="grid grid-cols-3 gap-2">
              <div className="h-12 bg-slate-700 rounded" />
              <div className="h-12 bg-slate-700 rounded" />
              <div className="h-12 bg-slate-700 rounded" />
            </div>
          </div>
        ))}
      </div>
    );
  }
  
  if (policies.length === 0) {
    return (
      <div className="bg-slate-800/30 rounded-lg border border-slate-700 p-8 text-center">
        <svg className="w-12 h-12 text-slate-600 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        <h3 className="text-lg font-medium text-slate-300 mb-2">No Policies</h3>
        <p className="text-sm text-slate-500">
          Create your first policy to start enforcing rules.
        </p>
      </div>
    );
  }
  
  // Group by status
  const active = policies.filter(p => p.status === PolicyStatus.ACTIVE);
  const pending = policies.filter(p => [PolicyStatus.DRAFT, PolicyStatus.PENDING_APPROVAL].includes(p.status));
  const inactive = policies.filter(p => [PolicyStatus.SUSPENDED, PolicyStatus.DEPRECATED, PolicyStatus.ARCHIVED].includes(p.status));
  
  return (
    <div className="space-y-6">
      {/* Active Policies */}
      {active.length > 0 && (
        <section>
          <h3 className="text-sm font-medium text-slate-400 mb-3 flex items-center gap-2">
            <span className="w-2 h-2 bg-green-400 rounded-full" />
            Active ({active.length})
          </h3>
          <div className="space-y-3">
            {active.map((policy) => (
              <PolicyCard
                key={policy.id}
                policy={policy}
                onSelect={() => onSelect(policy.id)}
                onSuspend={onSuspend ? () => onSuspend(policy.id) : undefined}
                isSelected={selectedId === policy.id}
              />
            ))}
          </div>
        </section>
      )}
      
      {/* Pending Policies */}
      {pending.length > 0 && (
        <section>
          <h3 className="text-sm font-medium text-slate-400 mb-3 flex items-center gap-2">
            <span className="w-2 h-2 bg-yellow-400 rounded-full" />
            Pending ({pending.length})
          </h3>
          <div className="space-y-3">
            {pending.map((policy) => (
              <PolicyCard
                key={policy.id}
                policy={policy}
                onSelect={() => onSelect(policy.id)}
                onActivate={onActivate ? () => onActivate(policy.id) : undefined}
                isSelected={selectedId === policy.id}
              />
            ))}
          </div>
        </section>
      )}
      
      {/* Inactive Policies */}
      {inactive.length > 0 && (
        <section>
          <h3 className="text-sm font-medium text-slate-400 mb-3 flex items-center gap-2">
            <span className="w-2 h-2 bg-slate-500 rounded-full" />
            Inactive ({inactive.length})
          </h3>
          <div className="space-y-3">
            {inactive.map((policy) => (
              <PolicyCard
                key={policy.id}
                policy={policy}
                onSelect={() => onSelect(policy.id)}
                onActivate={onActivate ? () => onActivate(policy.id) : undefined}
                isSelected={selectedId === policy.id}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
