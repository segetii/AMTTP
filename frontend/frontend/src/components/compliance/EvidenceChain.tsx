'use client';

/**
 * Evidence Chain Component
 * 
 * Sprint 11: Compliance Reporting & Export System
 * 
 * Ground Truth Reference:
 * - Evidence linking for complete audit trails
 * - Visual evidence chain representation
 * - Cross-reference between snapshots, transactions, and audit events
 */

import React, { useState, useEffect } from 'react';
import {
  Evidence,
  EvidenceType,
  EvidenceStatus,
  EvidenceLink,
  getEvidenceTypeLabel,
  getEvidenceStatusColor,
  truncateHash,
  formatSnapshotDate,
} from '@/types/compliance-report';
import { useEvidence } from '@/lib/compliance-report-service';

// ═══════════════════════════════════════════════════════════════════════════════
// INTERFACES
// ═══════════════════════════════════════════════════════════════════════════════

interface EvidenceChainProps {
  focusId?: string;
  focusType?: 'snapshot' | 'transaction' | 'audit';
  onSelectEvidence?: (evidence: Evidence) => void;
  className?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// EVIDENCE TYPE ICON
// ═══════════════════════════════════════════════════════════════════════════════

function EvidenceTypeIcon({ type }: { type: EvidenceType }) {
  const icons: Record<EvidenceType, string> = {
    [EvidenceType.UI_SNAPSHOT]: '📸',
    [EvidenceType.TRANSACTION]: '💸',
    [EvidenceType.SIGNATURE]: '✍️',
    [EvidenceType.AUDIT_LOG]: '📋',
    [EvidenceType.DOCUMENT]: '📄',
    [EvidenceType.CHAIN_DATA]: '⛓️',
    [EvidenceType.USER_INPUT]: '⌨️',
    [EvidenceType.SYSTEM_EVENT]: '⚙️',
  };
  
  return <span className="text-lg">{icons[type]}</span>;
}

// ═══════════════════════════════════════════════════════════════════════════════
// EVIDENCE CARD
// ═══════════════════════════════════════════════════════════════════════════════

function EvidenceCard({
  evidence,
  isSelected,
  onSelect,
}: {
  evidence: Evidence;
  isSelected: boolean;
  onSelect: () => void;
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
        <div className="flex items-center gap-3">
          <EvidenceTypeIcon type={evidence.type} />
          <div>
            <h4 className="font-medium text-white">{evidence.title}</h4>
            <p className="text-xs text-slate-400">{getEvidenceTypeLabel(evidence.type)}</p>
          </div>
        </div>
        <div className={`px-2 py-1 rounded text-xs font-medium ${
          evidence.status === EvidenceStatus.VERIFIED
            ? 'bg-green-900/50 text-green-400 border border-green-600/30'
            : evidence.status === EvidenceStatus.PENDING
            ? 'bg-yellow-900/50 text-yellow-400 border border-yellow-600/30'
            : evidence.status === EvidenceStatus.DISPUTED
            ? 'bg-orange-900/50 text-orange-400 border border-orange-600/30'
            : 'bg-red-900/50 text-red-400 border border-red-600/30'
        }`}>
          {evidence.status === EvidenceStatus.VERIFIED && '✓ '}
          {evidence.status}
        </div>
      </div>
      
      {/* Description */}
      <p className="text-sm text-slate-400 mb-3">{evidence.description}</p>
      
      {/* Metadata */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500 mb-3">
        <span>{formatSnapshotDate(evidence.timestamp)}</span>
        <span>By: {evidence.submittedBy}</span>
      </div>
      
      {/* Hash */}
      <div className="flex items-center gap-2 mb-3">
        <span className="text-xs text-slate-500">Hash:</span>
        <code className="text-xs text-cyan-400 font-mono">{truncateHash(evidence.contentHash)}</code>
      </div>
      
      {/* Relations */}
      <div className="flex flex-wrap gap-2">
        {evidence.relatedSnapshots.length > 0 && (
          <span className="px-2 py-0.5 bg-blue-900/50 text-blue-400 rounded text-xs">
            📸 {evidence.relatedSnapshots.length} snapshot{evidence.relatedSnapshots.length !== 1 ? 's' : ''}
          </span>
        )}
        {evidence.relatedTransactions.length > 0 && (
          <span className="px-2 py-0.5 bg-green-900/50 text-green-400 rounded text-xs">
            💸 {evidence.relatedTransactions.length} transaction{evidence.relatedTransactions.length !== 1 ? 's' : ''}
          </span>
        )}
        {evidence.relatedAuditEvents.length > 0 && (
          <span className="px-2 py-0.5 bg-purple-900/50 text-purple-400 rounded text-xs">
            📋 {evidence.relatedAuditEvents.length} audit event{evidence.relatedAuditEvents.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>
      
      {/* On-Chain Reference */}
      {evidence.onChainReference && (
        <div className="mt-3 pt-3 border-t border-slate-700">
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500">On-Chain:</span>
            <code className="text-xs text-green-400 font-mono">{truncateHash(evidence.onChainReference)}</code>
            {evidence.blockNumber && (
              <span className="text-xs text-slate-500">Block #{evidence.blockNumber.toLocaleString()}</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// EVIDENCE DETAIL PANEL
// ═══════════════════════════════════════════════════════════════════════════════

function EvidenceDetailPanel({
  evidence,
  onClose,
}: {
  evidence: Evidence;
  onClose: () => void;
}) {
  return (
    <div className="h-full flex flex-col bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-slate-700 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <EvidenceTypeIcon type={evidence.type} />
          <div>
            <h3 className="font-semibold text-white">{evidence.title}</h3>
            <p className="text-xs text-slate-400">{getEvidenceTypeLabel(evidence.type)}</p>
          </div>
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
      
      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Status */}
        <div className={`p-4 rounded border ${
          evidence.status === EvidenceStatus.VERIFIED
            ? 'bg-green-900/20 border-green-600/30'
            : evidence.status === EvidenceStatus.PENDING
            ? 'bg-yellow-900/20 border-yellow-600/30'
            : evidence.status === EvidenceStatus.DISPUTED
            ? 'bg-orange-900/20 border-orange-600/30'
            : 'bg-red-900/20 border-red-600/30'
        }`}>
          <div className="flex items-center gap-2 mb-2">
            <span className={`text-sm font-medium ${getEvidenceStatusColor(evidence.status)}`}>
              Status: {evidence.status}
            </span>
          </div>
          {evidence.verifiedBy && (
            <p className="text-xs text-slate-400">
              Verified by {evidence.verifiedBy} on {formatSnapshotDate(evidence.verifiedAt!)}
            </p>
          )}
        </div>
        
        {/* Description */}
        <div className="p-4 bg-slate-900 rounded border border-slate-700">
          <h4 className="text-sm font-medium text-white mb-2">Description</h4>
          <p className="text-sm text-slate-400">{evidence.description}</p>
        </div>
        
        {/* Timestamps */}
        <div className="p-4 bg-slate-900 rounded border border-slate-700">
          <h4 className="text-sm font-medium text-white mb-3">Timeline</h4>
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-sm text-slate-400">Occurred</span>
              <span className="text-sm text-white">{formatSnapshotDate(evidence.timestamp)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-slate-400">Submitted</span>
              <span className="text-sm text-white">{formatSnapshotDate(evidence.submittedAt)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-slate-400">Submitted By</span>
              <span className="text-sm text-white">{evidence.submittedBy}</span>
            </div>
            {evidence.verifiedAt && (
              <div className="flex justify-between">
                <span className="text-sm text-slate-400">Verified</span>
                <span className="text-sm text-white">{formatSnapshotDate(evidence.verifiedAt)}</span>
              </div>
            )}
          </div>
        </div>
        
        {/* Content Hash */}
        <div className="p-4 bg-slate-900 rounded border border-slate-700">
          <h4 className="text-sm font-medium text-white mb-3">Content Hash</h4>
          <code className="text-xs text-cyan-400 font-mono break-all">{evidence.contentHash}</code>
        </div>
        
        {/* On-Chain Reference */}
        {evidence.onChainReference && (
          <div className="p-4 bg-slate-900 rounded border border-slate-700">
            <h4 className="text-sm font-medium text-white mb-3">On-Chain Reference</h4>
            <div className="space-y-2">
              <div>
                <p className="text-xs text-slate-500 mb-1">Transaction Hash</p>
                <code className="text-xs text-green-400 font-mono break-all">{evidence.onChainReference}</code>
              </div>
              {evidence.blockNumber && (
                <div className="flex justify-between">
                  <span className="text-sm text-slate-400">Block Number</span>
                  <span className="text-sm text-white">{evidence.blockNumber.toLocaleString()}</span>
                </div>
              )}
            </div>
          </div>
        )}
        
        {/* Related Items */}
        <div className="p-4 bg-slate-900 rounded border border-slate-700">
          <h4 className="text-sm font-medium text-white mb-3">Related Items</h4>
          <div className="space-y-3">
            {evidence.relatedSnapshots.length > 0 && (
              <div>
                <p className="text-xs text-slate-500 mb-1">Snapshots</p>
                <div className="flex flex-wrap gap-1">
                  {evidence.relatedSnapshots.map(id => (
                    <code key={id} className="px-2 py-0.5 bg-blue-900/50 text-blue-400 rounded text-xs font-mono">
                      {id}
                    </code>
                  ))}
                </div>
              </div>
            )}
            {evidence.relatedTransactions.length > 0 && (
              <div>
                <p className="text-xs text-slate-500 mb-1">Transactions</p>
                <div className="flex flex-wrap gap-1">
                  {evidence.relatedTransactions.map(id => (
                    <code key={id} className="px-2 py-0.5 bg-green-900/50 text-green-400 rounded text-xs font-mono">
                      {id}
                    </code>
                  ))}
                </div>
              </div>
            )}
            {evidence.relatedAuditEvents.length > 0 && (
              <div>
                <p className="text-xs text-slate-500 mb-1">Audit Events</p>
                <div className="flex flex-wrap gap-1">
                  {evidence.relatedAuditEvents.map(id => (
                    <code key={id} className="px-2 py-0.5 bg-purple-900/50 text-purple-400 rounded text-xs font-mono">
                      {id}
                    </code>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// EVIDENCE CHAIN VISUALIZATION
// ═══════════════════════════════════════════════════════════════════════════════

function ChainVisualization({ evidence }: { evidence: Evidence[] }) {
  const sorted = [...evidence].sort((a, b) => 
    new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  );
  
  return (
    <div className="relative">
      {/* Timeline line */}
      <div className="absolute left-6 top-0 bottom-0 w-0.5 bg-slate-700" />
      
      <div className="space-y-4">
        {sorted.map((ev, index) => (
          <div key={ev.id} className="relative flex gap-4">
            {/* Timeline node */}
            <div className={`relative z-10 w-12 h-12 flex items-center justify-center rounded-full border-2 ${
              ev.status === EvidenceStatus.VERIFIED
                ? 'bg-green-900/50 border-green-500'
                : ev.status === EvidenceStatus.PENDING
                ? 'bg-yellow-900/50 border-yellow-500'
                : 'bg-slate-800 border-slate-600'
            }`}>
              <EvidenceTypeIcon type={ev.type} />
            </div>
            
            {/* Content */}
            <div className="flex-1 pb-4">
              <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700">
                <div className="flex items-start justify-between mb-1">
                  <span className="text-sm font-medium text-white">{ev.title}</span>
                  <span className="text-xs text-slate-500">{formatSnapshotDate(ev.timestamp)}</span>
                </div>
                <p className="text-xs text-slate-400">{ev.description}</p>
              </div>
              
              {/* Connection to next */}
              {index < sorted.length - 1 && (
                <div className="flex items-center gap-2 mt-2 ml-4">
                  <svg className="w-4 h-4 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                  <span className="text-xs text-slate-500">leads to</span>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function EvidenceChain({
  focusId,
  focusType,
  onSelectEvidence,
  className = '',
}: EvidenceChainProps) {
  const {
    evidence,
    isLoading,
    fetchEvidence,
    getEvidenceChain,
  } = useEvidence();
  
  const [selectedEvidence, setSelectedEvidence] = useState<Evidence | null>(null);
  const [viewMode, setViewMode] = useState<'list' | 'chain'>('list');
  const [filterType, setFilterType] = useState<EvidenceType | 'ALL'>('ALL');
  const [filterStatus, setFilterStatus] = useState<EvidenceStatus | 'ALL'>('ALL');
  
  // Load evidence
  useEffect(() => {
    fetchEvidence(focusId, focusType);
  }, [fetchEvidence, focusId, focusType]);
  
  // Apply filters
  const filteredEvidence = evidence.filter(ev => {
    if (filterType !== 'ALL' && ev.type !== filterType) return false;
    if (filterStatus !== 'ALL' && ev.status !== filterStatus) return false;
    return true;
  });
  
  const handleSelect = (ev: Evidence) => {
    setSelectedEvidence(ev);
    onSelectEvidence?.(ev);
  };
  
  return (
    <div className={`flex flex-col h-full ${className}`}>
      {/* Header */}
      <div className="mb-4">
        <h2 className="text-xl font-bold text-white flex items-center gap-2 mb-2">
          <span className="text-2xl">🔗</span>
          Evidence Chain
        </h2>
        <p className="text-sm text-slate-400">
          Linked evidence trail for complete audit reconstruction
        </p>
      </div>
      
      {/* Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        {/* Filters */}
        <div className="flex gap-3">
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value as EvidenceType | 'ALL')}
            className="px-3 py-2 bg-slate-800 border border-slate-700 rounded text-sm text-white"
          >
            <option value="ALL">All Types</option>
            {Object.values(EvidenceType).map(type => (
              <option key={type} value={type}>{getEvidenceTypeLabel(type)}</option>
            ))}
          </select>
          
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value as EvidenceStatus | 'ALL')}
            className="px-3 py-2 bg-slate-800 border border-slate-700 rounded text-sm text-white"
          >
            <option value="ALL">All Status</option>
            {Object.values(EvidenceStatus).map(status => (
              <option key={status} value={status}>{status}</option>
            ))}
          </select>
        </div>
        
        {/* View Toggle */}
        <div className="flex bg-slate-800 rounded-lg p-1">
          <button
            onClick={() => setViewMode('list')}
            className={`px-3 py-1.5 text-sm rounded ${
              viewMode === 'list'
                ? 'bg-cyan-600 text-white'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            List
          </button>
          <button
            onClick={() => setViewMode('chain')}
            className={`px-3 py-1.5 text-sm rounded ${
              viewMode === 'chain'
                ? 'bg-cyan-600 text-white'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            Timeline
          </button>
        </div>
      </div>
      
      {/* Content */}
      <div className="flex-1 flex gap-4 min-h-0">
        {/* Evidence List/Chain */}
        <div className={`flex-1 overflow-y-auto ${selectedEvidence ? 'hidden lg:block lg:w-1/2' : ''}`}>
          {isLoading ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <svg className="w-8 h-8 animate-spin text-cyan-400 mx-auto mb-2" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                <p className="text-slate-400">Loading evidence...</p>
              </div>
            </div>
          ) : filteredEvidence.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <p className="text-slate-400 mb-2">No evidence found</p>
                <p className="text-sm text-slate-500">Try adjusting your filters</p>
              </div>
            </div>
          ) : viewMode === 'list' ? (
            <div className="space-y-4">
              {filteredEvidence.map(ev => (
                <EvidenceCard
                  key={ev.id}
                  evidence={ev}
                  isSelected={selectedEvidence?.id === ev.id}
                  onSelect={() => handleSelect(ev)}
                />
              ))}
            </div>
          ) : (
            <ChainVisualization evidence={filteredEvidence} />
          )}
        </div>
        
        {/* Detail Panel */}
        {selectedEvidence && (
          <div className={`${selectedEvidence ? 'w-full lg:w-1/2' : ''}`}>
            <EvidenceDetailPanel
              evidence={selectedEvidence}
              onClose={() => setSelectedEvidence(null)}
            />
          </div>
        )}
      </div>
      
      {/* Stats Footer */}
      <div className="mt-4 pt-4 border-t border-slate-700">
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-400">
            {filteredEvidence.length} evidence item{filteredEvidence.length !== 1 ? 's' : ''}
          </span>
          <div className="flex items-center gap-4">
            <span className="text-green-400">
              {filteredEvidence.filter(e => e.status === EvidenceStatus.VERIFIED).length} verified
            </span>
            <span className="text-yellow-400">
              {filteredEvidence.filter(e => e.status === EvidenceStatus.PENDING).length} pending
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
