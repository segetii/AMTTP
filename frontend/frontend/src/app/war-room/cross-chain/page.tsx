'use client';

/**
 * War Room - Cross-Chain Dashboard
 * 
 * Sprint 8: Cross-Chain Dashboard
 * 
 * Ground Truth Reference:
 * - Unified view of all cross-chain activity
 * - Network health monitoring
 * - Bridge status and capacity
 * - Transfer tracking and troubleshooting
 */

import React, { useState, useEffect } from 'react';
import { useCrossChain } from '@/lib/cross-chain-service';
import {
  ChainHealthGrid,
  BridgeStatusPanel,
  TransferTracker,
} from '@/components/cross-chain';
import {
  Chain,
  BridgeProtocol,
  CrossChainAnalytics,
  AlertLevel,
} from '@/types/cross-chain';

// ═══════════════════════════════════════════════════════════════════════════════
// VIEW TABS
// ═══════════════════════════════════════════════════════════════════════════════

type ViewTab = 'overview' | 'bridges' | 'transfers';

// ═══════════════════════════════════════════════════════════════════════════════
// ALERT BANNER
// ═══════════════════════════════════════════════════════════════════════════════

function AlertBanner({
  alerts,
  onAcknowledge,
}: {
  alerts: Array<{ id: string; level: AlertLevel; title: string; message: string; chain: Chain; acknowledged?: boolean }>;
  onAcknowledge: (id: string) => void;
}) {
  const unacknowledged = alerts.filter(a => !a.acknowledged);
  
  if (unacknowledged.length === 0) return null;
  
  const alertColors: Record<AlertLevel, string> = {
    [AlertLevel.CRITICAL]: 'bg-red-900/50 border-red-600/50 text-red-300',
    [AlertLevel.WARNING]: 'bg-yellow-900/50 border-yellow-600/50 text-yellow-300',
    [AlertLevel.INFO]: 'bg-blue-900/50 border-blue-600/50 text-blue-300',
    [AlertLevel.NONE]: 'bg-background/50 border-borderSubtle/50 text-slate-300',
  };
  
  return (
    <div className="space-y-2 mb-4">
      {unacknowledged.map((alert) => (
        <div
          key={alert.id}
          className={`rounded-lg border p-3 flex items-center justify-between ${alertColors[alert.level]}`}
        >
          <div className="flex items-center gap-3">
            <span className="text-lg">
              {alert.level === AlertLevel.CRITICAL ? '🚨' : 
               alert.level === AlertLevel.WARNING ? '⚠️' : 'ℹ️'}
            </span>
            <div>
              <h4 className="font-medium">{alert.title}</h4>
              <p className="text-sm opacity-80">{alert.message}</p>
            </div>
          </div>
          <button
            onClick={() => onAcknowledge(alert.id)}
            className="px-3 py-1 text-sm bg-surface/50 rounded hover:bg-slate-700/50"
          >
            Dismiss
          </button>
        </div>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// ANALYTICS SUMMARY
// ═══════════════════════════════════════════════════════════════════════════════

function AnalyticsSummary({ analytics }: { analytics: CrossChainAnalytics | null }) {
  if (!analytics) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 animate-pulse">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="bg-surface/50 rounded-lg p-4">
            <div className="h-8 bg-slate-700 rounded mb-2" />
            <div className="h-4 bg-slate-700 rounded w-1/2" />
          </div>
        ))}
      </div>
    );
  }
  
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div className="bg-surface/50 rounded-lg border border-borderSubtle p-4">
        <p className="text-2xl font-bold text-text">
          ${(analytics.totalVolume / 1000000).toFixed(2)}M
        </p>
        <p className="text-sm text-mutedText">24h Volume</p>
      </div>
      <div className="bg-surface/50 rounded-lg border border-borderSubtle p-4">
        <p className="text-2xl font-bold text-cyan-400">
          {analytics.totalTransfers}
        </p>
        <p className="text-sm text-mutedText">Total Transfers</p>
      </div>
      <div className="bg-surface/50 rounded-lg border border-borderSubtle p-4">
        <p className="text-2xl font-bold text-green-400">
          {analytics.successRate.toFixed(1)}%
        </p>
        <p className="text-sm text-mutedText">Success Rate</p>
      </div>
      <div className="bg-surface/50 rounded-lg border border-borderSubtle p-4">
        <p className="text-2xl font-bold text-amber-400">
          {analytics.flaggedTransfers}
        </p>
        <p className="text-sm text-mutedText">Flagged</p>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ═══════════════════════════════════════════════════════════════════════════════

export default function CrossChainPage() {
  const {
    chains,
    bridges,
    transfers,
    networkHealth,
    alerts,
    isLoading,
    getAnalytics,
    acknowledgeAlert,
    retryTransfer,
  } = useCrossChain();
  
  const [activeTab, setActiveTab] = useState<ViewTab>('overview');
  const [analytics, setAnalytics] = useState<CrossChainAnalytics | null>(null);
  const [selectedChain, setSelectedChain] = useState<string | undefined>();
  const [selectedBridge, setSelectedBridge] = useState<string | undefined>();
  const [selectedTransfer, setSelectedTransfer] = useState<string | undefined>();
  
  // Load analytics
  useEffect(() => {
    const loadAnalytics = async () => {
      const now = Date.now();
      const dayAgo = now - 24 * 60 * 60 * 1000;
      const data = await getAnalytics(dayAgo, now);
      setAnalytics(data);
    };
    loadAnalytics();
  }, [getAnalytics, transfers]);
  
  return (
    <div className="space-y-6">
      {/* Header */}
      <header className="mb-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold text-text flex items-center gap-3">
              <span className="text-3xl">🌐</span>
              Cross-Chain Dashboard
            </h1>
            <p className="text-mutedText">Monitor cross-chain transfers and bridge status</p>
          </div>
          
          {/* Live indicator */}
          <div className="flex items-center gap-2 px-3 py-1.5 bg-green-900/30 border border-green-600/30 rounded-lg">
            <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
            <span className="text-sm text-green-400">Live</span>
          </div>
        </div>
        
        {/* Tabs */}
        <div className="flex gap-1 border-b border-borderSubtle pb-4">
          <button
            onClick={() => setActiveTab('overview')}
            className={`px-4 py-2 rounded-t-lg text-sm font-medium transition-colors
              ${activeTab === 'overview'
                ? 'bg-surface text-text'
                : 'text-mutedText hover:text-text'}`}
          >
            📊 Overview
          </button>
          <button
            onClick={() => setActiveTab('bridges')}
            className={`px-4 py-2 rounded-t-lg text-sm font-medium transition-colors
              ${activeTab === 'bridges'
                ? 'bg-surface text-text'
                : 'text-mutedText hover:text-text'}`}
          >
            🌉 Bridges
          </button>
          <button
            onClick={() => setActiveTab('transfers')}
            className={`px-4 py-2 rounded-t-lg text-sm font-medium transition-colors
              ${activeTab === 'transfers'
                ? 'bg-surface text-text'
                : 'text-mutedText hover:text-text'}`}
          >
            📡 Transfers
          </button>
        </div>
      </header>
      
      {/* Alerts */}
      <AlertBanner 
        alerts={alerts.filter(a => !a.acknowledged)} 
        onAcknowledge={acknowledgeAlert} 
      />
      
      {/* Content */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Analytics Summary */}
          <AnalyticsSummary analytics={analytics} />
          
          {/* Chain Health */}
          <ChainHealthGrid
            chains={chains}
            networkHealth={networkHealth}
            onChainSelect={setSelectedChain}
            selectedChain={selectedChain}
          />
          
          {/* Recent Transfers */}
          <TransferTracker
            transfers={transfers}
            onTransferSelect={setSelectedTransfer}
            onRetry={retryTransfer}
            selectedTransfer={selectedTransfer}
            maxDisplay={5}
          />
        </div>
      )}
      
      {activeTab === 'bridges' && (
        <div className="space-y-6">
          <BridgeStatusPanel
            bridges={bridges}
            onBridgeSelect={setSelectedBridge}
            selectedBridge={selectedBridge}
          />
          
          {/* Bridge details panel could go here */}
          {selectedBridge && (
            <div className="bg-surface/30 rounded-lg border border-borderSubtle p-6">
              <h3 className="text-lg font-medium text-text mb-4">Bridge Details</h3>
              {(() => {
                const bridge = bridges.find(b => b.id === selectedBridge);
                if (!bridge) return null;
                
                return (
                  <div className="grid grid-cols-2 gap-6">
                    <div>
                      <h4 className="text-sm font-medium text-mutedText mb-2">Fee Structure</h4>
                      <div className="space-y-1 text-sm">
                        <p className="flex justify-between">
                          <span className="text-mutedText">Base Fee:</span>
                          <span className="text-text">${bridge.fees.baseFee}</span>
                        </p>
                        <p className="flex justify-between">
                          <span className="text-mutedText">Percentage Fee:</span>
                          <span className="text-text">{bridge.fees.percentageFee / 100}%</span>
                        </p>
                        <p className="flex justify-between">
                          <span className="text-mutedText">Est. Gas:</span>
                          <span className="text-text">{bridge.fees.gasEstimate} {bridge.fees.currency}</span>
                        </p>
                      </div>
                    </div>
                    <div>
                      <h4 className="text-sm font-medium text-mutedText mb-2">Limits</h4>
                      <div className="space-y-1 text-sm">
                        <p className="flex justify-between">
                          <span className="text-mutedText">Min Amount:</span>
                          <span className="text-text">${bridge.limits.minAmount}</span>
                        </p>
                        <p className="flex justify-between">
                          <span className="text-mutedText">Max Amount:</span>
                          <span className="text-text">${bridge.limits.maxAmount.toLocaleString()}</span>
                        </p>
                        <p className="flex justify-between">
                          <span className="text-mutedText">Daily Limit:</span>
                          <span className="text-text">${(bridge.limits.dailyLimit / 1000000).toFixed(1)}M</span>
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })()}
            </div>
          )}
        </div>
      )}
      
      {activeTab === 'transfers' && (
        <TransferTracker
          transfers={transfers}
          onTransferSelect={setSelectedTransfer}
          onRetry={retryTransfer}
          selectedTransfer={selectedTransfer}
          maxDisplay={50}
        />
      )}
    </div>
  );
}
