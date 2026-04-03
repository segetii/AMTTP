'use client';

/**
 * Dispute Detail Page
 * 
 * View and interact with a specific dispute
 * Features:
 * - Full dispute details
 * - Evidence submission
 * - Voting (for eligible voters)
 * - Timeline of events
 */

import React, { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeftIcon,
  ScaleIcon,
  ClockIcon,
  CheckCircleIcon,
  XCircleIcon,
  ExclamationTriangleIcon,
  ChatBubbleLeftRightIcon,
  DocumentTextIcon,
  UserIcon,
  CalendarIcon,
  ArrowPathIcon,
} from '@heroicons/react/24/outline';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
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
  description: string;
  createdAt: string;
  deadline: string;
  votes?: { for: number; against: number; total: number };
  resolution?: 'claimant' | 'respondent';
  evidence: Evidence[];
  timeline: TimelineEvent[];
}

interface Evidence {
  id: string;
  submittedBy: 'claimant' | 'respondent';
  type: 'document' | 'screenshot' | 'transaction' | 'communication';
  title: string;
  description: string;
  timestamp: string;
  hash: string;
}

interface TimelineEvent {
  id: string;
  type: 'filed' | 'evidence' | 'voting_started' | 'vote_cast' | 'escalated' | 'resolved';
  description: string;
  timestamp: string;
  actor?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// MOCK DATA
// ═══════════════════════════════════════════════════════════════════════════════

const mockDisputes: Record<string, Dispute> = {
  'dispute_001': {
    id: 'dispute_001',
    transactionId: '0x1a2b3c4d5e6f7890',
    claimant: '0x742d35Cc6634C0532925a3b844Bc9e7595f8c2E4',
    respondent: '0x8Ba1f109551bD432803012645Ac136ddd64DBA72',
    amount: '5,000.00',
    token: 'USDC',
    status: 'evidence',
    reason: 'Services not delivered as agreed',
    description: 'The respondent was contracted to deliver consulting services over a 30-day period. Payment was made upfront as agreed. However, after 30 days, no deliverables were received and the respondent became unresponsive to communication attempts.',
    createdAt: '2026-01-20T10:30:00Z',
    deadline: '2026-01-27T10:30:00Z',
    evidence: [
      {
        id: 'ev_001',
        submittedBy: 'claimant',
        type: 'document',
        title: 'Original Contract Agreement',
        description: 'Signed contract outlining deliverables and timeline',
        timestamp: '2026-01-20T11:00:00Z',
        hash: '0xabc123...',
      },
      {
        id: 'ev_002',
        submittedBy: 'claimant',
        type: 'communication',
        title: 'Email Thread Screenshots',
        description: 'Evidence of unanswered follow-up emails',
        timestamp: '2026-01-21T09:30:00Z',
        hash: '0xdef456...',
      },
    ],
    timeline: [
      { id: 't1', type: 'filed', description: 'Dispute filed by claimant', timestamp: '2026-01-20T10:30:00Z', actor: '0x742d...c2E4' },
      { id: 't2', type: 'evidence', description: 'Contract document submitted', timestamp: '2026-01-20T11:00:00Z', actor: '0x742d...c2E4' },
      { id: 't3', type: 'evidence', description: 'Email evidence submitted', timestamp: '2026-01-21T09:30:00Z', actor: '0x742d...c2E4' },
    ],
  },
  'dispute_002': {
    id: 'dispute_002',
    transactionId: '0x2b3c4d5e6f789012',
    claimant: '0x9Cd2f109551bD432803012645Ac136ddd64DBA73',
    respondent: '0x742d35Cc6634C0532925a3b844Bc9e7595f8c2E4',
    amount: '12,500.00',
    token: 'USDT',
    status: 'voting',
    reason: 'Fraudulent transfer claim',
    description: 'Claimant alleges that the transfer was initiated without proper authorization. They claim their wallet was compromised and the transaction should be reversed.',
    createdAt: '2026-01-18T14:20:00Z',
    deadline: '2026-01-25T14:20:00Z',
    votes: { for: 67, against: 33, total: 15 },
    evidence: [
      {
        id: 'ev_003',
        submittedBy: 'claimant',
        type: 'screenshot',
        title: 'Security Alert Notification',
        description: 'Screenshot of suspicious login alert from wallet provider',
        timestamp: '2026-01-18T15:00:00Z',
        hash: '0xghi789...',
      },
      {
        id: 'ev_004',
        submittedBy: 'respondent',
        type: 'transaction',
        title: 'Transaction Authorization Log',
        description: 'On-chain proof of multi-sig approval',
        timestamp: '2026-01-19T10:00:00Z',
        hash: '0xjkl012...',
      },
    ],
    timeline: [
      { id: 't1', type: 'filed', description: 'Dispute filed by claimant', timestamp: '2026-01-18T14:20:00Z', actor: '0x9Cd2...BA73' },
      { id: 't2', type: 'evidence', description: 'Security alert submitted', timestamp: '2026-01-18T15:00:00Z', actor: '0x9Cd2...BA73' },
      { id: 't3', type: 'evidence', description: 'Authorization log submitted', timestamp: '2026-01-19T10:00:00Z', actor: '0x742d...c2E4' },
      { id: 't4', type: 'voting_started', description: 'Voting period opened', timestamp: '2026-01-20T00:00:00Z' },
      { id: 't5', type: 'vote_cast', description: '8 votes cast for claimant', timestamp: '2026-01-21T12:00:00Z' },
      { id: 't6', type: 'vote_cast', description: '7 votes cast for respondent', timestamp: '2026-01-22T16:00:00Z' },
    ],
  },
  'dispute_003': {
    id: 'dispute_003',
    transactionId: '0x3c4d5e6f78901234',
    claimant: '0xABc2f109551bD432803012645Ac136ddd64DBA74',
    respondent: '0xDEf35Cc6634C0532925a3b844Bc9e7595f8c2E5',
    amount: '50,000.00',
    token: 'DAI',
    status: 'escalated',
    reason: 'Disputed terms interpretation',
    description: 'Both parties have different interpretations of the smart contract terms. The dispute has been escalated to Kleros decentralized court for final arbitration.',
    createdAt: '2026-01-15T08:00:00Z',
    deadline: '2026-02-01T08:00:00Z',
    evidence: [],
    timeline: [
      { id: 't1', type: 'filed', description: 'Dispute filed', timestamp: '2026-01-15T08:00:00Z' },
      { id: 't2', type: 'voting_started', description: 'Initial voting completed - inconclusive', timestamp: '2026-01-20T00:00:00Z' },
      { id: 't3', type: 'escalated', description: 'Escalated to Kleros Court', timestamp: '2026-01-22T10:00:00Z' },
    ],
  },
  'dispute_004': {
    id: 'dispute_004',
    transactionId: '0x4d5e6f7890123456',
    claimant: '0xFEd35Cc6634C0532925a3b844Bc9e7595f8c2E6',
    respondent: '0x123d35Cc6634C0532925a3b844Bc9e7595f8c2E7',
    amount: '2,000.00',
    token: 'USDC',
    status: 'resolved',
    reason: 'Payment timing dispute',
    description: 'Dispute regarding the timing of payment release from escrow. Claimant argued payment was due upon milestone completion, respondent argued it was time-based.',
    createdAt: '2026-01-10T12:00:00Z',
    deadline: '2026-01-17T12:00:00Z',
    resolution: 'claimant',
    evidence: [],
    timeline: [
      { id: 't1', type: 'filed', description: 'Dispute filed', timestamp: '2026-01-10T12:00:00Z' },
      { id: 't2', type: 'voting_started', description: 'Voting period opened', timestamp: '2026-01-12T00:00:00Z' },
      { id: 't3', type: 'resolved', description: 'Resolved in favor of claimant (72% votes)', timestamp: '2026-01-17T12:00:00Z' },
    ],
  },
  'dispute_005': {
    id: 'dispute_005',
    transactionId: '0x5e6f789012345678',
    claimant: '0x456d35Cc6634C0532925a3b844Bc9e7595f8c2E8',
    respondent: '0x789d35Cc6634C0532925a3b844Bc9e7595f8c2E9',
    amount: '8,750.00',
    token: 'USDT',
    status: 'pending',
    reason: 'Unauthorized transaction',
    description: 'Claimant reports an unauthorized transaction from their account. Investigation pending.',
    createdAt: '2026-01-22T09:00:00Z',
    deadline: '2026-01-29T09:00:00Z',
    evidence: [],
    timeline: [
      { id: 't1', type: 'filed', description: 'Dispute filed', timestamp: '2026-01-22T09:00:00Z' },
    ],
  },
};

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function DisputeDetailPage() {
  const params = useParams();
  const router = useRouter();
  const disputeId = params.id as string;
  
  const [dispute, setDispute] = useState<Dispute | null>(null);
  const [loading, setLoading] = useState(true);
  const [voting, setVoting] = useState(false);
  const [userVote, setUserVote] = useState<'claimant' | 'respondent' | null>(null);
  const [showEvidenceModal, setShowEvidenceModal] = useState(false);

  useEffect(() => {
    // Simulate API call
    setLoading(true);
    setTimeout(() => {
      const found = mockDisputes[disputeId];
      setDispute(found || null);
      setLoading(false);
    }, 500);
  }, [disputeId]);

  const handleVote = async (vote: 'claimant' | 'respondent') => {
    if (!dispute || voting) return;
    
    setVoting(true);
    // Simulate voting API call
    await new Promise(resolve => setTimeout(resolve, 1500));
    
    setUserVote(vote);
    setDispute(prev => {
      if (!prev || !prev.votes) return prev;
      const newVotes = { ...prev.votes };
      newVotes.total += 1;
      if (vote === 'claimant') {
        newVotes.for = Math.round(((newVotes.for * (newVotes.total - 1) / 100) + 1) / newVotes.total * 100);
        newVotes.against = 100 - newVotes.for;
      } else {
        newVotes.against = Math.round(((newVotes.against * (newVotes.total - 1) / 100) + 1) / newVotes.total * 100);
        newVotes.for = 100 - newVotes.against;
      }
      return { ...prev, votes: newVotes };
    });
    
    setVoting(false);
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'pending':
        return (
          <span className="flex items-center gap-2 px-3 py-1.5 rounded-full text-sm bg-slate-700 text-slate-300">
            <ClockIcon className="w-4 h-4" />
            Pending Review
          </span>
        );
      case 'evidence':
        return (
          <span className="flex items-center gap-2 px-3 py-1.5 rounded-full text-sm bg-blue-900/50 text-blue-400 border border-blue-700">
            <ChatBubbleLeftRightIcon className="w-4 h-4" />
            Evidence Collection
          </span>
        );
      case 'voting':
        return (
          <span className="flex items-center gap-2 px-3 py-1.5 rounded-full text-sm bg-purple-900/50 text-purple-400 border border-purple-700">
            <ScaleIcon className="w-4 h-4" />
            Active Voting
          </span>
        );
      case 'escalated':
        return (
          <span className="flex items-center gap-2 px-3 py-1.5 rounded-full text-sm bg-orange-900/50 text-orange-400 border border-orange-700">
            <ExclamationTriangleIcon className="w-4 h-4" />
            Escalated to Kleros
          </span>
        );
      case 'resolved':
        return (
          <span className="flex items-center gap-2 px-3 py-1.5 rounded-full text-sm bg-green-900/50 text-green-400 border border-green-700">
            <CheckCircleIcon className="w-4 h-4" />
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
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getDaysRemaining = (deadline: string) => {
    const days = Math.ceil((new Date(deadline).getTime() - Date.now()) / (1000 * 60 * 60 * 24));
    if (days < 0) return 'Expired';
    if (days === 0) return 'Today';
    if (days === 1) return '1 day remaining';
    return `${days} days remaining`;
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="flex items-center gap-3 text-slate-400">
          <ArrowPathIcon className="w-6 h-6 animate-spin" />
          Loading dispute...
        </div>
      </div>
    );
  }

  if (!dispute) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="text-center">
          <XCircleIcon className="w-16 h-16 text-red-400 mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-white mb-2">Dispute Not Found</h1>
          <p className="text-slate-400 mb-6">The dispute you&apos;re looking for doesn&apos;t exist.</p>
          <Link
            href="/war-room/disputes"
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg inline-flex items-center gap-2"
          >
            <ArrowLeftIcon className="w-4 h-4" />
            Back to Disputes
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-900 text-white">
      <div className="max-w-6xl mx-auto p-6">
        {/* Back Button */}
        <Link
          href="/war-room/disputes"
          className="inline-flex items-center gap-2 text-slate-400 hover:text-white mb-6 transition-colors"
        >
          <ArrowLeftIcon className="w-4 h-4" />
          Back to Disputes
        </Link>

        {/* Header */}
        <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 mb-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <h1 className="text-2xl font-bold">{dispute.id}</h1>
                {getStatusBadge(dispute.status)}
              </div>
              <p className="text-slate-400">{dispute.reason}</p>
            </div>
            <div className="text-right">
              <p className="text-3xl font-bold">{dispute.amount} {dispute.token}</p>
              <p className="text-slate-500 text-sm mt-1">
                <CalendarIcon className="w-4 h-4 inline mr-1" />
                {getDaysRemaining(dispute.deadline)}
              </p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main Content */}
          <div className="lg:col-span-2 space-y-6">
            {/* Description */}
            <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
              <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <DocumentTextIcon className="w-5 h-5 text-blue-400" />
                Description
              </h2>
              <p className="text-slate-300 leading-relaxed">{dispute.description}</p>
            </div>

            {/* Parties */}
            <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
              <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <UserIcon className="w-5 h-5 text-blue-400" />
                Parties Involved
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-slate-700/50 rounded-lg p-4">
                  <p className="text-blue-400 text-sm font-medium mb-2">Claimant</p>
                  <code className="text-slate-200 text-sm font-mono break-all">
                    {dispute.claimant}
                  </code>
                </div>
                <div className="bg-slate-700/50 rounded-lg p-4">
                  <p className="text-orange-400 text-sm font-medium mb-2">Respondent</p>
                  <code className="text-slate-200 text-sm font-mono break-all">
                    {dispute.respondent}
                  </code>
                </div>
              </div>
            </div>

            {/* Evidence */}
            <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold flex items-center gap-2">
                  <DocumentTextIcon className="w-5 h-5 text-blue-400" />
                  Evidence ({dispute.evidence.length})
                </h2>
                {dispute.status === 'evidence' && (
                  <button
                    onClick={() => setShowEvidenceModal(true)}
                    className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded text-sm"
                  >
                    Submit Evidence
                  </button>
                )}
              </div>
              
              {dispute.evidence.length === 0 ? (
                <p className="text-slate-500 text-center py-8">No evidence submitted yet</p>
              ) : (
                <div className="space-y-3">
                  {dispute.evidence.map((ev) => (
                    <div key={ev.id} className="bg-slate-700/50 rounded-lg p-4">
                      <div className="flex items-start justify-between">
                        <div>
                          <div className="flex items-center gap-2 mb-1">
                            <span className={`text-xs px-2 py-0.5 rounded ${
                              ev.submittedBy === 'claimant' 
                                ? 'bg-blue-900/50 text-blue-400' 
                                : 'bg-orange-900/50 text-orange-400'
                            }`}>
                              {ev.submittedBy}
                            </span>
                            <span className="text-xs px-2 py-0.5 rounded bg-slate-600 text-slate-300">
                              {ev.type}
                            </span>
                          </div>
                          <h3 className="font-medium text-white">{ev.title}</h3>
                          <p className="text-sm text-slate-400 mt-1">{ev.description}</p>
                        </div>
                        <span className="text-xs text-slate-500">
                          {formatDate(ev.timestamp)}
                        </span>
                      </div>
                      <div className="mt-2 pt-2 border-t border-slate-600">
                        <code className="text-xs text-slate-500">Hash: {ev.hash}</code>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Voting Section */}
            {dispute.status === 'voting' && dispute.votes && (
              <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
                <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <ScaleIcon className="w-5 h-5 text-purple-400" />
                  Cast Your Vote
                </h2>
                
                {/* Voting Progress */}
                <div className="mb-6">
                  <div className="flex items-center justify-between text-sm mb-2">
                    <span className="text-blue-400">Claimant ({dispute.votes.for}%)</span>
                    <span className="text-slate-500">{dispute.votes.total} votes cast</span>
                    <span className="text-orange-400">Respondent ({dispute.votes.against}%)</span>
                  </div>
                  <div className="flex h-4 rounded-full overflow-hidden bg-slate-700">
                    <div 
                      className="bg-blue-500 transition-all duration-500"
                      style={{ width: `${dispute.votes.for}%` }}
                    />
                    <div 
                      className="bg-orange-500 transition-all duration-500"
                      style={{ width: `${dispute.votes.against}%` }}
                    />
                  </div>
                </div>

                {userVote ? (
                  <div className="text-center py-4 bg-green-900/20 border border-green-700 rounded-lg">
                    <CheckCircleIcon className="w-8 h-8 text-green-400 mx-auto mb-2" />
                    <p className="text-green-400">You voted for the {userVote}</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-4">
                    <button
                      onClick={() => handleVote('claimant')}
                      disabled={voting}
                      className="py-4 bg-blue-600 hover:bg-blue-700 rounded-lg font-semibold transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                    >
                      {voting ? (
                        <ArrowPathIcon className="w-5 h-5 animate-spin" />
                      ) : (
                        <>Vote for Claimant</>
                      )}
                    </button>
                    <button
                      onClick={() => handleVote('respondent')}
                      disabled={voting}
                      className="py-4 bg-orange-600 hover:bg-orange-700 rounded-lg font-semibold transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                    >
                      {voting ? (
                        <ArrowPathIcon className="w-5 h-5 animate-spin" />
                      ) : (
                        <>Vote for Respondent</>
                      )}
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Resolution */}
            {dispute.status === 'resolved' && dispute.resolution && (
              <div className="bg-green-900/20 border border-green-700 rounded-xl p-6">
                <div className="flex items-center gap-3 mb-2">
                  <CheckCircleIcon className="w-8 h-8 text-green-400" />
                  <div>
                    <h2 className="text-lg font-semibold text-green-400">Dispute Resolved</h2>
                    <p className="text-slate-300">
                      Decision in favor of the <span className="font-semibold">{dispute.resolution}</span>
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Info Card */}
            <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
              <h3 className="text-sm font-semibold text-slate-400 uppercase mb-4">Details</h3>
              <dl className="space-y-4">
                <div>
                  <dt className="text-xs text-slate-500">Transaction ID</dt>
                  <dd className="text-sm font-mono text-slate-300 mt-1">{dispute.transactionId}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Filed On</dt>
                  <dd className="text-sm text-slate-300 mt-1">{formatDate(dispute.createdAt)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Deadline</dt>
                  <dd className="text-sm text-slate-300 mt-1">{formatDate(dispute.deadline)}</dd>
                </div>
              </dl>
            </div>

            {/* Timeline */}
            <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
              <h3 className="text-sm font-semibold text-slate-400 uppercase mb-4">Timeline</h3>
              <div className="space-y-4">
                {dispute.timeline.map((event, idx) => (
                  <div key={event.id} className="relative pl-6">
                    {idx < dispute.timeline.length - 1 && (
                      <div className="absolute left-[9px] top-6 bottom-0 w-px bg-slate-700" />
                    )}
                    <div className={`absolute left-0 top-1 w-[18px] h-[18px] rounded-full flex items-center justify-center ${
                      event.type === 'resolved' ? 'bg-green-500' :
                      event.type === 'escalated' ? 'bg-orange-500' :
                      event.type === 'voting_started' ? 'bg-purple-500' :
                      'bg-slate-600'
                    }`}>
                      <div className="w-2 h-2 bg-white rounded-full" />
                    </div>
                    <p className="text-sm text-slate-300">{event.description}</p>
                    <p className="text-xs text-slate-500 mt-1">
                      {formatDate(event.timestamp)}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Evidence Modal (simplified) */}
      {showEvidenceModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 max-w-md w-full">
            <h2 className="text-lg font-semibold mb-4">Submit Evidence</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">Title</label>
                <input
                  type="text"
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white"
                  placeholder="Evidence title"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">Description</label>
                <textarea
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white h-24"
                  placeholder="Describe the evidence..."
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">File</label>
                <input
                  type="file"
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white"
                />
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setShowEvidenceModal(false)}
                className="flex-1 px-4 py-2 bg-slate-600 hover:bg-slate-500 rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  alert('Evidence submission would be processed here');
                  setShowEvidenceModal(false);
                }}
                className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg"
              >
                Submit
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
