'use client';

/**
 * ChainHealthGrid Component
 * 
 * Overview of all monitored chains health status
 * 
 * Ground Truth Reference:
 * - Infrastructure status must be visible
 * - Health affects transfer routing decisions
 */

import React from 'react';
import {
  ChainConfig,
  ChainStatus,
  NetworkHealth,
  getChainName,
  getChainColor,
  getStatusColor,
} from '@/types/cross-chain';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface ChainHealthGridProps {
  chains: ChainConfig[];
  networkHealth: NetworkHealth[];
  onChainSelect?: (chainId: string) => void;
  selectedChain?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// CHAIN CARD
// ═══════════════════════════════════════════════════════════════════════════════

function ChainCard({
  chain,
  health,
  isSelected,
  onSelect,
}: {
  chain: ChainConfig;
  health?: NetworkHealth;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const statusColorMap: Record<string, string> = {
    green: 'bg-green-500',
    yellow: 'bg-yellow-500',
    orange: 'bg-orange-500',
    red: 'bg-red-500',
    gray: 'bg-gray-500',
  };
  
  const statusBgMap: Record<string, string> = {
    green: 'bg-green-900/20 border-green-600/30',
    yellow: 'bg-yellow-900/20 border-yellow-600/30',
    orange: 'bg-orange-900/20 border-orange-600/30',
    red: 'bg-red-900/20 border-red-600/30',
    gray: 'bg-gray-900/20 border-gray-600/30',
  };
  
  const color = getStatusColor(chain.status);
  
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
        <div className="flex items-center gap-2">
          <div 
            className="w-8 h-8 rounded-full flex items-center justify-center text-white font-bold text-sm"
            style={{ backgroundColor: chain.color }}
          >
            {chain.name.substring(0, 2).toUpperCase()}
          </div>
          <div>
            <h3 className="font-medium text-white">{chain.name}</h3>
            <p className="text-xs text-slate-500">Chain ID: {chain.chainId}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${statusColorMap[color]} animate-pulse`} />
          <span className={`px-2 py-0.5 text-xs rounded border ${statusBgMap[color]}`}>
            {chain.status}
          </span>
        </div>
      </div>
      
      {/* Metrics */}
      {health && (
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="bg-slate-900/50 rounded p-2">
            <p className="text-sm font-medium text-white">{health.rpcLatency}ms</p>
            <p className="text-xs text-slate-500">Latency</p>
          </div>
          <div className="bg-slate-900/50 rounded p-2">
            <p className="text-sm font-medium text-white">{health.gasPriceGwei}</p>
            <p className="text-xs text-slate-500">Gas (Gwei)</p>
          </div>
          <div className="bg-slate-900/50 rounded p-2">
            <p className="text-sm font-medium text-white">{chain.blockTime}s</p>
            <p className="text-xs text-slate-500">Block Time</p>
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function ChainHealthGrid({
  chains,
  networkHealth,
  onChainSelect,
  selectedChain,
}: ChainHealthGridProps) {
  // Summary stats
  const healthyCount = chains.filter(c => c.status === ChainStatus.HEALTHY).length;
  const degradedCount = chains.filter(c => c.status === ChainStatus.DEGRADED).length;
  const downCount = chains.filter(c => [ChainStatus.DOWN, ChainStatus.MAINTENANCE].includes(c.status)).length;
  
  return (
    <div className="space-y-4">
      {/* Summary Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium text-white">Network Health</h2>
        <div className="flex items-center gap-4 text-sm">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 bg-green-500 rounded-full" />
            <span className="text-slate-400">{healthyCount} Healthy</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 bg-yellow-500 rounded-full" />
            <span className="text-slate-400">{degradedCount} Degraded</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 bg-red-500 rounded-full" />
            <span className="text-slate-400">{downCount} Down</span>
          </span>
        </div>
      </div>
      
      {/* Chain Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
        {chains.map((chain) => (
          <ChainCard
            key={chain.id}
            chain={chain}
            health={networkHealth.find(h => h.chain === chain.id)}
            isSelected={selectedChain === chain.id}
            onSelect={() => onChainSelect?.(chain.id)}
          />
        ))}
      </div>
    </div>
  );
}
