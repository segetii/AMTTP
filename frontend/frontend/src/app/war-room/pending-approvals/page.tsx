'use client';

import { useState } from 'react';
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

const mockApprovals: PendingApproval[] = [
  {
    id: '1',
    type: 'transfer',
    title: 'Large Transfer Approval',
    description: 'Transfer exceeds daily limit threshold',
    requestedBy: '0xAlice...1234',
    timestamp: '2026-01-31 14:00:00',
    priority: 'high',
    amount: '75,000',
    token: 'USDC',
    from: '0xAlice...1234',
    to: '0xBob...5678',
    approvals: [
      { user: 'compliance@exchange.com', timestamp: '2026-01-31 14:05:00' },
    ],
    requiredApprovals: 2,
  },
  {
    id: '2',
    type: 'policy_change',
    title: 'Velocity Limit Update',
    description: 'Increase daily limit for premium users to $100,000',
    requestedBy: 'admin@exchange.com',
    timestamp: '2026-01-31 12:00:00',
    priority: 'medium',
    approvals: [],
    requiredApprovals: 3,
  },
  {
    id: '3',
    type: 'enforcement',
    title: 'Account Freeze Request',
    description: 'Freeze account 0xSuspect...9012 due to fraud investigation',
    requestedBy: 'legal@exchange.com',
    timestamp: '2026-01-31 10:30:00',
    priority: 'urgent',
    approvals: [
      { user: 'compliance@exchange.com', timestamp: '2026-01-31 10:45:00' },
      { user: 'admin@exchange.com', timestamp: '2026-01-31 11:00:00' },
    ],
    requiredApprovals: 3,
  },
  {
    id: '4',
    type: 'user_action',
    title: 'New Approver Addition',
    description: 'Add jane@exchange.com as a compliance approver',
    requestedBy: 'admin@exchange.com',
    timestamp: '2026-01-30 16:00:00',
    priority: 'low',
    approvals: [
      { user: 'super@exchange.com', timestamp: '2026-01-30 16:30:00' },
    ],
    requiredApprovals: 2,
  },
];

export default function PendingApprovalsPage() {
  const [approvals, setApprovals] = useState(mockApprovals);

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
      default: return 'bg-slate-500/20 text-slate-400';
    }
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'urgent': return 'bg-red-500 text-white';
      case 'high': return 'bg-orange-500/20 text-orange-400';
      case 'medium': return 'bg-yellow-500/20 text-yellow-400';
      case 'low': return 'bg-slate-500/20 text-slate-400';
      default: return 'bg-slate-500/20 text-slate-400';
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
    <div className="min-h-screen bg-slate-900 text-white p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <Link href="/war-room" className="text-slate-400 hover:text-white">
              ← War Room
            </Link>
          </div>
          <h1 className="text-3xl font-bold">Pending Approvals</h1>
          <p className="text-slate-400 mt-1">Review and approve pending requests</p>
        </div>
        <div className="flex items-center gap-4">
          <span className="px-3 py-1 bg-yellow-500/20 text-yellow-400 rounded-full text-sm">
            {approvals.length} Pending
          </span>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
          <div className="text-2xl font-bold text-green-400">{approvals.filter(a => a.type === 'transfer').length}</div>
          <div className="text-slate-400 text-sm">Transfers</div>
        </div>
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
          <div className="text-2xl font-bold text-blue-400">{approvals.filter(a => a.type === 'policy_change').length}</div>
          <div className="text-slate-400 text-sm">Policy Changes</div>
        </div>
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
          <div className="text-2xl font-bold text-red-400">{approvals.filter(a => a.type === 'enforcement').length}</div>
          <div className="text-slate-400 text-sm">Enforcement</div>
        </div>
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
          <div className="text-2xl font-bold text-purple-400">{approvals.filter(a => a.type === 'user_action').length}</div>
          <div className="text-slate-400 text-sm">User Actions</div>
        </div>
      </div>

      {/* Approvals List */}
      <div className="space-y-4">
        {approvals.map(approval => (
          <div key={approval.id} className="bg-slate-800 rounded-xl p-6 border border-slate-700">
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
                  <p className="text-slate-400 text-sm mb-2">{approval.description}</p>
                  
                  {approval.type === 'transfer' && approval.amount && (
                    <div className="bg-slate-700/50 rounded-lg p-3 mb-3 inline-block">
                      <span className="text-2xl font-bold">{approval.amount}</span>
                      <span className="text-slate-400 ml-2">{approval.token}</span>
                      <div className="text-sm text-slate-400 mt-1">
                        {approval.from} → {approval.to}
                      </div>
                    </div>
                  )}
                  
                  <div className="text-xs text-slate-500">
                    Requested by {approval.requestedBy} • {approval.timestamp}
                  </div>
                </div>
              </div>
              
              <div className="text-right">
                <div className="mb-3">
                  <div className="text-sm text-slate-400 mb-1">Approvals</div>
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
              <div className="mt-4 pt-4 border-t border-slate-700">
                <div className="text-sm text-slate-400 mb-2">Approval History</div>
                <div className="flex flex-wrap gap-2">
                  {approval.approvals.map((a, i) => (
                    <div key={i} className="bg-green-500/10 border border-green-500/30 rounded-lg px-3 py-1 text-sm">
                      <span className="text-green-400">✓</span> {a.user}
                      <span className="text-slate-500 ml-2 text-xs">{a.timestamp}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
