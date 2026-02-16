'use client';

import { useState } from 'react';
import React from 'react';
import Link from 'next/link';

interface FlaggedTransaction {
  id: string;
  txHash: string;
  from: string;
  to: string;
  amount: string;
  token: string;
  riskScore: number;
  riskLevel: 'low' | 'medium' | 'high' | 'critical';
  flagReason: string;
  timestamp: string;
  status: 'pending' | 'approved' | 'rejected' | 'escalated';
}

const mockFlaggedTxs: FlaggedTransaction[] = []; // Removed mock data

export default function FlaggedQueuePage() {
  const [transactions, setTransactions] = useState<FlaggedTransaction[]>([]);
  const [selectedTx, setSelectedTx] = useState<FlaggedTransaction | null>(null);
  const [filter, setFilter] = useState<'all' | 'pending' | 'approved' | 'rejected' | 'escalated'>('pending');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  React.useEffect(() => {
    fetch('http://127.0.0.1:8007/dashboard/alerts')
      .then(r => { if (!r.ok) throw new Error(`API error: ${r.status} ${r.statusText}`); return r.json(); })
      .then(data => setTransactions(Array.isArray(data) ? data : []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const filteredTxs = filter === 'all' 
    ? transactions 
    : transactions.filter(tx => tx.status === filter);

  const handleAction = (txId: string, action: 'approve' | 'reject' | 'escalate') => {
    setTransactions(prev => prev.map(tx => 
      tx.id === txId 
        ? { ...tx, status: action === 'approve' ? 'approved' : action === 'reject' ? 'rejected' : 'escalated' }
        : tx
    ));
    setSelectedTx(null);
  };

  const getRiskColor = (level: string) => {
    switch (level) {
      case 'critical': return 'bg-red-500/20 text-red-400 border-red-500/50';
      case 'high': return 'bg-orange-500/20 text-orange-400 border-orange-500/50';
      case 'medium': return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50';
      default: return 'bg-green-500/20 text-green-400 border-green-500/50';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'approved': return 'bg-green-500/20 text-green-400';
      const getStatusColor = (status: string) => {
        switch (status) {
          case 'approved': return 'bg-green-500/20 text-green-400';
          case 'rejected': return 'bg-red-500/20 text-red-400';
          case 'escalated': return 'bg-purple-500/20 text-purple-400';
          default: return 'bg-yellow-500/20 text-yellow-400';
        }
      };

      case 'rejected': return 'bg-red-500/20 text-red-400';
      case 'escalated': return 'bg-purple-500/20 text-purple-400';
      default: return 'bg-yellow-500/20 text-yellow-400';
    }
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
          <h1 className="text-3xl font-bold">Flagged Queue</h1>
          <p className="text-mutedText mt-1">Review and action flagged transactions</p>
        </div>
        <div className="flex items-center gap-4">
          <span className="px-3 py-1 bg-red-500/20 text-red-400 rounded-full text-sm">
            {transactions.filter(t => t.status === 'pending').length} Pending Review
          </span>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-2 mb-6">
        {(['all', 'pending', 'approved', 'rejected', 'escalated'] as const).map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-4 py-2 rounded-lg capitalize transition-colors ${
              filter === f 
                ? 'bg-indigo-600 text-text' 
                : 'bg-surface text-mutedText hover:bg-slate-700'
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {/* Transaction Table */}
      <div className="bg-surface rounded-xl border border-borderSubtle overflow-hidden">
        <table className="w-full">
          <thead className="bg-slate-700/50">
            <tr>
              <th className="text-left p-4 text-mutedText font-medium">Transaction</th>
              <th className="text-left p-4 text-mutedText font-medium">From → To</th>
              <th className="text-left p-4 text-mutedText font-medium">Amount</th>
              <th className="text-left p-4 text-mutedText font-medium">Risk</th>
              <th className="text-left p-4 text-mutedText font-medium">Reason</th>
              <th className="text-left p-4 text-mutedText font-medium">Status</th>
              <th className="text-left p-4 text-mutedText font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredTxs.map(tx => (
              <tr 
                key={tx.id} 
                className="border-t border-borderSubtle hover:bg-slate-700/30 cursor-pointer"
                onClick={() => setSelectedTx(tx)}
              >
                <td className="p-4">
                  <div className="font-mono text-sm">{tx.txHash}</div>
                  <div className="text-xs text-mutedText">{tx.timestamp}</div>
                </td>
                <td className="p-4">
                  <div className="text-sm">{tx.from}</div>
                  <div className="text-xs text-mutedText">→ {tx.to}</div>
                </td>
                <td className="p-4">
                  <div className="font-semibold">{tx.amount}</div>
                  <div className="text-xs text-mutedText">{tx.token}</div>
                </td>
                <td className="p-4">
                  <span className={`px-2 py-1 rounded border text-xs font-medium ${getRiskColor(tx.riskLevel)}`}>
                    {tx.riskScore}% {tx.riskLevel}
                  </span>
                </td>
                <td className="p-4 max-w-xs">
                  <div className="text-sm text-slate-300 truncate">{tx.flagReason}</div>
                </td>
                <td className="p-4">
                  <span className={`px-2 py-1 rounded text-xs font-medium capitalize ${getStatusColor(tx.status)}`}>
                    {tx.status}
                  </span>
                </td>
                <td className="p-4">
                  {tx.status === 'pending' && (
                    <div className="flex gap-2" onClick={e => e.stopPropagation()}>
                      <button 
                        onClick={() => handleAction(tx.id, 'approve')}
                        className="px-3 py-1 bg-green-600 hover:bg-green-700 rounded text-sm"
                      >
                        Approve
                      </button>
                      <button 
                        onClick={() => handleAction(tx.id, 'reject')}
                        className="px-3 py-1 bg-red-600 hover:bg-red-700 rounded text-sm"
                      >
                        Reject
                      </button>
                      <button 
                        onClick={() => handleAction(tx.id, 'escalate')}
                        className="px-3 py-1 bg-purple-600 hover:bg-purple-700 rounded text-sm"
                      >
                        Escalate
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Detail Modal */}
      {selectedTx && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setSelectedTx(null)}>
          <div className="bg-surface rounded-xl p-6 max-w-2xl w-full mx-4 border border-borderSubtle" onClick={e => e.stopPropagation()}>
            <h2 className="text-xl font-bold mb-4">Transaction Details</h2>
            <div className="grid grid-cols-2 gap-4 mb-6">
              <div>
                <div className="text-mutedText text-sm">Transaction Hash</div>
                <div className="font-mono">{selectedTx.txHash}</div>
              </div>
              <div>
                <div className="text-mutedText text-sm">Risk Score</div>
                <span className={`px-2 py-1 rounded border text-sm font-medium ${getRiskColor(selectedTx.riskLevel)}`}>
                  {selectedTx.riskScore}% {selectedTx.riskLevel}
                </span>
              </div>
              <div>
                <div className="text-mutedText text-sm">From</div>
                <div className="font-mono text-sm">{selectedTx.from}</div>
              </div>
              <div>
                <div className="text-mutedText text-sm">To</div>
                <div className="font-mono text-sm">{selectedTx.to}</div>
              </div>
              <div>
                <div className="text-mutedText text-sm">Amount</div>
                <div>{selectedTx.amount} {selectedTx.token}</div>
              </div>
              <div>
                <div className="text-mutedText text-sm">Timestamp</div>
                <div>{selectedTx.timestamp}</div>
              </div>
            </div>
            <div className="mb-6">
              <div className="text-mutedText text-sm mb-1">Flag Reason</div>
              <div className="bg-slate-700/50 p-3 rounded">{selectedTx.flagReason}</div>
            </div>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setSelectedTx(null)} className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg">
                Close
              </button>
              {selectedTx.status === 'pending' && (
                <>
                  <button 
                    onClick={() => handleAction(selectedTx.id, 'approve')}
                    className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded-lg"
                  >
                    Approve
                  </button>
                  <button 
                    onClick={() => handleAction(selectedTx.id, 'reject')}
                    className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg"
                  >
                    Reject
                  </button>
          {error && <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 mb-4 text-red-400 text-sm">⚠ Backend unavailable: {error}</div>}
          {loading && <div className="text-zinc-500 text-sm mb-4">Loading from backend...</div>}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
