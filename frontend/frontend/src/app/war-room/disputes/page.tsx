'use client';

/**
 * War Room Disputes Page
 * 
 * Dispute management for institutional users
 * RBAC: R3+ required (Escrow, Institution, Regulator, Admin)
 */

import React, { useState } from 'react';
import Link from 'next/link';
import { 
  ArrowPathIcon,
  ScaleIcon,
  ClockIcon,
  CheckCircleIcon,
  XCircleIcon,
  ExclamationTriangleIcon,
  MagnifyingGlassIcon,
  FunnelIcon,
  ChatBubbleLeftRightIcon,
} from '@heroicons/react/24/outline';

// ═══════════════════════════════════════════════════════════════════════════════
// MOCK DATA
// ═══════════════════════════════════════════════════════════════════════════════

interface Dispute {
  id: string;
  transactionId: string;
  claimant: string;
  respondent: string;
  amount: string;
  token: string;
  status: 'pending' | 'evidence' | 'voting' | 'resolved' | 'escalated';
  reason: string;
  createdAt: string;
  deadline: string;
  votes?: { for: number; against: number };
  resolution?: 'claimant' | 'respondent';
}

const mockDisputes: Dispute[] = [
  {
    id: 'dispute_001',
    transactionId: '0x1a2b3c4d5e6f7890',
    claimant: '0x742d35Cc6634C0532925a3b844Bc9e7595f8c2E4',
    respondent: '0x8Ba1f109551bD432803012645Ac136ddd64DBA72',
    amount: '5,000.00',
    token: 'USDC',
    status: 'evidence',
    reason: 'Services not delivered as agreed',
    createdAt: '2026-01-20T10:30:00Z',
    deadline: '2026-01-27T10:30:00Z',
  },
  {
    id: 'dispute_002',
    transactionId: '0x2b3c4d5e6f789012',
    claimant: '0x9Cd2f109551bD432803012645Ac136ddd64DBA73',
    respondent: '0x742d35Cc6634C0532925a3b844Bc9e7595f8c2E4',
    amount: '12,500.00',
    token: 'USDT',
    status: 'voting',
    reason: 'Fraudulent transfer claim',
    createdAt: '2026-01-18T14:20:00Z',
    deadline: '2026-01-25T14:20:00Z',
    votes: { for: 67, against: 33 },
  },
  {
    id: 'dispute_003',
    transactionId: '0x3c4d5e6f78901234',
    claimant: '0xABc2f109551bD432803012645Ac136ddd64DBA74',
    respondent: '0xDEf35Cc6634C0532925a3b844Bc9e7595f8c2E5',
    amount: '50,000.00',
    token: 'DAI',
    status: 'escalated',
    reason: 'Disputed terms interpretation',
    createdAt: '2026-01-15T08:00:00Z',
    deadline: '2026-02-01T08:00:00Z',
  },
  {
    id: 'dispute_004',
    transactionId: '0x4d5e6f7890123456',
    claimant: '0xFEd35Cc6634C0532925a3b844Bc9e7595f8c2E6',
    respondent: '0x123d35Cc6634C0532925a3b844Bc9e7595f8c2E7',
    amount: '2,000.00',
    token: 'USDC',
    status: 'resolved',
    reason: 'Payment timing dispute',
    createdAt: '2026-01-10T12:00:00Z',
    deadline: '2026-01-17T12:00:00Z',
    resolution: 'claimant',
  },
  {
    id: 'dispute_005',
    transactionId: '0x5e6f789012345678',
    claimant: '0x456d35Cc6634C0532925a3b844Bc9e7595f8c2E8',
    respondent: '0x789d35Cc6634C0532925a3b844Bc9e7595f8c2E9',
    amount: '8,750.00',
    token: 'USDT',
    status: 'pending',
    reason: 'Unauthorized transaction',
    createdAt: '2026-01-22T09:00:00Z',
    deadline: '2026-01-29T09:00:00Z',
  },
];

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function DisputesPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [isLoading, setIsLoading] = useState(false);

  const handleRefresh = () => {
    setIsLoading(true);
    setTimeout(() => setIsLoading(false), 1000);
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'pending':
        return (
          <span className="flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-slate-700 text-slate-300">
            <ClockIcon className="w-3 h-3" />
            Pending
          </span>
        );
      case 'evidence':
        return (
          <span className="flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-blue-900/50 text-blue-400 border border-blue-700">
            <ChatBubbleLeftRightIcon className="w-3 h-3" />
            Evidence
          </span>
        );
      case 'voting':
        return (
          <span className="flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-purple-900/50 text-purple-400 border border-purple-700">
            <ScaleIcon className="w-3 h-3" />
            Voting
          </span>
        );
      case 'escalated':
        return (
          <span className="flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-orange-900/50 text-orange-400 border border-orange-700">
            <ExclamationTriangleIcon className="w-3 h-3" />
            Escalated
          </span>
        );
      case 'resolved':
        return (
          <span className="flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-green-900/50 text-green-400 border border-green-700">
            <CheckCircleIcon className="w-3 h-3" />
            Resolved
          </span>
        );
      default:
        return null;
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const getDaysRemaining = (deadline: string) => {
    const days = Math.ceil((new Date(deadline).getTime() - Date.now()) / (1000 * 60 * 60 * 24));
    if (days < 0) return 'Expired';
    if (days === 0) return 'Today';
    if (days === 1) return '1 day';
    return `${days} days`;
  };

  const filteredDisputes = mockDisputes.filter(d => {
    const matchesSearch = 
      d.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      d.claimant.toLowerCase().includes(searchQuery.toLowerCase()) ||
      d.respondent.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === 'all' || d.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const activeDisputes = mockDisputes.filter(d => d.status !== 'resolved').length;
  const totalValue = mockDisputes.reduce((sum, d) => sum + parseFloat(d.amount.replace(',', '')), 0);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Disputes</h1>
          <p className="text-slate-400 mt-1">Manage and resolve transaction disputes</p>
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

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center gap-2 text-slate-400 text-sm">
            <ScaleIcon className="w-4 h-4" />
            <span>Total Disputes</span>
          </div>
          <p className="text-2xl font-bold text-white mt-2">{mockDisputes.length}</p>
        </div>
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center gap-2 text-slate-400 text-sm">
            <ClockIcon className="w-4 h-4 text-yellow-400" />
            <span>Active</span>
          </div>
          <p className="text-2xl font-bold text-yellow-400 mt-2">{activeDisputes}</p>
        </div>
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center gap-2 text-slate-400 text-sm">
            <CheckCircleIcon className="w-4 h-4 text-green-400" />
            <span>Resolved</span>
          </div>
          <p className="text-2xl font-bold text-green-400 mt-2">
            {mockDisputes.filter(d => d.status === 'resolved').length}
          </p>
        </div>
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center gap-2 text-slate-400 text-sm">
            <span>Total Value</span>
          </div>
          <p className="text-2xl font-bold text-white mt-2">${totalValue.toLocaleString()}</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-4 items-center">
        <div className="relative flex-1 max-w-md">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
          <input
            type="text"
            placeholder="Search by ID or address..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
        </div>
        <div className="flex items-center gap-2">
          <FunnelIcon className="w-5 h-5 text-slate-400" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
          >
            <option value="all">All Status</option>
            <option value="pending">Pending</option>
            <option value="evidence">Evidence</option>
            <option value="voting">Voting</option>
            <option value="escalated">Escalated</option>
            <option value="resolved">Resolved</option>
          </select>
        </div>
      </div>

      {/* Disputes List */}
      <div className="space-y-4">
        {filteredDisputes.map((dispute) => (
          <div 
            key={dispute.id}
            className="bg-slate-800 rounded-lg border border-slate-700 p-4 hover:border-slate-600 transition-colors"
          >
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-3">
                  <span className="text-white font-semibold">{dispute.id}</span>
                  {getStatusBadge(dispute.status)}
                </div>
                <p className="text-slate-400 text-sm mt-2">{dispute.reason}</p>
              </div>
              <div className="text-right">
                <p className="text-xl font-bold text-white">{dispute.amount} {dispute.token}</p>
                <p className="text-slate-500 text-xs mt-1">
                  Deadline: {getDaysRemaining(dispute.deadline)}
                </p>
              </div>
            </div>

            {/* Parties */}
            <div className="grid grid-cols-2 gap-4 mt-4 pt-4 border-t border-slate-700">
              <div>
                <p className="text-slate-500 text-xs uppercase mb-1">Claimant</p>
                <code className="text-blue-400 text-sm font-mono">
                  {dispute.claimant.slice(0, 10)}...{dispute.claimant.slice(-8)}
                </code>
              </div>
              <div>
                <p className="text-slate-500 text-xs uppercase mb-1">Respondent</p>
                <code className="text-slate-300 text-sm font-mono">
                  {dispute.respondent.slice(0, 10)}...{dispute.respondent.slice(-8)}
                </code>
              </div>
            </div>

            {/* Voting Progress */}
            {dispute.status === 'voting' && dispute.votes && (
              <div className="mt-4 pt-4 border-t border-slate-700">
                <p className="text-slate-500 text-xs uppercase mb-2">Voting Progress</p>
                <div className="flex items-center gap-4">
                  <div className="flex-1 bg-slate-700 rounded-full h-3 overflow-hidden">
                    <div 
                      className="bg-green-500 h-full"
                      style={{ width: `${dispute.votes.for}%` }}
                    />
                  </div>
                  <span className="text-green-400 text-sm">{dispute.votes.for}%</span>
                  <span className="text-slate-500">vs</span>
                  <span className="text-red-400 text-sm">{dispute.votes.against}%</span>
                </div>
              </div>
            )}

            {/* Resolution */}
            {dispute.status === 'resolved' && dispute.resolution && (
              <div className="mt-4 pt-4 border-t border-slate-700">
                <div className="flex items-center gap-2">
                  <CheckCircleIcon className="w-5 h-5 text-green-400" />
                  <span className="text-green-400">
                    Resolved in favor of {dispute.resolution === 'claimant' ? 'Claimant' : 'Respondent'}
                  </span>
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-2 mt-4 pt-4 border-t border-slate-700">
              <Link 
                href={`/disputes/${dispute.id}`}
                className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded text-sm"
              >
                View Details
              </Link>
              {dispute.status === 'evidence' && (
                <button className="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 rounded text-sm">
                  Submit Evidence
                </button>
              )}
              {dispute.status === 'voting' && (
                <button className="px-3 py-1.5 bg-purple-600 hover:bg-purple-700 rounded text-sm">
                  Cast Vote
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {filteredDisputes.length === 0 && (
        <div className="text-center py-12 text-slate-500">
          No disputes found matching your filters
        </div>
      )}
    </div>
  );
}
