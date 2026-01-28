'use client';

/**
 * BridgeStatusPanel Component
 * 
 * Status overview of cross-chain bridges
 * 
 * Ground Truth Reference:
 * - Bridge status affects transfer availability
 * - Clear capacity and congestion indicators
 */

import React from 'react';
import {
  Bridge,
  BridgeStatus,
  BridgeProtocol,
  getChainName,
  getBridgeProtocolName,
  getStatusColor,
} from '@/types/cross-chain';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface BridgeStatusPanelProps {
  bridges: Bridge[];
  onBridgeSelect?: (bridgeId: string) => void;
  selectedBridge?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// BRIDGE ROW
// ═══════════════════════════════════════════════════════════════════════════════

function BridgeRow({
  bridge,
  isSelected,
  onSelect,
}: {
  bridge: Bridge;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const color = getStatusColor(bridge.status);
  const statusColors: Record<string, string> = {
    green: 'text-green-400 bg-green-900/30',
    yellow: 'text-yellow-400 bg-yellow-900/30',
    orange: 'text-orange-400 bg-orange-900/30',
    red: 'text-red-400 bg-red-900/30',
    gray: 'text-gray-400 bg-gray-900/30',
  };
  
  const utilizationPercent = 100 - (bridge.limits.remainingDailyLimit / bridge.limits.dailyLimit * 100);
  const utilizationColor = utilizationPercent > 80 ? 'bg-red-500' : 
                           utilizationPercent > 50 ? 'bg-yellow-500' : 'bg-green-500';
  
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
          <div className="text-2xl">🌉</div>
          <div>
            <h3 className="font-medium text-white">{getBridgeProtocolName(bridge.protocol)}</h3>
            <p className="text-xs text-slate-400">
              {getChainName(bridge.sourceChain)} → {getChainName(bridge.destinationChain)}
            </p>
          </div>
        </div>
        <span className={`px-2 py-1 text-xs rounded ${statusColors[color]}`}>
          {bridge.status}
        </span>
      </div>
      
      {/* Stats Row */}
      <div className="grid grid-cols-4 gap-3 mb-3 text-center">
        <div className="bg-slate-900/50 rounded p-2">
          <p className="text-sm font-medium text-white">
            ${(bridge.stats.totalVolume24h / 1000000).toFixed(1)}M
          </p>
          <p className="text-xs text-slate-500">24h Vol</p>
        </div>
        <div className="bg-slate-900/50 rounded p-2">
          <p className="text-sm font-medium text-white">
            {bridge.stats.totalTransactions24h.toLocaleString()}
          </p>
          <p className="text-xs text-slate-500">24h Txns</p>
        </div>
        <div className="bg-slate-900/50 rounded p-2">
          <p className="text-sm font-medium text-white">
            {Math.floor(bridge.stats.avgTransferTime / 60)}m
          </p>
          <p className="text-xs text-slate-500">Avg Time</p>
        </div>
        <div className="bg-slate-900/50 rounded p-2">
          <p className="text-sm font-medium text-green-400">
            {bridge.stats.successRate}%
          </p>
          <p className="text-xs text-slate-500">Success</p>
        </div>
      </div>
      
      {/* Capacity Bar */}
      <div className="mb-2">
        <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
          <span>Daily Capacity</span>
          <span>
            ${((bridge.limits.dailyLimit - bridge.limits.remainingDailyLimit) / 1000000).toFixed(1)}M / 
            ${(bridge.limits.dailyLimit / 1000000).toFixed(1)}M
          </span>
        </div>
        <div className="h-2 bg-slate-900 rounded-full overflow-hidden">
          <div
            className={`h-full ${utilizationColor} transition-all`}
            style={{ width: `${utilizationPercent}%` }}
          />
        </div>
      </div>
      
      {/* Pending indicator */}
      {bridge.stats.pendingTransactions > 0 && (
        <div className="flex items-center justify-between text-xs">
          <span className="text-slate-500">Pending</span>
          <span className={`${bridge.stats.pendingTransactions > 20 ? 'text-orange-400' : 'text-slate-300'}`}>
            {bridge.stats.pendingTransactions} transactions
          </span>
        </div>
      )}
      
      {/* Supported Assets */}
      <div className="mt-3 pt-3 border-t border-slate-700">
        <p className="text-xs text-slate-500 mb-1">Supported Assets</p>
        <div className="flex flex-wrap gap-1">
          {bridge.supportedAssets.map((asset) => (
            <span
              key={asset}
              className="px-2 py-0.5 bg-slate-700 text-slate-300 text-xs rounded"
            >
              {asset}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function BridgeStatusPanel({
  bridges,
  onBridgeSelect,
  selectedBridge,
}: BridgeStatusPanelProps) {
  // Summary stats
  const operationalCount = bridges.filter(b => b.status === BridgeStatus.OPERATIONAL).length;
  const congestedCount = bridges.filter(b => b.status === BridgeStatus.CONGESTED).length;
  const offlineCount = bridges.filter(b => [BridgeStatus.PAUSED, BridgeStatus.OFFLINE].includes(b.status)).length;
  const totalPending = bridges.reduce((sum, b) => sum + b.stats.pendingTransactions, 0);
  
  return (
    <div className="space-y-4">
      {/* Summary Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium text-white">Bridge Status</h2>
        <div className="flex items-center gap-4 text-sm">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 bg-green-500 rounded-full" />
            <span className="text-slate-400">{operationalCount} Operational</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 bg-yellow-500 rounded-full" />
            <span className="text-slate-400">{congestedCount} Congested</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 bg-red-500 rounded-full" />
            <span className="text-slate-400">{offlineCount} Offline</span>
          </span>
          {totalPending > 0 && (
            <span className="text-orange-400">
              {totalPending} pending
            </span>
          )}
        </div>
      </div>
      
      {/* Bridge Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {bridges.map((bridge) => (
          <BridgeRow
            key={bridge.id}
            bridge={bridge}
            isSelected={selectedBridge === bridge.id}
            onSelect={() => onBridgeSelect?.(bridge.id)}
          />
        ))}
      </div>
    </div>
  );
}
