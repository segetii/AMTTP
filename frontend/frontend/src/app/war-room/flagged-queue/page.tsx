'use client';

import { useState } from 'react';
import React from 'react';
import Link from 'next/link';
import { useFlaggedQueue, FlaggedTransaction } from '@/lib/data-service';
import ExplainabilityModal, { getRiskLevel, getRiskColor } from '@/components/shared/ExplainabilityModal';

// Local view-model with action state
interface FlaggedTxView extends FlaggedTransaction {
  actionStatus: 'pending' | 'approved' | 'rejected' | 'escalated';
}

// ═══════════════════════════════════════════════════════════════════════════════
// STAT CARDS
// ═══════════════════════════════════════════════════════════════════════════════

function QueueStats({ transactions }: { transactions: FlaggedTxView[] }) {
  const pending = transactions.filter(t => t.actionStatus === 'pending').length;
  const critical = transactions.filter(t => {
    const level = getRiskLevel(t.riskScore);
    return level === 'CRITICAL' && t.actionStatus === 'pending';
  }).length;
  const approved = transactions.filter(t => t.actionStatus === 'approved').length;
  const escalated = transactions.filter(t => t.actionStatus === 'escalated').length;

  return (
    <div className="grid grid-cols-4 gap-4 mb-6">
      <div className="bg-surface rounded-lg p-4 border border-borderSubtle">
        <div className="flex items-center justify-between">
          <span className="text-mutedText text-sm">Pending Review</span>
          <span className="text-2xl">📋</span>
        </div>
        <div className="mt-2">
          <span className="text-3xl font-bold text-text">{pending}</span>
        </div>
      </div>
      <div className="bg-surface rounded-lg p-4 border border-red-900/50">
        <div className="flex items-center justify-between">
          <span className="text-mutedText text-sm">Critical</span>
          <span className="text-2xl">🚨</span>
        </div>
        <div className="mt-2">
          <span className={`text-3xl font-bold ${critical > 0 ? 'text-red-400' : 'text-text'}`}>
            {critical}
          </span>
        </div>
      </div>
      <div className="bg-surface rounded-lg p-4 border border-borderSubtle">
        <div className="flex items-center justify-between">
          <span className="text-mutedText text-sm">Approved</span>
          <span className="text-2xl">✅</span>
        </div>
        <div className="mt-2">
          <span className="text-3xl font-bold text-green-400">{approved}</span>
        </div>
      </div>
      <div className="bg-surface rounded-lg p-4 border border-borderSubtle">
        <div className="flex items-center justify-between">
          <span className="text-mutedText text-sm">Escalated</span>
          <span className="text-2xl">⬆️</span>
        </div>
        <div className="mt-2">
          <span className="text-3xl font-bold text-purple-400">{escalated}</span>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// FLAGGED TRANSACTION ROW (card style — matches AlertRow design)
// ═══════════════════════════════════════════════════════════════════════════════

const riskAccent: Record<string, string> = {
  CRITICAL: 'border-l-red-500',
  HIGH:     'border-l-orange-400',
  MEDIUM:   'border-l-amber-400',
  LOW:      'border-l-sky-400',
};

const riskDot: Record<string, string> = {
  CRITICAL: 'bg-red-500 shadow-red-500/40 shadow-[0_0_6px]',
  HIGH:     'bg-orange-400',
  MEDIUM:   'bg-amber-400',
  LOW:      'bg-sky-400',
};

const statusLabel: Record<string, { text: string; cls: string }> = {
  pending:   { text: 'Pending',   cls: 'text-yellow-400' },
  approved:  { text: 'Approved',  cls: 'text-emerald-400' },
  rejected:  { text: 'Rejected',  cls: 'text-red-400' },
  escalated: { text: 'Escalated', cls: 'text-purple-400' },
};

function FlaggedTxRow({
  tx,
  isSelected,
  onSelect,
  onAction,
}: {
  tx: FlaggedTxView;
  isSelected: boolean;
  onSelect: () => void;
  onAction?: (txId: string, action: 'approve' | 'reject' | 'escalate') => void;
}) {
  const level = getRiskLevel(tx.riskScore);
  const st = statusLabel[tx.actionStatus] || statusLabel.pending;

  return (
    <div
      onClick={onSelect}
      className={`
        group relative flex items-center gap-4 px-4 py-3.5
        border-l-[3px] border-b border-b-slate-800/60
        cursor-pointer transition-all duration-150
        ${riskAccent[level] || 'border-l-slate-600'}
        ${isSelected
          ? 'bg-slate-800/80 border-b-slate-700'
          : 'bg-transparent hover:bg-slate-800/40'}
      `}
    >
      {/* Risk dot */}
      <div className={`w-2 h-2 rounded-full flex-shrink-0 ${riskDot[level] || 'bg-slate-500'}`} />

      {/* Icon */}
      <span className="text-base flex-shrink-0 opacity-70 group-hover:opacity-100 transition-opacity">
        {level === 'CRITICAL' ? '🚨' : level === 'HIGH' ? '⚠️' : '🔍'}
      </span>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2">
          <h3 className="text-[13px] font-medium text-slate-200 truncate">
            {tx.reason || tx.flags?.[0] || 'Flagged transaction'}
          </h3>
          <span className={`text-[11px] font-semibold tabular-nums flex-shrink-0 ${
            tx.riskScore >= 85 ? 'text-red-400' : tx.riskScore >= 70 ? 'text-orange-400' : tx.riskScore >= 50 ? 'text-yellow-400' : 'text-green-400'
          }`}>{Math.round(tx.riskScore)}</span>
        </div>
        <p className="text-xs text-slate-500 truncate mt-0.5">
          {tx.from || tx.address || 'Unknown address'} → {tx.to || '—'}
          {tx.value != null ? ` • ${tx.value} ETH` : ''}
        </p>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-3 flex-shrink-0">
        <span className={`text-[11px] font-medium ${st.cls}`}>{st.text}</span>
        <span className="text-[11px] text-slate-600 tabular-nums w-14 text-right">
          {tx.timestamp ? formatTimeAgo(tx.timestamp) : '—'}
        </span>

        {/* Quick approve */}
        {tx.actionStatus === 'pending' && onAction && (
          <button
            onClick={(e) => { e.stopPropagation(); onAction(tx.id, 'approve'); }}
            className="opacity-0 group-hover:opacity-100 text-[11px] px-2 py-0.5 rounded
                       bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/20
                       hover:bg-emerald-500/20 transition-all duration-150"
          >
            Approve
          </button>
        )}

        {/* Chevron */}
        <svg className="w-4 h-4 text-slate-600 group-hover:text-slate-400 transition-colors flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5l7 7-7 7" />
        </svg>
      </div>
    </div>
  );
}

// Helper to format time ago
function formatTimeAgo(ts: string): string {
  const date = new Date(ts);
  if (isNaN(date.getTime())) return ts;
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);
  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${diffDays}d ago`;
}

// ═══════════════════════════════════════════════════════════════════════════════
// DETAIL MODAL (matches AlertDetailModal design)
// ═══════════════════════════════════════════════════════════════════════════════

function TxDetailModal({
  tx,
  onClose,
  onApprove,
  onReject,
  onEscalate,
  onExplain,
}: {
  tx: FlaggedTxView;
  onClose: () => void;
  onApprove: () => void;
  onReject: () => void;
  onEscalate: () => void;
  onExplain: () => void;
}) {
  const level = getRiskLevel(tx.riskScore);
  const rc = getRiskColor(level);

  const statusDot: Record<string, string> = {
    pending:   'bg-yellow-400',
    approved:  'bg-emerald-400',
    rejected:  'bg-red-500',
    escalated: 'bg-purple-400',
  };

  const MonoField = ({ label, val }: { label: string; val: string }) => (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-1">{label}</div>
      <div className="font-mono text-[13px] text-slate-300 bg-slate-800/60 rounded-lg px-3 py-2 truncate select-all" title={val}>{val || '—'}</div>
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      {/* Overlay */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-[2px]" />

      {/* Panel */}
      <div
        className="relative w-full max-w-xl mx-4 bg-[#0f1219] rounded-2xl border border-slate-800
                   shadow-[0_24px_80px_-12px_rgba(0,0,0,0.6)] max-h-[88vh] flex flex-col
                   animate-in fade-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ─── Header ─── */}
        <div className="flex items-start gap-4 px-6 pt-6 pb-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2.5 mb-1.5">
              <div className={`w-2 h-2 rounded-full flex-shrink-0 ${statusDot[tx.actionStatus] || 'bg-slate-500'}`} />
              <span className="text-[11px] font-medium uppercase tracking-wider text-slate-500">
                {level} • {tx.actionStatus}
              </span>
            </div>
            <h2 className="text-lg font-semibold text-white leading-snug">
              {tx.reason || tx.flags?.[0] || 'Flagged Transaction'}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 -mt-1 -mr-1 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* ─── Scrollable body ─── */}
        <div className="flex-1 overflow-y-auto px-6 pb-6 space-y-5 scrollbar-thin">

          {/* Risk score — compact inline bar */}
          <div className={`flex items-center gap-4 px-4 py-3 rounded-xl ${rc.bgSoft} ring-1 ${rc.ring}`}>
            <div className="flex-1">
              <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-1.5">Risk Score</div>
              <div className="w-full h-1.5 bg-slate-700/60 rounded-full overflow-hidden">
                <div className={`h-full rounded-full ${rc.bg} transition-all duration-500`} style={{ width: `${Math.min(tx.riskScore, 100)}%` }} />
              </div>
            </div>
            <div className="text-right flex-shrink-0">
              <span className={`text-2xl font-bold tabular-nums ${rc.text}`}>{Math.round(tx.riskScore)}</span>
              <div className={`text-[11px] font-medium ${rc.text}`}>{level}</div>
            </div>
          </div>

          {/* Transaction details — clean grid */}
          <div className="space-y-3">
            <div className="text-[11px] uppercase tracking-wider text-slate-500">Transaction</div>
            {(tx.hash || tx.id) && <MonoField label="Hash" val={tx.hash || tx.id} />}
            <div className="grid grid-cols-2 gap-3">
              <MonoField label="From" val={tx.from || tx.address || ''} />
              <MonoField label="To" val={tx.to || ''} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              {tx.value != null && (
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-1">Amount</div>
                  <div className="text-lg font-semibold text-white tabular-nums">{tx.value} <span className="text-sm font-normal text-slate-500">ETH</span></div>
                </div>
              )}
              {tx.timestamp && (
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-1">Timestamp</div>
                  <div className="text-[13px] text-slate-300">{tx.timestamp}</div>
                </div>
              )}
            </div>
          </div>

          {/* Flag reason */}
          {(tx.reason || tx.flags?.length) && (
            <div>
              <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">Flag Reason</div>
              <p className="text-[13px] text-slate-400 leading-relaxed">{tx.reason || tx.flags?.[0] || 'Flagged by ML risk engine'}</p>
            </div>
          )}

          {/* Tags — minimal pills */}
          {tx.flags && tx.flags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {tx.flags.map((flag) => (
                <span key={flag} className="px-2.5 py-0.5 rounded-full bg-slate-800 text-[11px] text-slate-500 ring-1 ring-slate-700/60">{flag}</span>
              ))}
            </div>
          )}

          {/* Timeline — thin & compact */}
          <div className="pt-1">
            <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-3">Activity</div>
            <div className="space-y-0 relative ml-1.5">
              <div className="absolute left-[3px] top-1 bottom-1 w-px bg-slate-800" />
              {[
                { label: 'Flagged by ML engine', color: 'bg-slate-500' },
                ...(tx.actionStatus === 'approved' ? [{ label: 'Approved by analyst', color: 'bg-emerald-400' }] : []),
                ...(tx.actionStatus === 'rejected' ? [{ label: 'Rejected by analyst', color: 'bg-red-400' }] : []),
                ...(tx.actionStatus === 'escalated' ? [{ label: 'Escalated for review', color: 'bg-purple-400' }] : []),
              ].map((ev, i) => (
                <div key={i} className="flex items-center gap-3 py-1.5 relative">
                  <div className={`w-[7px] h-[7px] rounded-full ${ev.color} flex-shrink-0 z-10 ring-2 ring-[#0f1219]`} />
                  <span className="text-[12px] text-slate-400">{ev.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ─── Actions bar ─── */}
        <div className="px-6 py-4 border-t border-slate-800/80 flex items-center gap-2">
          {tx.actionStatus === 'pending' && (
            <>
              <button onClick={onApprove}
                className="flex-1 px-3 py-2 rounded-lg text-[13px] font-medium
                           bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/20
                           hover:bg-emerald-500/20 transition-colors">
                Approve
              </button>
              <button onClick={onReject}
                className="flex-1 px-3 py-2 rounded-lg text-[13px] font-medium
                           bg-red-500/10 text-red-400 ring-1 ring-red-500/20
                           hover:bg-red-500/20 transition-colors">
                Reject
              </button>
              <button onClick={onEscalate}
                className="flex-1 px-3 py-2 rounded-lg text-[13px] font-medium
                           bg-purple-500/10 text-purple-400 ring-1 ring-purple-500/20
                           hover:bg-purple-500/20 transition-colors">
                Escalate
              </button>
            </>
          )}
          <button onClick={onClose}
            className="px-4 py-2 rounded-lg text-[13px] text-slate-500 hover:text-slate-300
                       hover:bg-slate-800 transition-colors">
            Close
          </button>
          <button onClick={onExplain}
            className="px-4 py-2 rounded-lg text-[13px] font-medium
                       bg-indigo-500/10 text-indigo-400 ring-1 ring-indigo-500/20
                       hover:bg-indigo-500/20 transition-colors flex items-center gap-1.5">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            Explainability
          </button>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ═══════════════════════════════════════════════════════════════════════════════

export default function FlaggedQueuePage() {
  const { data: rawData, loading, error } = useFlaggedQueue();
  const [actionOverrides, setActionOverrides] = useState<Record<string, FlaggedTxView['actionStatus']>>({});
  const [selectedTx, setSelectedTx] = useState<FlaggedTxView | null>(null);
  const [explainTx, setExplainTx] = useState<FlaggedTransaction | null>(null);
  const [filter, setFilter] = useState<'all' | 'pending' | 'approved' | 'rejected' | 'escalated'>('pending');
  const [search, setSearch] = useState('');

  // Merge API data with local action overrides
  const transactions: FlaggedTxView[] = rawData.map(tx => ({
    ...tx,
    actionStatus: actionOverrides[tx.id] || 'pending',
  }));

  let filteredTxs = filter === 'all'
    ? transactions
    : transactions.filter(tx => tx.actionStatus === filter);

  if (search) {
    const q = search.toLowerCase();
    filteredTxs = filteredTxs.filter(tx =>
      (tx.hash || tx.id).toLowerCase().includes(q) ||
      (tx.address || tx.from || '').toLowerCase().includes(q) ||
      (tx.reason || '').toLowerCase().includes(q)
    );
  }

  // Sort: higher risk first, then by id
  filteredTxs.sort((a, b) => b.riskScore - a.riskScore);

  const handleAction = (txId: string, action: 'approve' | 'reject' | 'escalate') => {
    const status = action === 'approve' ? 'approved' : action === 'reject' ? 'rejected' : 'escalated';
    setActionOverrides(prev => ({ ...prev, [txId]: status }));
    setSelectedTx(null);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <Link href="/war-room" className="text-mutedText hover:text-text text-sm">
            ← War Room
          </Link>
        </div>
        <h1 className="text-2xl font-bold text-text">Flagged Queue</h1>
        <p className="text-mutedText">Review and action flagged transactions</p>
      </div>

      {/* Status */}
      {error && <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-red-400 text-sm">⚠ Backend unavailable: {error}</div>}
      {loading && <div className="text-zinc-500 text-sm">Loading flagged transactions...</div>}

      {/* Stats */}
      <QueueStats transactions={transactions} />

      {/* Filters — bottom-border tabs matching Alert Center */}
      <div className="flex gap-4 mb-6 border-b border-slate-800">
        {(['all', 'pending', 'approved', 'rejected', 'escalated'] as const).map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-4 py-3 text-sm font-medium transition-colors border-b-2 -mb-px capitalize ${
              filter === f
                ? 'text-cyan-400 border-cyan-400'
                : 'text-mutedText border-transparent hover:text-text'
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {/* Search + count toolbar */}
      <div className="flex items-center gap-2 px-1 pb-4">
        <div className="relative flex-1 max-w-xs">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search hash, address, reason..."
            className="w-full pl-9 pr-3 py-1.5 bg-slate-800/60 border border-slate-700/60 rounded-lg
                       text-sm text-slate-300 placeholder-slate-600
                       focus:outline-none focus:border-slate-600 focus:bg-slate-800 transition-colors"
          />
        </div>
        <span className="text-[11px] text-slate-600 ml-auto tabular-nums">{filteredTxs.length} / {transactions.length}</span>
      </div>

      {/* Transaction List — card rows matching AlertList */}
      {filteredTxs.length === 0 ? (
        <div className="py-16 text-center">
          <div className="text-4xl mb-3 opacity-30">📋</div>
          <p className="text-sm text-slate-500">
            {search || filter !== 'all'
              ? 'No transactions match your filters'
              : 'No flagged transactions'}
          </p>
        </div>
      ) : (
        <div className="rounded-xl border border-slate-800/80 overflow-hidden divide-y divide-slate-800/40">
          {filteredTxs.map((tx) => (
            <FlaggedTxRow
              key={tx.id}
              tx={tx}
              isSelected={selectedTx?.id === tx.id}
              onSelect={() => setSelectedTx(tx)}
              onAction={handleAction}
            />
          ))}
        </div>
      )}

      {/* Detail Modal */}
      {selectedTx && (
        <TxDetailModal
          tx={selectedTx}
          onClose={() => setSelectedTx(null)}
          onApprove={() => handleAction(selectedTx.id, 'approve')}
          onReject={() => handleAction(selectedTx.id, 'reject')}
          onEscalate={() => handleAction(selectedTx.id, 'escalate')}
          onExplain={() => { setExplainTx(selectedTx); setSelectedTx(null); }}
        />
      )}

      {/* Explainability Modal */}
      {explainTx && (
        <ExplainabilityModal
          item={{
            id: explainTx.id,
            address: explainTx.address || explainTx.from,
            riskScore: explainTx.riskScore,
            riskLevel: explainTx.riskLevel,
            reason: explainTx.reason || explainTx.flags?.[0],
            hash: explainTx.hash,
            from: explainTx.from,
            to: explainTx.to,
            value: explainTx.value,
            timestamp: explainTx.timestamp,
            flags: explainTx.flags,
            patternCount: explainTx.patternCount,
            totalTransactions: explainTx.totalTransactions,
            uniqueCounterparties: explainTx.uniqueCounterparties,
          }}
          onClose={() => setExplainTx(null)}
          onInvestigate={() => {
            setExplainTx(null);
            window.open(`/war-room/detection/graph?address=${explainTx.address || explainTx.from || ''}`, '_blank');
          }}
        />
      )}
    </div>
  );
}
