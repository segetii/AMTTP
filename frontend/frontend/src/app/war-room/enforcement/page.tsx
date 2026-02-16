'use client';

import React, { useState } from 'react';
import Link from 'next/link';

interface EnforcementAction {
  id: string;
  type: 'freeze' | 'unfreeze' | 'blacklist' | 'whitelist' | 'limit';
  targetAddress: string;
  targetName?: string;
  reason: string;
  initiatedBy: string;
  timestamp: string;
  status: 'pending' | 'executed' | 'rejected' | 'expired';
  requiresMultisig: boolean;
  approvals: number;
  requiredApprovals: number;
}



export default function EnforcementPage() {
    const [actions, setActions] = useState<EnforcementAction[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    React.useEffect(() => {
      fetch('http://127.0.0.1:3001/monitoring/alerts')
        .then(r => { if (!r.ok) throw new Error(`API error: ${r.status} ${r.statusText}`); return r.json(); })
        .then(data => setActions(Array.isArray(data) ? data : []))
        .catch(e => setError(e.message))
        .finally(() => setLoading(false));
    }, []);
  const [showNewAction, setShowNewAction] = useState(false);
  const [newActionType, setNewActionType] = useState<'freeze' | 'unfreeze' | 'blacklist' | 'whitelist' | 'limit'>('freeze');

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'freeze': return '🧊';
      case 'unfreeze': return '🔓';
      case 'blacklist': return '⛔';
      case 'whitelist': return '✅';
      case 'limit': return '📉';
      default: return '⚡';
    }
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'freeze': return 'bg-blue-500/20 text-blue-400 border-blue-500/50';
      case 'unfreeze': return 'bg-green-500/20 text-green-400 border-green-500/50';
      case 'blacklist': return 'bg-red-500/20 text-red-400 border-red-500/50';
      case 'whitelist': return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/50';
      case 'limit': return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50';
      default: return 'bg-slate-500/20 text-mutedText border-slate-500/50';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'executed': return 'bg-green-500/20 text-green-400';
      case 'pending': return 'bg-yellow-500/20 text-yellow-400';
      case 'rejected': return 'bg-red-500/20 text-red-400';
      case 'expired': return 'bg-slate-500/20 text-mutedText';
      default: return 'bg-slate-500/20 text-mutedText';
    }
  };

  const handleApprove = (id: string) => {
    setActions(prev => prev.map(a => {
      if (a.id === id) {
        const newApprovals = a.approvals + 1;
        return {
          ...a,
          approvals: newApprovals,
          status: newApprovals >= a.requiredApprovals ? 'executed' : 'pending',
        };
      }
      return a;
    }));
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
      {error && <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 mb-4 text-red-400 text-sm">⚠ Backend unavailable: {error}</div>}
      {loading && <div className="text-zinc-500 text-sm mb-4">Loading from backend...</div>}
        <div>
          <div className="flex items-center gap-3 mb-2">
            <Link href="/war-room" className="text-mutedText hover:text-text">
              ← War Room
            </Link>
          </div>
          <h1 className="text-3xl font-bold">Enforcement Actions</h1>
          <p className="text-mutedText mt-1">Freeze, unfreeze, and manage account restrictions</p>
        </div>
        <button 
          onClick={() => setShowNewAction(true)}
          className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg flex items-center gap-2"
        >
          <span>+ New Action</span>
        </button>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-5 gap-4 mb-8">
        {(['freeze', 'unfreeze', 'blacklist', 'whitelist', 'limit'] as const).map(type => (
          <button
            key={type}
            onClick={() => { setNewActionType(type); setShowNewAction(true); }}
            className={`p-4 rounded-xl border ${getTypeColor(type)} hover:opacity-80 transition-opacity`}
          >
            <div className="text-2xl mb-2">{getTypeIcon(type)}</div>
            <div className="capitalize font-medium">{type}</div>
          </button>
        ))}
      </div>

      {/* Actions List */}
      <div className="bg-surface rounded-xl border border-borderSubtle overflow-hidden">
        <div className="p-4 border-b border-borderSubtle">
          <h2 className="font-semibold">Recent Actions</h2>
        </div>
        <div className="divide-y divide-slate-700">
          {actions.map(action => (
            <div key={action.id} className="p-4 hover:bg-slate-700/30">
              <div className="flex items-start justify-between">
                <div className="flex gap-4">
                  <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-2xl border ${getTypeColor(action.type)}`}>
                    {getTypeIcon(action.type)}
                  </div>
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-semibold capitalize">{action.type}</span>
                      <span className={`px-2 py-0.5 rounded text-xs ${getStatusColor(action.status)}`}>
                        {action.status}
                      </span>
                    </div>
                    <div className="font-mono text-sm text-mutedText mb-1">
                      {action.targetAddress}
                      {action.targetName && <span className="ml-2 text-mutedText">({action.targetName})</span>}
                    </div>
                    <div className="text-sm text-mutedText">{action.reason}</div>
                    <div className="text-xs text-mutedText mt-2">
                      By {action.initiatedBy} • {action.timestamp}
                    </div>
                  </div>
                </div>
                <div className="text-right">
                  {action.requiresMultisig && (
                    <div className="mb-2">
                      <div className="text-sm text-mutedText">Approvals</div>
                      <div className="text-lg font-semibold">
                        {action.approvals}/{action.requiredApprovals}
                      </div>
                    </div>
                  )}
                  {action.status === 'pending' && (
                    <button
                      onClick={() => handleApprove(action.id)}
                      className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded-lg text-sm"
                    >
                      Approve
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* New Action Modal */}
      {showNewAction && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setShowNewAction(false)}>
          <div className="bg-surface rounded-xl p-6 max-w-lg w-full mx-4 border border-borderSubtle" onClick={e => e.stopPropagation()}>
            <h2 className="text-xl font-bold mb-4 capitalize">New {newActionType} Action</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-mutedText mb-1">Target Address</label>
                <input 
                  type="text" 
                  placeholder="0x..." 
                  className="w-full bg-slate-700 border border-borderSubtle rounded-lg px-4 py-2 focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div>
                <label className="block text-sm text-mutedText mb-1">Reason</label>
                <textarea 
                  rows={3}
                  placeholder="Explain the reason for this action..."
                  className="w-full bg-slate-700 border border-borderSubtle rounded-lg px-4 py-2 focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div className="flex items-center gap-2">
                <input type="checkbox" id="multisig" className="rounded" defaultChecked />
                <label htmlFor="multisig" className="text-sm text-mutedText">Require multisig approval (3 of 5)</label>
              </div>
            </div>
            <div className="flex gap-3 justify-end mt-6">
              <button onClick={() => setShowNewAction(false)} className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg">
                Cancel
              </button>
              <button className={`px-4 py-2 rounded-lg ${newActionType === 'freeze' || newActionType === 'blacklist' ? 'bg-red-600 hover:bg-red-700' : 'bg-green-600 hover:bg-green-700'}`}>
                Submit Action
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
