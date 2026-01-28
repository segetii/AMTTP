'use client';

/**
 * TransferTracker Component
 * 
 * Real-time cross-chain transfer monitoring
 * 
 * Ground Truth Reference:
 * - Track transfers through all phases
 * - Clear status and progress indicators
 * - Error visibility for troubleshooting
 */

import React from 'react';
import {
  CrossChainTransfer,
  TransferStatus,
  TransferPhase,
  getChainName,
  getBridgeProtocolName,
  getStatusColor,
  formatTransferTime,
} from '@/types/cross-chain';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface TransferTrackerProps {
  transfers: CrossChainTransfer[];
  onTransferSelect?: (transferId: string) => void;
  onRetry?: (transferId: string) => void;
  selectedTransfer?: string;
  maxDisplay?: number;
}

// ═══════════════════════════════════════════════════════════════════════════════
// PHASE INDICATOR
// ═══════════════════════════════════════════════════════════════════════════════

function PhaseIndicator({ phase, progress }: { phase: TransferPhase; progress: number }) {
  const phases = [
    { key: TransferPhase.INITIATED, label: 'Init' },
    { key: TransferPhase.SOURCE_CONFIRMED, label: 'Src' },
    { key: TransferPhase.BRIDGE_PROCESSING, label: 'Bridge' },
    { key: TransferPhase.DESTINATION_PENDING, label: 'Dst' },
    { key: TransferPhase.COMPLETED, label: 'Done' },
  ];
  
  const currentIndex = phases.findIndex(p => p.key === phase);
  
  return (
    <div className="flex items-center gap-1">
      {phases.map((p, idx) => (
        <React.Fragment key={p.key}>
          <div
            className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium
              ${idx < currentIndex 
                ? 'bg-green-600 text-white' 
                : idx === currentIndex 
                  ? 'bg-cyan-600 text-white animate-pulse' 
                  : 'bg-slate-700 text-slate-500'}`}
          >
            {idx < currentIndex ? '✓' : idx + 1}
          </div>
          {idx < phases.length - 1 && (
            <div 
              className={`w-4 h-0.5 ${idx < currentIndex ? 'bg-green-600' : 'bg-slate-700'}`}
            />
          )}
        </React.Fragment>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TRANSFER ROW
// ═══════════════════════════════════════════════════════════════════════════════

function TransferRow({
  transfer,
  isSelected,
  onSelect,
  onRetry,
}: {
  transfer: CrossChainTransfer;
  isSelected: boolean;
  onSelect: () => void;
  onRetry?: () => void;
}) {
  const color = getStatusColor(transfer.status);
  const statusColors: Record<string, string> = {
    green: 'text-green-400 bg-green-900/30 border-green-600/30',
    yellow: 'text-yellow-400 bg-yellow-900/30 border-yellow-600/30',
    blue: 'text-blue-400 bg-blue-900/30 border-blue-600/30',
    cyan: 'text-cyan-400 bg-cyan-900/30 border-cyan-600/30',
    orange: 'text-orange-400 bg-orange-900/30 border-orange-600/30',
    red: 'text-red-400 bg-red-900/30 border-red-600/30',
    gray: 'text-gray-400 bg-gray-900/30 border-gray-600/30',
  };
  
  const timeElapsed = Math.floor((Date.now() - transfer.initiatedAt) / 1000);
  
  return (
    <div
      onClick={onSelect}
      className={`bg-slate-800/50 rounded-lg border p-4 cursor-pointer transition-all
                ${isSelected 
                  ? 'border-cyan-500 bg-slate-800' 
                  : 'border-slate-700 hover:border-slate-600'}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-white">
              {getChainName(transfer.sourceChain)}
            </span>
            <span className="text-slate-500">→</span>
            <span className="text-sm font-medium text-white">
              {getChainName(transfer.destinationChain)}
            </span>
          </div>
          <span className="text-xs text-slate-500">
            via {getBridgeProtocolName(transfer.bridge)}
          </span>
        </div>
        <span className={`px-2 py-0.5 text-xs rounded border ${statusColors[color]}`}>
          {transfer.status}
        </span>
      </div>
      
      {/* Amount & Asset */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <p className="text-lg font-bold text-white">
            {transfer.amount.toLocaleString()} {transfer.asset}
          </p>
          <p className="text-xs text-slate-500">
            Fee: {transfer.bridgeFee.toFixed(2)} {transfer.asset}
          </p>
        </div>
        
        {/* Time */}
        <div className="text-right">
          <p className="text-sm text-slate-300">
            {transfer.status === TransferStatus.COMPLETED 
              ? formatTransferTime(Math.floor((transfer.completedAt! - transfer.initiatedAt) / 1000))
              : formatTransferTime(timeElapsed)}
          </p>
          <p className="text-xs text-slate-500">
            {transfer.status === TransferStatus.COMPLETED ? 'Completed in' : 'Elapsed'}
          </p>
        </div>
      </div>
      
      {/* Progress */}
      <div className="mb-3">
        <div className="flex items-center justify-between mb-1">
          <PhaseIndicator phase={transfer.phase} progress={transfer.progress} />
          <span className="text-xs text-slate-500">{transfer.progress}%</span>
        </div>
        <div className="h-1.5 bg-slate-900 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all ${
              transfer.status === TransferStatus.STUCK ? 'bg-orange-500' :
              transfer.status === TransferStatus.FAILED ? 'bg-red-500' :
              transfer.status === TransferStatus.COMPLETED ? 'bg-green-500' :
              'bg-cyan-500'
            }`}
            style={{ width: `${transfer.progress}%` }}
          />
        </div>
      </div>
      
      {/* Error / Warning */}
      {transfer.errorMessage && (
        <div className="bg-red-900/20 border border-red-600/30 rounded p-2 mb-3 flex items-center justify-between">
          <p className="text-xs text-red-400">{transfer.errorMessage}</p>
          {onRetry && transfer.status === TransferStatus.STUCK && (
            <button
              onClick={(e) => { e.stopPropagation(); onRetry(); }}
              className="px-2 py-1 text-xs bg-red-600/20 text-red-400 rounded hover:bg-red-600/30"
            >
              Retry ({transfer.retryCount})
            </button>
          )}
        </div>
      )}
      
      {/* Policy Flags */}
      {transfer.policyFlags.length > 0 && (
        <div className="flex items-center gap-2 mb-3">
          {transfer.policyFlags.map((flag) => (
            <span
              key={flag}
              className="px-2 py-0.5 text-xs bg-amber-900/30 text-amber-400 rounded border border-amber-600/30"
            >
              ⚠ {flag}
            </span>
          ))}
        </div>
      )}
      
      {/* Addresses & Tx Hash */}
      <div className="text-xs text-slate-500 space-y-1">
        <div className="flex items-center justify-between">
          <span>From: {transfer.sender.slice(0, 8)}...{transfer.sender.slice(-6)}</span>
          <span>To: {transfer.recipient.slice(0, 8)}...{transfer.recipient.slice(-6)}</span>
        </div>
        <div className="flex items-center justify-between">
          <span>Src Tx: {transfer.sourceTxHash.slice(0, 10)}...</span>
          {transfer.destinationTxHash && (
            <span>Dst Tx: {transfer.destinationTxHash.slice(0, 10)}...</span>
          )}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function TransferTracker({
  transfers,
  onTransferSelect,
  onRetry,
  selectedTransfer,
  maxDisplay = 10,
}: TransferTrackerProps) {
  // Sort by status priority and time
  const sortedTransfers = [...transfers].sort((a, b) => {
    const statusPriority: Record<TransferStatus, number> = {
      [TransferStatus.STUCK]: 0,
      [TransferStatus.PROCESSING]: 1,
      [TransferStatus.CONFIRMING]: 2,
      [TransferStatus.PENDING]: 3,
      [TransferStatus.FAILED]: 4,
      [TransferStatus.COMPLETED]: 5,
      [TransferStatus.CANCELLED]: 6,
    };
    
    if (statusPriority[a.status] !== statusPriority[b.status]) {
      return statusPriority[a.status] - statusPriority[b.status];
    }
    return b.initiatedAt - a.initiatedAt;
  });
  
  const displayTransfers = sortedTransfers.slice(0, maxDisplay);
  
  // Stats
  const pending = transfers.filter(t => 
    [TransferStatus.PENDING, TransferStatus.PROCESSING, TransferStatus.CONFIRMING].includes(t.status)
  ).length;
  const stuck = transfers.filter(t => t.status === TransferStatus.STUCK).length;
  const completed = transfers.filter(t => t.status === TransferStatus.COMPLETED).length;
  
  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium text-white">Transfer Activity</h2>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-cyan-400">{pending} in progress</span>
          {stuck > 0 && <span className="text-orange-400">{stuck} stuck</span>}
          <span className="text-slate-400">{completed} completed</span>
        </div>
      </div>
      
      {/* Transfer List */}
      {displayTransfers.length === 0 ? (
        <div className="bg-slate-800/30 rounded-lg border border-slate-700 p-8 text-center">
          <svg className="w-12 h-12 text-slate-600 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
          </svg>
          <h3 className="text-lg font-medium text-slate-300 mb-2">No Transfers</h3>
          <p className="text-sm text-slate-500">
            Cross-chain transfers will appear here
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {displayTransfers.map((transfer) => (
            <TransferRow
              key={transfer.id}
              transfer={transfer}
              isSelected={selectedTransfer === transfer.id}
              onSelect={() => onTransferSelect?.(transfer.id)}
              onRetry={onRetry ? () => onRetry(transfer.id) : undefined}
            />
          ))}
        </div>
      )}
      
      {/* View more link */}
      {transfers.length > maxDisplay && (
        <div className="text-center">
          <button className="text-sm text-cyan-400 hover:text-cyan-300">
            View all {transfers.length} transfers →
          </button>
        </div>
      )}
    </div>
  );
}
