'use client';

import { useState } from 'react';
import Link from 'next/link';

interface Policy {
  id: string;
  name: string;
  description: string;
  type: 'transaction' | 'risk' | 'velocity' | 'compliance';
  status: 'active' | 'inactive' | 'draft';
  conditions: string[];
  actions: string[];
  lastModified: string;
  createdBy: string;
}

const mockPolicies: Policy[] = [
  {
    id: '1',
    name: 'High Value Transfer Review',
    description: 'Requires manual review for transfers exceeding $10,000',
    type: 'transaction',
    status: 'active',
    conditions: ['amount > 10000', 'token in [USDC, USDT, ETH]'],
    actions: ['Flag for review', 'Notify compliance team'],
    lastModified: '2026-01-30',
    createdBy: 'admin@exchange.com',
  },
  {
    id: '2',
    name: 'Velocity Limit - Daily',
    description: 'Limits daily transfer volume per user',
    type: 'velocity',
    status: 'active',
    conditions: ['daily_volume > 50000', 'user_tier != premium'],
    actions: ['Block transaction', 'Alert user', 'Log event'],
    lastModified: '2026-01-28',
    createdBy: 'compliance@exchange.com',
  },
  {
    id: '3',
    name: 'Sanctions Screening',
    description: 'Screen counterparties against OFAC and EU sanctions lists',
    type: 'compliance',
    status: 'active',
    conditions: ['counterparty_address exists'],
    actions: ['Check OFAC list', 'Check EU sanctions', 'Block if match'],
    lastModified: '2026-01-25',
    createdBy: 'compliance@exchange.com',
  },
  {
    id: '4',
    name: 'ML Risk Threshold',
    description: 'Route high-risk transactions to escrow',
    type: 'risk',
    status: 'active',
    conditions: ['ml_risk_score > 75'],
    actions: ['Escrow funds', 'Create dispute case', 'Notify parties'],
    lastModified: '2026-01-20',
    createdBy: 'admin@exchange.com',
  },
];

