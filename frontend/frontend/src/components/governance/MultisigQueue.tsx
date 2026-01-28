'use client';

/**
 * Multisig Queue Component
 * 
 * Ground Truth Reference:
 * - Only actions needing your signature
 * - No graphs, no noise
 * - Click → WYA screen
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  GovernanceAction,
  ActionStatus,
  getActionTypeLabel,
  getStatusColor,
  calculateQuorumProgress,
} from '@/types/governance';
import { fetchPendingActions } from '@/lib/governance-service';
import { useAuth } from '@/lib/auth-context';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface MultisigQueueProps {
  onSelectAction: (action: GovernanceAction) => void;
  className?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function MultisigQueue({ onSelectAction, className = '' }: MultisigQueueProps) {
  const { session } = useAuth();
  const [actions, setActions] = useState<GovernanceAction[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'needs_signature' | 'signed'>('all');
  
  // Fetch pending actions
  useEffect(() => {
    async function loadActions() {
      if (!session?.userId) return;
      
      setLoading(true);
      try {
        const pending = await fetchPendingActions(session.userId);
        setActions(pending);
      } catch (error) {
        console.error('Failed to load actions:', error);
      } finally {
        setLoading(false);
      }
    }
    
    loadActions();
    
    // Poll for updates
    const interval = setInterval(loadActions, 30000);
    return () => clearInterval(interval);
  }, [session?.userId]);
  
  // Filter actions
  const filteredActions = actions.filter(action => {
    const hasSigned = action.signatures.some(s => s.signerId === session?.userId);
    
    switch (filter) {
      case 'needs_signature':
        return !hasSigned;
      case 'signed':
        return hasSigned;
      default:
        return true;
    }
  });
  
  // Calculate time remaining
  const getTimeRemaining = (expiresAt: string) => {
    const remaining = new Date(expiresAt).getTime() - Date.now();
    if (remaining < 0) return 'Expired';
    
    const hours = Math.floor(remaining / (1000 * 60 * 60));
    const minutes = Math.floor((remaining % (1000 * 60 * 60)) / (1000 * 60));
    
    if (hours > 24) {
      return `${Math.floor(hours / 24)}d ${hours % 24}h`;
    }
    return `${hours}h ${minutes}m`;
  };
  
  if (loading) {
    return (
      <div className={`bg-slate-800/50 rounded-xl p-6 ${className}`}>
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-slate-700 rounded w-1/3"></div>
          <div className="h-20 bg-slate-700 rounded"></div>
          <div className="h-20 bg-slate-700 rounded"></div>
        </div>
      </div>
    );
  }
  
  return (
    <div className={`bg-slate-800/50 rounded-xl border border-slate-700 ${className}`}>
      {/* Header */}
      <div className="p-4 border-b border-slate-700">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-white">Pending Approvals</h2>
            <p className="text-sm text-slate-400">
              {filteredActions.length} action{filteredActions.length !== 1 ? 's' : ''} requiring attention
            </p>
          </div>
          
          {/* Filter */}
          <div className="flex gap-2">
            {(['all', 'needs_signature', 'signed'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-3 py-1 rounded-lg text-sm transition-colors ${
                  filter === f
                    ? 'bg-cyan-600 text-white'
                    : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
                }`}
              >
                {f === 'all' ? 'All' : f === 'needs_signature' ? 'Needs Signature' : 'Signed'}
              </button>
            ))}
          </div>
        </div>
      </div>
      
      {/* Action List */}
      <div className="divide-y divide-slate-700">
        {filteredActions.length === 0 ? (
          <div className="p-8 text-center text-slate-500">
            No pending actions
          </div>
        ) : (
          filteredActions.map((action) => {
            const quorum = calculateQuorumProgress(action);
            const hasSigned = action.signatures.some(s => s.signerId === session?.userId);
            const timeRemaining = getTimeRemaining(action.expiresAt);
            
            return (
              <div
                key={action.id}
                onClick={() => onSelectAction(action)}
                className="p-4 hover:bg-slate-700/50 cursor-pointer transition-colors"
              >
                <div className="flex items-start justify-between gap-4">
                  {/* Left: Action details */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium text-white">
                        {getActionTypeLabel(action.type)}
                      </span>
                      <span
                        className="px-2 py-0.5 rounded-full text-xs font-medium"
                        style={{ 
                          backgroundColor: `${getStatusColor(action.status)}20`,
                          color: getStatusColor(action.status),
                        }}
                      >
                        {action.status.replace('_', ' ')}
                      </span>
                      {hasSigned && (
                        <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-green-500/20 text-green-400">
                          Signed
                        </span>
                      )}
                    </div>
                    
                    <p className="text-sm text-slate-400 truncate">
                      {action.riskContext.summary}
                    </p>
                    
                    <div className="flex items-center gap-4 mt-2 text-xs text-slate-500">
                      <span>
                        Target: {action.targetAddress?.slice(0, 10)}...
                      </span>
                      <span>
                        Policy: {action.policyVersion}
                      </span>
                    </div>
                  </div>
                  
                  {/* Right: Quorum & Time */}
                  <div className="text-right">
                    <div className="flex items-center gap-2 mb-2">
                      <div className="w-24 h-2 bg-slate-700 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-cyan-500 transition-all"
                          style={{ width: `${quorum.percentage}%` }}
                        />
                      </div>
                      <span className="text-sm text-slate-400">
                        {quorum.current}/{quorum.required}
                      </span>
                    </div>
                    
                    <div className={`text-sm ${
                      timeRemaining === 'Expired' ? 'text-red-400' : 'text-slate-400'
                    }`}>
                      {timeRemaining}
                    </div>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
