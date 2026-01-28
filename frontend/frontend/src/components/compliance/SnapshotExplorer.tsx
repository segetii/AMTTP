'use client';

/**
 * Snapshot Explorer Component
 * 
 * Sprint 11: Compliance Reporting & Export System
 * 
 * Ground Truth Reference:
 * - Browse and verify UI snapshots
 * - Integrity verification with chain anchoring
 * - Evidence linking capability
 */

import React, { useState, useEffect } from 'react';
import {
  UISnapshot,
  SnapshotFilter,
  formatSnapshotDate,
  truncateHash,
} from '@/types/compliance-report';
import { useSnapshots } from '@/lib/compliance-report-service';

// ═══════════════════════════════════════════════════════════════════════════════
// INTERFACES
// ═══════════════════════════════════════════════════════════════════════════════

interface SnapshotExplorerProps {
  onSelectSnapshot?: (snapshot: UISnapshot) => void;
  onVerify?: (snapshot: UISnapshot) => void;
  className?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// FILTER PANEL
// ═══════════════════════════════════════════════════════════════════════════════

function FilterPanel({ 
  filter, 
  onChange 
}: { 
  filter: SnapshotFilter; 
  onChange: (filter: SnapshotFilter) => void;
}) {
  return (
    <div className="flex flex-wrap gap-3 p-4 bg-slate-800/50 rounded-lg border border-slate-700">
      <div className="flex-1 min-w-[200px]">
        <label className="block text-xs text-slate-400 mb-1">Start Date</label>
        <input
          type="datetime-local"
          value={filter.startDate?.slice(0, 16) || ''}
          onChange={(e) => onChange({ ...filter, startDate: e.target.value ? new Date(e.target.value).toISOString() : undefined })}
          className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-sm text-white"
        />
      </div>
      
      <div className="flex-1 min-w-[200px]">
        <label className="block text-xs text-slate-400 mb-1">End Date</label>
        <input
          type="datetime-local"
          value={filter.endDate?.slice(0, 16) || ''}
          onChange={(e) => onChange({ ...filter, endDate: e.target.value ? new Date(e.target.value).toISOString() : undefined })}
          className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-sm text-white"
        />
      </div>
      
      <div className="flex-1 min-w-[150px]">
        <label className="block text-xs text-slate-400 mb-1">Screen</label>
        <select
          value={filter.screenId || ''}
          onChange={(e) => onChange({ ...filter, screenId: e.target.value || undefined })}
          className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-sm text-white"
        >
          <option value="">All Screens</option>
          <option value="focus-transfer">Focus - Transfer</option>
          <option value="focus-trust">Focus - Trust</option>
          <option value="war-room-detection">War Room - Detection</option>
          <option value="war-room-policies">War Room - Policies</option>
        </select>
      </div>
      
      <div className="flex-1 min-w-[150px]">
        <label className="block text-xs text-slate-400 mb-1">Verification</label>
        <select
          value={filter.verified === undefined ? '' : filter.verified.toString()}
          onChange={(e) => onChange({ 
            ...filter, 
            verified: e.target.value === '' ? undefined : e.target.value === 'true' 
          })}
          className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-sm text-white"
        >
          <option value="">All</option>
          <option value="true">Verified</option>
          <option value="false">Pending</option>
        </select>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// SNAPSHOT CARD
// ═══════════════════════════════════════════════════════════════════════════════

function SnapshotCard({
  snapshot,
  isSelected,
  onSelect,
  onVerify,
}: {
  snapshot: UISnapshot;
  isSelected: boolean;
  onSelect: () => void;
  onVerify: () => void;
}) {
  return (
    <div
      className={`p-4 bg-slate-800 border rounded-lg transition-all cursor-pointer hover:border-cyan-500/50 ${
        isSelected ? 'border-cyan-400 ring-1 ring-cyan-400/30' : 'border-slate-700'
      }`}
      onClick={onSelect}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div>
          <h4 className="font-medium text-white">{snapshot.screenName}</h4>
          <p className="text-xs text-slate-400">{formatSnapshotDate(snapshot.timestamp)}</p>
        </div>
        <div className={`px-2 py-1 rounded text-xs font-medium ${
          snapshot.integrityProof.verified
            ? 'bg-green-900/50 text-green-400 border border-green-600/30'
            : 'bg-yellow-900/50 text-yellow-400 border border-yellow-600/30'
        }`}>
          {snapshot.integrityProof.verified ? '✓ Verified' : '⏳ Pending'}
        </div>
      </div>
      
      {/* Hash Info */}
      <div className="space-y-2 mb-3">
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-500">State Hash</span>
          <code className="text-xs text-cyan-400 font-mono">{truncateHash(snapshot.stateHash)}</code>
        </div>
        {snapshot.integrityProof.onChainAnchor && (
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-500">On-Chain</span>
            <code className="text-xs text-purple-400 font-mono">{truncateHash(snapshot.integrityProof.onChainAnchor)}</code>
          </div>
        )}
      </div>
      
      {/* User Context */}
      <div className="flex items-center gap-2 mb-3">
        <span className={`px-2 py-0.5 rounded text-xs ${
          snapshot.userContext.mode === 'focus' 
            ? 'bg-blue-900/50 text-blue-400' 
            : 'bg-red-900/50 text-red-400'
        }`}>
          {snapshot.userContext.mode === 'focus' ? '🎯 Focus' : '🔴 War Room'}
        </span>
        <span className="px-2 py-0.5 bg-slate-700 rounded text-xs text-slate-300">
          {snapshot.userContext.role}
        </span>
      </div>
      
      {/* Components */}
      <div className="text-xs text-slate-400 mb-3">
        {snapshot.components.length} component{snapshot.components.length !== 1 ? 's' : ''} captured
        {snapshot.components.filter(c => c.interacted).length > 0 && (
          <span className="text-cyan-400"> • {snapshot.components.filter(c => c.interacted).length} interacted</span>
        )}
      </div>
      
      {/* Transaction Context */}
      {snapshot.transactionContext && (
        <div className="p-2 bg-slate-900/50 rounded border border-slate-700 mb-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400">{snapshot.transactionContext.action}</span>
            <span className="text-xs text-green-400 font-mono">{snapshot.transactionContext.amount}</span>
          </div>
        </div>
      )}
      
      {/* Actions */}
      <div className="flex items-center justify-end gap-2">
        {!snapshot.integrityProof.verified && (
          <button
            onClick={(e) => { e.stopPropagation(); onVerify(); }}
            className="px-3 py-1.5 text-xs bg-cyan-600 text-white rounded hover:bg-cyan-500 transition-colors"
          >
            Verify Integrity
          </button>
        )}
        <button
          onClick={(e) => { e.stopPropagation(); onSelect(); }}
          className="px-3 py-1.5 text-xs bg-slate-700 text-slate-300 rounded hover:bg-slate-600 transition-colors"
        >
          View Details
        </button>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// SNAPSHOT DETAIL PANEL
// ═══════════════════════════════════════════════════════════════════════════════

function SnapshotDetailPanel({ 
  snapshot,
  onClose,
}: { 
  snapshot: UISnapshot;
  onClose: () => void;
}) {
  const [activeTab, setActiveTab] = useState<'overview' | 'components' | 'proof'>('overview');
  
  return (
    <div className="h-full flex flex-col bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-slate-700 flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-white">{snapshot.screenName}</h3>
          <p className="text-xs text-slate-400">{formatSnapshotDate(snapshot.timestamp)}</p>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 text-slate-400 hover:text-white transition-colors"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
      
      {/* Tabs */}
      <div className="flex border-b border-slate-700">
        {(['overview', 'components', 'proof'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab
                ? 'text-cyan-400 border-b-2 border-cyan-400'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>
      
      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === 'overview' && (
          <div className="space-y-4">
            {/* Basic Info */}
            <div className="grid grid-cols-2 gap-4">
              <div className="p-3 bg-slate-900 rounded border border-slate-700">
                <p className="text-xs text-slate-500 mb-1">Snapshot ID</p>
                <code className="text-sm text-white font-mono">{snapshot.id}</code>
              </div>
              <div className="p-3 bg-slate-900 rounded border border-slate-700">
                <p className="text-xs text-slate-500 mb-1">Session ID</p>
                <code className="text-sm text-white font-mono">{snapshot.sessionId}</code>
              </div>
              <div className="p-3 bg-slate-900 rounded border border-slate-700">
                <p className="text-xs text-slate-500 mb-1">User ID</p>
                <code className="text-sm text-white font-mono">{snapshot.userId}</code>
              </div>
              <div className="p-3 bg-slate-900 rounded border border-slate-700">
                <p className="text-xs text-slate-500 mb-1">Version</p>
                <code className="text-sm text-white font-mono">{snapshot.version}</code>
              </div>
            </div>
            
            {/* User Context */}
            <div className="p-4 bg-slate-900 rounded border border-slate-700">
              <h4 className="text-sm font-medium text-white mb-3">User Context</h4>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-sm text-slate-400">Role</span>
                  <span className="text-sm text-white">{snapshot.userContext.role}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-slate-400">Mode</span>
                  <span className="text-sm text-white capitalize">{snapshot.userContext.mode}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-slate-400">Active View</span>
                  <span className="text-sm text-white">{snapshot.userContext.activeView}</span>
                </div>
                <div>
                  <p className="text-sm text-slate-400 mb-1">Permissions</p>
                  <div className="flex flex-wrap gap-1">
                    {snapshot.userContext.permissions.map(p => (
                      <span key={p} className="px-2 py-0.5 bg-slate-800 rounded text-xs text-slate-300">
                        {p}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
            
            {/* Transaction Context */}
            {snapshot.transactionContext && (
              <div className="p-4 bg-slate-900 rounded border border-slate-700">
                <h4 className="text-sm font-medium text-white mb-3">Transaction Context</h4>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm text-slate-400">Transaction ID</span>
                    <code className="text-sm text-cyan-400 font-mono">{snapshot.transactionContext.transactionId}</code>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-slate-400">Action</span>
                    <span className="text-sm text-white">{snapshot.transactionContext.action}</span>
                  </div>
                  {snapshot.transactionContext.amount && (
                    <div className="flex justify-between">
                      <span className="text-sm text-slate-400">Amount</span>
                      <span className="text-sm text-green-400">{snapshot.transactionContext.amount}</span>
                    </div>
                  )}
                  {snapshot.transactionContext.recipient && (
                    <div className="flex justify-between">
                      <span className="text-sm text-slate-400">Recipient</span>
                      <code className="text-sm text-purple-400 font-mono">{truncateHash(snapshot.transactionContext.recipient, 6)}</code>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
        
        {activeTab === 'components' && (
          <div className="space-y-3">
            {snapshot.components.map(comp => (
              <div key={comp.id} className="p-4 bg-slate-900 rounded border border-slate-700">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <h4 className="text-sm font-medium text-white">{comp.name}</h4>
                    <code className="text-xs text-slate-500 font-mono">{comp.type}</code>
                  </div>
                  <div className="flex items-center gap-2">
                    {comp.visible && (
                      <span className="px-2 py-0.5 bg-green-900/50 text-green-400 rounded text-xs">Visible</span>
                    )}
                    {comp.interacted && (
                      <span className="px-2 py-0.5 bg-cyan-900/50 text-cyan-400 rounded text-xs">Interacted</span>
                    )}
                  </div>
                </div>
                
                {Object.keys(comp.state).length > 0 && (
                  <div className="mt-2 p-2 bg-slate-800 rounded">
                    <p className="text-xs text-slate-500 mb-1">State</p>
                    <pre className="text-xs text-slate-300 overflow-x-auto">
                      {JSON.stringify(comp.state, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
        
        {activeTab === 'proof' && (
          <div className="space-y-4">
            {/* Verification Status */}
            <div className={`p-4 rounded border ${
              snapshot.integrityProof.verified
                ? 'bg-green-900/20 border-green-600/30'
                : 'bg-yellow-900/20 border-yellow-600/30'
            }`}>
              <div className="flex items-center gap-2 mb-2">
                {snapshot.integrityProof.verified ? (
                  <>
                    <svg className="w-5 h-5 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                    </svg>
                    <span className="text-sm font-medium text-green-400">Integrity Verified</span>
                  </>
                ) : (
                  <>
                    <svg className="w-5 h-5 text-yellow-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span className="text-sm font-medium text-yellow-400">Pending Verification</span>
                  </>
                )}
              </div>
              <p className="text-xs text-slate-400">
                {snapshot.integrityProof.verified
                  ? 'This snapshot has been cryptographically verified against the on-chain anchor.'
                  : 'This snapshot is awaiting integrity verification.'}
              </p>
            </div>
            
            {/* Hash Chain */}
            <div className="p-4 bg-slate-900 rounded border border-slate-700">
              <h4 className="text-sm font-medium text-white mb-3">Hash Chain</h4>
              <div className="space-y-3">
                <div>
                  <p className="text-xs text-slate-500 mb-1">State Hash</p>
                  <code className="text-xs text-cyan-400 font-mono break-all">{snapshot.stateHash}</code>
                </div>
                <div>
                  <p className="text-xs text-slate-500 mb-1">Previous Hash</p>
                  <code className="text-xs text-slate-400 font-mono break-all">{snapshot.previousHash}</code>
                </div>
                <div>
                  <p className="text-xs text-slate-500 mb-1">Merkle Root</p>
                  <code className="text-xs text-purple-400 font-mono break-all">{snapshot.integrityProof.merkleRoot}</code>
                </div>
              </div>
            </div>
            
            {/* On-Chain Anchor */}
            {snapshot.integrityProof.onChainAnchor && (
              <div className="p-4 bg-slate-900 rounded border border-slate-700">
                <h4 className="text-sm font-medium text-white mb-3">On-Chain Anchor</h4>
                <div className="space-y-3">
                  <div>
                    <p className="text-xs text-slate-500 mb-1">Transaction Hash</p>
                    <code className="text-xs text-green-400 font-mono break-all">{snapshot.integrityProof.onChainAnchor}</code>
                  </div>
                  {snapshot.integrityProof.blockNumber && (
                    <div>
                      <p className="text-xs text-slate-500 mb-1">Block Number</p>
                      <code className="text-xs text-white font-mono">{snapshot.integrityProof.blockNumber.toLocaleString()}</code>
                    </div>
                  )}
                </div>
              </div>
            )}
            
            {/* Merkle Proof */}
            {snapshot.integrityProof.merkleProof.length > 0 && (
              <div className="p-4 bg-slate-900 rounded border border-slate-700">
                <h4 className="text-sm font-medium text-white mb-3">Merkle Proof</h4>
                <div className="space-y-1">
                  {snapshot.integrityProof.merkleProof.map((hash, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <span className="text-xs text-slate-500 w-6">[{i}]</span>
                      <code className="text-xs text-slate-400 font-mono break-all">{hash}</code>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function SnapshotExplorer({
  onSelectSnapshot,
  onVerify,
  className = '',
}: SnapshotExplorerProps) {
  const {
    snapshots,
    isLoading,
    selectedSnapshot,
    setSelectedSnapshot,
    fetchSnapshots,
    verifySnapshot,
  } = useSnapshots();
  
  const [filter, setFilter] = useState<SnapshotFilter>({});
  const [showDetail, setShowDetail] = useState(false);
  
  // Load snapshots on filter change
  useEffect(() => {
    fetchSnapshots(filter);
  }, [filter, fetchSnapshots]);
  
  const handleSelect = (snapshot: UISnapshot) => {
    setSelectedSnapshot(snapshot);
    setShowDetail(true);
    onSelectSnapshot?.(snapshot);
  };
  
  const handleVerify = async (snapshot: UISnapshot) => {
    await verifySnapshot(snapshot.id);
    onVerify?.(snapshot);
  };
  
  return (
    <div className={`flex flex-col h-full ${className}`}>
      {/* Header */}
      <div className="mb-4">
        <h2 className="text-xl font-bold text-white flex items-center gap-2 mb-2">
          <span className="text-2xl">📸</span>
          Snapshot Explorer
        </h2>
        <p className="text-sm text-slate-400">
          Browse and verify UI state snapshots for compliance auditing
        </p>
      </div>
      
      {/* Filters */}
      <FilterPanel filter={filter} onChange={setFilter} />
      
      {/* Content */}
      <div className="flex-1 mt-4 flex gap-4 min-h-0">
        {/* Snapshot Grid */}
        <div className={`flex-1 overflow-y-auto ${showDetail ? 'hidden lg:block lg:w-1/2' : ''}`}>
          {isLoading ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <svg className="w-8 h-8 animate-spin text-cyan-400 mx-auto mb-2" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                <p className="text-slate-400">Loading snapshots...</p>
              </div>
            </div>
          ) : snapshots.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <p className="text-slate-400 mb-2">No snapshots found</p>
                <p className="text-sm text-slate-500">Try adjusting your filters</p>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              {snapshots.map(snapshot => (
                <SnapshotCard
                  key={snapshot.id}
                  snapshot={snapshot}
                  isSelected={selectedSnapshot?.id === snapshot.id}
                  onSelect={() => handleSelect(snapshot)}
                  onVerify={() => handleVerify(snapshot)}
                />
              ))}
            </div>
          )}
        </div>
        
        {/* Detail Panel */}
        {showDetail && selectedSnapshot && (
          <div className={`${showDetail ? 'w-full lg:w-1/2' : ''}`}>
            <SnapshotDetailPanel
              snapshot={selectedSnapshot}
              onClose={() => {
                setShowDetail(false);
                setSelectedSnapshot(null);
              }}
            />
          </div>
        )}
      </div>
      
      {/* Stats Footer */}
      <div className="mt-4 pt-4 border-t border-slate-700">
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-400">
            {snapshots.length} snapshot{snapshots.length !== 1 ? 's' : ''} found
          </span>
          <div className="flex items-center gap-4">
            <span className="text-green-400">
              {snapshots.filter(s => s.integrityProof.verified).length} verified
            </span>
            <span className="text-yellow-400">
              {snapshots.filter(s => !s.integrityProof.verified).length} pending
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
