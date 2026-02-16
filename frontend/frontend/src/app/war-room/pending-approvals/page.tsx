'use client';

import React, { useState } from 'react';
import Link from 'next/link';

interface PendingApproval {
  id: string;
  type: 'transfer' | 'policy_change' | 'user_action' | 'enforcement';
  title: string;
  description: string;
  requestedBy: string;
  timestamp: string;
  priority: 'low' | 'medium' | 'high' | 'urgent';
  amount?: string;
  token?: string;
  from?: string;
  to?: string;
  approvals: { user: string; timestamp: string }[];
  requiredApprovals: number;
}



export default function PendingApprovalsPage() {
  const [approvals, setApprovals] = useState<PendingApproval[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  React.useEffect(() => {
    fetch('http://127.0.0.1:3001/risk/reviews')
      .then(r => { if (!r.ok) throw new Error(`API error: ${r.status} ${r.statusText}`); return r.json(); })
      .then(data => setApprovals(Array.isArray(data) ? data : []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'transfer': return '💸';
      case 'policy_change': return '📜';
      case 'enforcement': return '🔒';
      case 'user_action': return '👤';
      default: return '📋';
    }
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'transfer': return 'bg-green-500/20 text-green-400';
      case 'policy_change': return 'bg-blue-500/20 text-blue-400';
      case 'enforcement': return 'bg-red-500/20 text-red-400';
      case 'user_action': return 'bg-purple-500/20 text-purple-400';
      default: return 'bg-slate-500/20 text-mutedText';
    }
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'urgent': return 'bg-red-500 text-text';
      case 'high': return 'bg-orange-500/20 text-orange-400';
      case 'medium': return 'bg-yellow-500/20 text-yellow-400';
      case 'low': return 'bg-slate-500/20 text-mutedText';
      default: return 'bg-slate-500/20 text-mutedText';
    }
  };

  const handleApprove = (id: string) => {
    setApprovals(prev => prev.map(a => {
      if (a.id === id) {
        return {
          ...a,
          approvals: [...a.approvals, { user: 'you@exchange.com', timestamp: new Date().toISOString() }],
        };
      }
      return a;
    }));
  };

  const handleReject = (id: string) => {
    setApprovals(prev => prev.filter(a => a.id !== id));
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <Link href="/war-room" className="text-mutedText hover:text-text">
              ← War Room
            </Link>
          </div>
          <h1 className="text-3xl font-bold">Pending Approvals</h1>
          <p className="text-mutedText mt-1">Review and approve pending requests</p>
        </div>
        <div className="flex items-center gap-4">
          <span className="px-3 py-1 bg-yellow-500/20 text-yellow-400 rounded-full text-sm">
            {approvals.length} Pending
          </span>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <div className="bg-surface rounded-xl p-4 border border-borderSubtle">
          <div className="text-2xl font-bold text-green-400">{approvals.filter(a => a.type === 'transfer').length}</div>
          <div className="text-mutedText text-sm">Transfers</div>
        </div>
        <div className="bg-surface rounded-xl p-4 border border-borderSubtle">
          <div className="text-2xl font-bold text-blue-400">{approvals.filter(a => a.type === 'policy_change').length}</div>
          <div className="text-mutedText text-sm">Policy Changes</div>
        </div>
        <div className="bg-surface rounded-xl p-4 border border-borderSubtle">
          <div className="text-2xl font-bold text-red-400">{approvals.filter(a => a.type === 'enforcement').length}</div>
          <div className="text-mutedText text-sm">Enforcement</div>
        </div>
        <div className="bg-surface rounded-xl p-4 border border-borderSubtle">
          <div className="text-2xl font-bold text-purple-400">{approvals.filter(a => a.type === 'user_action').length}</div>
          <div className="text-mutedText text-sm">User Actions</div>
        </div>
      </div>

      {/* Approvals List */}
      <div className="space-y-4">
        {approvals.map(approval => (
          <div key={approval.id} className="bg-surface rounded-xl p-6 border border-borderSubtle">
            <div className="flex items-start justify-between">
              <div className="flex gap-4">
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-2xl ${getTypeColor(approval.type)}`}>
                  {getTypeIcon(approval.type)}
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-1">
                    <h3 className="font-semibold">{approval.title}</h3>
                    <span className={`px-2 py-0.5 rounded text-xs ${getTypeColor(approval.type)}`}>
                      {approval.type.replace('_', ' ')}
                    </span>
                    <span className={`px-2 py-0.5 rounded text-xs ${getPriorityColor(approval.priority)}`}>
                      {approval.priority}
                    </span>
                  </div>
                  <p className="text-mutedText text-sm mb-2">{approval.description}</p>
                  
                  {approval.type === 'transfer' && approval.amount && (
                    <div className="bg-slate-700/50 rounded-lg p-3 mb-3 inline-block">
                      <span className="text-2xl font-bold">{approval.amount}</span>
                      <span className="text-mutedText ml-2">{approval.token}</span>
                      <div className="text-sm text-mutedText mt-1">
                        {approval.from} → {approval.to}
                      </div>
                    </div>
                  )}
                  
                  <div className="text-xs text-mutedText">
                    Requested by {approval.requestedBy} • {approval.timestamp}
                  </div>
                </div>
              </div>
              
              <div className="text-right">
                <div className="mb-3">
                  <div className="text-sm text-mutedText mb-1">Approvals</div>
                  <div className="flex items-center gap-1 justify-end">
                    {Array.from({ length: approval.requiredApprovals }).map((_, i) => (
                      <div 
                        key={i}
                        className={`w-3 h-3 rounded-full ${i < approval.approvals.length ? 'bg-green-500' : 'bg-slate-600'}`}
                      />
                    ))}
                    <span className="text-sm ml-2">{approval.approvals.length}/{approval.requiredApprovals}</span>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleReject(approval.id)}
                    className="px-4 py-2 bg-red-600/20 text-red-400 hover:bg-red-600/30 rounded-lg text-sm"
                  >
                    Reject
                  </button>
                  <button
                    onClick={() => handleApprove(approval.id)}
                    className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded-lg text-sm"
                  >
                    Approve
                  </button>
                </div>
              </div>
            </div>
            
            {approval.approvals.length > 0 && (
              <div className="mt-4 pt-4 border-t border-borderSubtle">
                <div className="text-sm text-mutedText mb-2">Approval History</div>
                <div className="flex flex-wrap gap-2">
                  {approval.approvals.map((a, i) => (
                    <div key={i} className="bg-green-500/10 border border-green-500/30 rounded-lg px-3 py-1 text-sm">
                      <span className="text-green-400">✓</span> {a.user}
                      <span className="text-mutedText ml-2 text-xs">{a.timestamp}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
      {error && <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 mb-4 text-red-400 text-sm">⚠ Backend unavailable: {error}</div>}
      {loading && <div className="text-zinc-500 text-sm mb-4">Loading from backend...</div>}
    </div>
  );
}
