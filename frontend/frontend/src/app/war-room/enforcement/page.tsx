'use client';

import { useState } from 'react';
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

const mockActions: EnforcementAction[] = [
  {
    id: '1',
    type: 'freeze',
    targetAddress: '0xSuspicious...1234',
    targetName: 'Suspected Fraud Account',
    reason: 'Multiple fraud reports, pending investigation',
    initiatedBy: 'compliance@exchange.com',
    timestamp: '2026-01-31 10:00:00',
    status: 'pending',
    requiresMultisig: true,
    approvals: 2,
    requiredApprovals: 3,
  },
  {
    id: '2',
    type: 'blacklist',
    targetAddress: '0xMixer...5678',
    reason: 'Known mixer service - OFAC sanctioned',
    initiatedBy: 'admin@exchange.com',
    timestamp: '2026-01-30 15:30:00',
    status: 'executed',
    requiresMultisig: true,
    approvals: 3,
    requiredApprovals: 3,
  },
  {
    id: '3',
    type: 'unfreeze',
    targetAddress: '0xCleared...9012',
    targetName: 'John Doe',
    reason: 'Investigation complete - no wrongdoing found',
    initiatedBy: 'legal@exchange.com',
    timestamp: '2026-01-29 11:00:00',
    status: 'executed',
    requiresMultisig: true,
    approvals: 3,
    requiredApprovals: 3,
  },
  {
    id: '4',
    type: 'limit',
    targetAddress: '0xHighRisk...3456',
    targetName: 'High Risk User',
    reason: 'Reduce daily limit to $5,000 pending enhanced due diligence',
    initiatedBy: 'compliance@exchange.com',
    timestamp: '2026-01-28 09:00:00',
    status: 'pending',
    requiresMultisig: false,
    approvals: 0,
    requiredApprovals: 1,
  },
];

export default function EnforcementPage() {
  const [actions, setActions] = useState(mockActions);
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
      default: return 'bg-slate-500/20 text-slate-400 border-slate-500/50';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'executed': return 'bg-green-500/20 text-green-400';
      case 'pending': return 'bg-yellow-500/20 text-yellow-400';
      case 'rejected': return 'bg-red-500/20 text-red-400';
      case 'expired': return 'bg-slate-500/20 text-slate-400';
      default: return 'bg-slate-500/20 text-slate-400';
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
    <div className="min-h-screen bg-slate-900 text-white p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <Link href="/war-room" className="text-slate-400 hover:text-white">
              ← War Room
            </Link>
          </div>
          <h1 className="text-3xl font-bold">Enforcement Actions</h1>
          <p className="text-slate-400 mt-1">Freeze, unfreeze, and manage account restrictions</p>
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
      <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
        <div className="p-4 border-b border-slate-700">
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
                    <div className="font-mono text-sm text-slate-400 mb-1">
                      {action.targetAddress}
                      {action.targetName && <span className="ml-2 text-slate-500">({action.targetName})</span>}
                    </div>
                    <div className="text-sm text-slate-400">{action.reason}</div>
                    <div className="text-xs text-slate-500 mt-2">
                      By {action.initiatedBy} • {action.timestamp}
                    </div>
                  </div>
                </div>
                <div className="text-right">
                  {action.requiresMultisig && (
                    <div className="mb-2">
                      <div className="text-sm text-slate-400">Approvals</div>
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
          <div className="bg-slate-800 rounded-xl p-6 max-w-lg w-full mx-4 border border-slate-700" onClick={e => e.stopPropagation()}>
            <h2 className="text-xl font-bold mb-4 capitalize">New {newActionType} Action</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">Target Address</label>
                <input 
                  type="text" 
                  placeholder="0x..." 
                  className="w-full bg-slate-700 border border-slate-600 rounded-lg px-4 py-2 focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">Reason</label>
                <textarea 
                  rows={3}
                  placeholder="Explain the reason for this action..."
                  className="w-full bg-slate-700 border border-slate-600 rounded-lg px-4 py-2 focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div className="flex items-center gap-2">
                <input type="checkbox" id="multisig" className="rounded" defaultChecked />
                <label htmlFor="multisig" className="text-sm text-slate-400">Require multisig approval (3 of 5)</label>
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