export default function PolicyEnginePage() {
  const [policies, setPolicies] = useState(mockPolicies);
  const [selectedPolicy, setSelectedPolicy] = useState<Policy | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'transaction': return 'bg-blue-500/20 text-blue-400';
      case 'risk': return 'bg-red-500/20 text-red-400';
      case 'velocity': return 'bg-yellow-500/20 text-yellow-400';
      case 'compliance': return 'bg-purple-500/20 text-purple-400';
      default: return 'bg-slate-500/20 text-slate-400';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'bg-green-500/20 text-green-400';
      case 'inactive': return 'bg-slate-500/20 text-slate-400';
      case 'draft': return 'bg-yellow-500/20 text-yellow-400';
      default: return 'bg-slate-500/20 text-slate-400';
    }
  };

  const toggleStatus = (id: string) => {
    setPolicies(prev => prev.map(p => 
      p.id === id 
        ? { ...p, status: p.status === 'active' ? 'inactive' : 'active' }
        : p
    ));
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
          <h1 className="text-3xl font-bold">Policy Engine</h1>
          <p className="text-slate-400 mt-1">Configure transaction policies, risk rules, and compliance controls</p>
        </div>
        <button 
          onClick={() => setIsCreating(true)}
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg flex items-center gap-2"
        >
          <span>+ New Policy</span>
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
          <div className="text-2xl font-bold text-green-400">{policies.filter(p => p.status === 'active').length}</div>
          <div className="text-slate-400 text-sm">Active Policies</div>
        </div>
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
          <div className="text-2xl font-bold text-blue-400">{policies.filter(p => p.type === 'transaction').length}</div>
          <div className="text-slate-400 text-sm">Transaction Rules</div>
        </div>
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
          <div className="text-2xl font-bold text-red-400">{policies.filter(p => p.type === 'risk').length}</div>
          <div className="text-slate-400 text-sm">Risk Policies</div>
        </div>
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
          <div className="text-2xl font-bold text-purple-400">{policies.filter(p => p.type === 'compliance').length}</div>
          <div className="text-slate-400 text-sm">Compliance Rules</div>
        </div>
      </div>

      {/* Policy List */}
      <div className="space-y-4">
        {policies.map(policy => (
          <div 
            key={policy.id}
            className="bg-slate-800 rounded-xl p-6 border border-slate-700 hover:border-slate-600 cursor-pointer transition-colors"
            onClick={() => setSelectedPolicy(policy)}
          >
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-2">
                  <h3 className="text-lg font-semibold">{policy.name}</h3>
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${getTypeColor(policy.type)}`}>
                    {policy.type}
                  </span>
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${getStatusColor(policy.status)}`}>
                    {policy.status}
                  </span>
                </div>
                <p className="text-slate-400 text-sm mb-3">{policy.description}</p>
                <div className="flex gap-6 text-sm">
                  <div>
                    <span className="text-slate-500">Conditions:</span>{' '}
                    <span className="text-slate-300">{policy.conditions.length} rules</span>
                  </div>
                  <div>
                    <span className="text-slate-500">Actions:</span>{' '}
                    <span className="text-slate-300">{policy.actions.length} actions</span>
                  </div>
                  <div>
                    <span className="text-slate-500">Modified:</span>{' '}
                    <span className="text-slate-300">{policy.lastModified}</span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
                <button
                  onClick={() => toggleStatus(policy.id)}
                  className={`px-3 py-1 rounded text-sm ${
                    policy.status === 'active' 
                      ? 'bg-red-600/20 text-red-400 hover:bg-red-600/30' 
                      : 'bg-green-600/20 text-green-400 hover:bg-green-600/30'
                  }`}
                >
                  {policy.status === 'active' ? 'Disable' : 'Enable'}
                </button>
                <button className="px-3 py-1 bg-slate-700 hover:bg-slate-600 rounded text-sm">
                  Edit
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Policy Detail Modal */}
      {selectedPolicy && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setSelectedPolicy(null)}>
          <div className="bg-slate-800 rounded-xl p-6 max-w-3xl w-full mx-4 border border-slate-700 max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-bold">{selectedPolicy.name}</h2>
              <div className="flex gap-2">
                <span className={`px-2 py-1 rounded text-xs font-medium ${getTypeColor(selectedPolicy.type)}`}>
                  {selectedPolicy.type}
                </span>
                <span className={`px-2 py-1 rounded text-xs font-medium ${getStatusColor(selectedPolicy.status)}`}>
                  {selectedPolicy.status}
                </span>
              </div>
            </div>
            
            <p className="text-slate-400 mb-6">{selectedPolicy.description}</p>
            
            <div className="mb-6">
              <h3 className="text-sm font-medium text-slate-400 mb-2">Conditions</h3>
              <div className="bg-slate-700/50 rounded-lg p-4 space-y-2">
                {selectedPolicy.conditions.map((c, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <span className="text-indigo-400">IF</span>
                    <code className="bg-slate-900 px-2 py-1 rounded text-sm">{c}</code>
                  </div>
                ))}
              </div>
            </div>
            
            <div className="mb-6">
              <h3 className="text-sm font-medium text-slate-400 mb-2">Actions</h3>
              <div className="bg-slate-700/50 rounded-lg p-4 space-y-2">
                {selectedPolicy.actions.map((a, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <span className="text-green-400">THEN</span>
                    <span className="text-slate-300">{a}</span>
                  </div>
                ))}
              </div>
            </div>
            
            <div className="flex justify-between text-sm text-slate-500 mb-6">
              <span>Created by: {selectedPolicy.createdBy}</span>
              <span>Last modified: {selectedPolicy.lastModified}</span>
            </div>
            
            <div className="flex gap-3 justify-end">
              <button onClick={() => setSelectedPolicy(null)} className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg">
                Close
              </button>
              <button className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg">
                Edit Policy
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
