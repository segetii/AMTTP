'use client';

/**
 * Transaction Flow Page
 * 
 * War Room transaction monitoring
 * RBAC: R4+ required (Institution, Regulator, Admin)
 */

import React, { useState } from 'react';
import { 
  ArrowPathIcon,
  FunnelIcon,
  MagnifyingGlassIcon,
  ArrowTrendingUpIcon,
  ArrowTrendingDownIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';

// ═══════════════════════════════════════════════════════════════════════════════
// MOCK DATA
// ═══════════════════════════════════════════════════════════════════════════════



// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function TransactionsPage() {
  const [transactions, setTransactions] = useState<any[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  React.useEffect(() => {
    fetch('http://127.0.0.1:8007/decisions')
      .then(r => { if (!r.ok) throw new Error(`API error: ${r.status} ${r.statusText}`); return r.json(); })
      .then(data => setTransactions(Array.isArray(data) ? data : []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const filteredTransactions = transactions.filter(tx => {
    const matchesSearch = 
      tx.hash?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      tx.from?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      tx.to?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === 'all' || tx.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const handleRefresh = () => {
    setIsLoading(true);
    setTimeout(() => setIsLoading(false), 1000);
  };

  const getRiskColor = (score: number) => {
    if (score < 0.3) return 'text-green-400';
    if (score < 0.6) return 'text-yellow-400';
    return 'text-red-400';
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return <span className="px-2 py-1 rounded-full text-xs bg-green-900/50 text-green-400 border border-green-700">Completed</span>;
      case 'pending':
        return <span className="px-2 py-1 rounded-full text-xs bg-yellow-900/50 text-yellow-400 border border-yellow-700">Pending</span>;
      case 'flagged':
        return <span className="px-2 py-1 rounded-full text-xs bg-red-900/50 text-red-400 border border-red-700">Flagged</span>;
      default:
        return <span className="px-2 py-1 rounded-full text-xs bg-slate-700 text-mutedText">{status}</span>;
    }
  };

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="space-y-6">
      {error && <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 mb-4 text-red-400 text-sm">⚠ Backend unavailable: {error}</div>}
      {loading && <div className="text-zinc-500 text-sm mb-4">Loading from backend...</div>}
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text">Transaction Flow</h1>
          <p className="text-mutedText mt-1">Monitor real-time transaction activity</p>
        </div>
        <button 
          onClick={handleRefresh}
          disabled={isLoading}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg flex items-center gap-2 transition-colors disabled:opacity-50"
        >
          <ArrowPathIcon className={`w-5 h-5 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-surface rounded-lg p-4 border border-borderSubtle">
          <div className="flex items-center justify-between">
            <span className="text-mutedText text-sm">Total Volume (24h)</span>
            <ArrowTrendingUpIcon className="w-5 h-5 text-green-400" />
          </div>
          <p className="text-2xl font-bold text-text mt-2">$2.4M</p>
          <p className="text-green-400 text-sm mt-1">+12.5% from yesterday</p>
        </div>
        <div className="bg-surface rounded-lg p-4 border border-borderSubtle">
          <div className="flex items-center justify-between">
            <span className="text-mutedText text-sm">Transactions</span>
            <ArrowTrendingUpIcon className="w-5 h-5 text-green-400" />
          </div>
          <p className="text-2xl font-bold text-text mt-2">1,247</p>
          <p className="text-green-400 text-sm mt-1">+8.3% from yesterday</p>
        </div>
        <div className="bg-surface rounded-lg p-4 border border-borderSubtle">
          <div className="flex items-center justify-between">
            <span className="text-mutedText text-sm">Flagged</span>
            <ExclamationTriangleIcon className="w-5 h-5 text-red-400" />
          </div>
          <p className="text-2xl font-bold text-text mt-2">23</p>
          <p className="text-red-400 text-sm mt-1">+3 new alerts</p>
        </div>
        <div className="bg-surface rounded-lg p-4 border border-borderSubtle">
          <div className="flex items-center justify-between">
            <span className="text-mutedText text-sm">Avg Risk Score</span>
            <ArrowTrendingDownIcon className="w-5 h-5 text-green-400" />
          </div>
          <p className="text-2xl font-bold text-text mt-2">0.24</p>
          <p className="text-green-400 text-sm mt-1">-0.05 from yesterday</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-4 items-center">
        <div className="relative flex-1 max-w-md">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-mutedText" />
          <input
            type="text"
            placeholder="Search by hash, from, or to address..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-surface border border-borderSubtle rounded-lg text-text placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
        </div>
        <div className="flex items-center gap-2">
          <FunnelIcon className="w-5 h-5 text-mutedText" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-surface border border-borderSubtle rounded-lg px-3 py-2 text-text focus:outline-none focus:border-blue-500"
          >
            <option value="all">All Status</option>
            <option value="completed">Completed</option>
            <option value="pending">Pending</option>
            <option value="flagged">Flagged</option>
          </select>
        </div>
      </div>

      {/* Transactions Table */}
      <div className="bg-surface rounded-lg border border-borderSubtle overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-borderSubtle bg-background/50">
                <th className="text-left py-3 px-4 text-mutedText font-medium text-sm">Time</th>
                <th className="text-left py-3 px-4 text-mutedText font-medium text-sm">Hash</th>
                <th className="text-left py-3 px-4 text-mutedText font-medium text-sm">From</th>
                <th className="text-left py-3 px-4 text-mutedText font-medium text-sm">To</th>
                <th className="text-right py-3 px-4 text-mutedText font-medium text-sm">Amount</th>
                <th className="text-center py-3 px-4 text-mutedText font-medium text-sm">Risk</th>
                <th className="text-center py-3 px-4 text-mutedText font-medium text-sm">Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredTransactions.map((tx) => (
                <tr key={tx.id} className="border-b border-borderSubtle/50 hover:bg-slate-700/30 transition-colors">
                  <td className="py-3 px-4 text-slate-300 text-sm">{formatTime(tx.timestamp)}</td>
                  <td className="py-3 px-4">
                    <code className="text-blue-400 text-sm font-mono">
                      {tx.hash.slice(0, 10)}...{tx.hash.slice(-8)}
                    </code>
                  </td>
                  <td className="py-3 px-4">
                    <code className="text-slate-300 text-sm font-mono">
                      {tx.from.slice(0, 6)}...{tx.from.slice(-4)}
                    </code>
                  </td>
                  <td className="py-3 px-4">
                    <code className="text-slate-300 text-sm font-mono">
                      {tx.to.slice(0, 6)}...{tx.to.slice(-4)}
                    </code>
                  </td>
                  <td className="py-3 px-4 text-right">
                    <span className="text-text font-medium">{tx.amount}</span>
                    <span className="text-mutedText ml-1">{tx.token}</span>
                  </td>
                  <td className="py-3 px-4 text-center">
                    <span className={`font-mono ${getRiskColor(tx.riskScore)}`}>
                      {tx.riskScore.toFixed(2)}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-center">
                    {getStatusBadge(tx.status)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        
        {filteredTransactions.length === 0 && (
          <div className="text-center py-12 text-mutedText">
            No transactions found matching your filters
          </div>
        )}
      </div>
    </div>
  );
}
