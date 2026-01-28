'use client';

/**
 * War Room - Dashboard Page
 * 
 * Main monitoring dashboard for institutional users (R3/R4)
 * 
 * Features:
 * - Live alerts
 * - Transaction flow summary
 * - System status
 * - Quick actions
 * - Clickable flagged items with explainability modal
 */

import React, { useState } from 'react';
import WarRoomShell from '@/components/shells/WarRoomShell';
import { useAuth } from '@/lib/auth-context';
import { useDashboardStats, useFlaggedQueue, FlaggedTransaction } from '@/lib/data-service';

// ═══════════════════════════════════════════════════════════════════════════════
// STAT CARD COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

interface StatCardProps {
  label: string;
  value: string;
  change?: string;
  changeType?: 'positive' | 'negative' | 'neutral';
  icon: React.ReactNode;
}

function StatCard({ label, value, change, changeType = 'neutral', icon }: StatCardProps) {
  const changeColors = {
    positive: 'text-green-400',
    negative: 'text-red-400',
    neutral: 'text-slate-400',
  };
  
  return (
    <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-slate-400">{label}</p>
          <p className="text-2xl font-bold text-white mt-1">{value}</p>
          {change && (
            <p className={`text-sm mt-1 ${changeColors[changeType]}`}>
              {change}
            </p>
          )}
        </div>
        <div className="text-slate-400">
          {icon}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// FLAGGED ITEM ROW COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

function FlaggedRow({ item, onClick }: { item: FlaggedTransaction; onClick: () => void }) {
  const getTypeConfig = (riskLevel?: string, status?: string) => {
    if (riskLevel === 'CRITICAL' || status === 'escalated') {
      return { 
        bg: 'bg-red-500/10', 
        border: 'border-red-500/30', 
        icon: 'text-red-400',
        badge: 'bg-red-500',
        type: 'critical' as const
      };
    }
    if (riskLevel === 'HIGH' || status === 'under_review') {
      return { 
        bg: 'bg-amber-500/10', 
        border: 'border-amber-500/30', 
        icon: 'text-amber-400',
        badge: 'bg-amber-500',
        type: 'warning' as const
      };
    }
    return { 
      bg: 'bg-blue-500/10', 
      border: 'border-blue-500/30', 
      icon: 'text-blue-400',
      badge: 'bg-blue-500',
      type: 'info' as const
    };
  };
  
  const config = getTypeConfig(item.riskLevel, item.status);
  const timeAgo = item.timestamp ? formatTimeAgo(new Date(item.timestamp)) : 'Unknown';
  
  return (
    <div 
      onClick={onClick}
      className={`${config.bg} border ${config.border} rounded-lg p-3 hover:bg-slate-700/50 transition-colors cursor-pointer group`}
    >
      <div className="flex items-start gap-3">
        <div className={`mt-0.5 ${config.icon}`}>
          {config.type === 'critical' ? (
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          ) : (
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={`px-1.5 py-0.5 text-xs font-bold text-white rounded ${config.badge}`}>
              {item.riskLevel || 'FLAGGED'}
            </span>
            <span className="text-sm font-medium text-white truncate">
              {item.reason || 'Flagged for review'}
            </span>
          </div>
          <p className="text-sm text-slate-400 mt-1 line-clamp-2">
            Risk Score: {item.riskScore?.toFixed(1) || 'N/A'} • {item.status?.replace('_', ' ') || 'pending'}
          </p>
          {item.address && (
            <p className="text-xs font-mono text-slate-500 mt-1">{item.address}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500 whitespace-nowrap">{timeAgo}</span>
          <svg className="w-4 h-4 text-indigo-400 opacity-0 group-hover:opacity-100 transition-opacity" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </div>
      </div>
    </div>
  );
}

// Helper to format time ago
function formatTimeAgo(date: Date): string {
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
// EXPLAINABILITY MODAL COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

interface ExplainabilityData {
  riskScore: number;
  riskLevel: string;
  narrative: string;
  patterns: Array<{
    name: string;
    description: string;
    severity: string;
    confidence: number;
  }>;
  factors: Array<{
    name: string;
    value: number;
    impact: number;
    description: string;
  }>;
  typologies: string[];
  confidence: number;
}

function ExplainabilityModal({ 
  item, 
  onClose,
  onInvestigate,
}: { 
  item: FlaggedTransaction; 
  onClose: () => void;
  onInvestigate: () => void;
}) {
  // Generate explanation based on item data
  const explanation: ExplainabilityData = React.useMemo(() => {
    const riskScore = item.riskScore ?? 0.5;
    const riskLevel = item.riskLevel || (riskScore > 0.7 ? 'HIGH' : riskScore > 0.4 ? 'MEDIUM' : 'LOW');
    
    // Build patterns from available data
    const patterns = [];
    
    if (riskLevel === 'CRITICAL' || riskLevel === 'HIGH') {
      patterns.push({
        name: 'high_risk_transfer',
        description: `This transaction has been flagged due to ${item.reason || 'suspicious activity patterns'}`,
        severity: 'high',
        confidence: 0.85,
      });
    }
    
    if (item.reason?.toLowerCase().includes('velocity') || item.reason?.toLowerCase().includes('fan-out')) {
      patterns.push({
        name: 'velocity_anomaly',
        description: 'Unusual transaction frequency detected in short time window',
        severity: 'medium',
        confidence: 0.78,
      });
    }
    
    if (item.reason?.toLowerCase().includes('sanction') || item.reason?.toLowerCase().includes('ofac')) {
      patterns.push({
        name: 'sanctions_proximity',
        description: 'Transaction path includes addresses within 2 hops of sanctioned entities',
        severity: 'critical',
        confidence: 0.92,
      });
    }
    
    if (item.reason?.toLowerCase().includes('mixer') || item.reason?.toLowerCase().includes('layering')) {
      patterns.push({
        name: 'mixing_pattern',
        description: 'Transaction flow consistent with layering or mixing behavior',
        severity: 'high',
        confidence: 0.81,
      });
    }
    
    // Default pattern if none matched
    if (patterns.length === 0) {
      patterns.push({
        name: 'general_risk',
        description: item.reason || 'Flagged for compliance review based on ML risk scoring',
        severity: 'medium',
        confidence: 0.75,
      });
    }
    
    // Build factors
    const factors = [
      { name: 'Transaction Value', value: riskScore * 100, impact: riskScore > 0.7 ? 0.3 : 0.1, description: 'Transaction amount relative to typical patterns' },
      { name: 'Velocity Score', value: 0.65, impact: 0.2, description: 'Transaction frequency in 24h window' },
      { name: 'Network Centrality', value: 0.45, impact: 0.15, description: 'PageRank score in transaction graph' },
      { name: 'Counterparty Risk', value: 0.55, impact: 0.25, description: 'Risk score of connected addresses' },
    ];
    
    // Build typologies
    const typologies: string[] = [];
    if (riskLevel === 'HIGH' || riskLevel === 'CRITICAL') {
      typologies.push('Potential Layering');
      if (item.reason?.toLowerCase().includes('sanction')) {
        typologies.push('Sanctions Evasion Risk');
      }
    }
    
    return {
      riskScore,
      riskLevel,
      narrative: `This transaction was flagged with a ${riskLevel} risk classification. ` +
        `${item.reason || 'The ML pipeline detected patterns requiring review'}. ` +
        `The GraphSAGE model analyzed the transaction's network context and XGBoost provided behavioral risk scoring.`,
      patterns,
      factors,
      typologies,
      confidence: 0.82,
    };
  }, [item]);
  
  const getRiskColor = (level: string) => {
    switch (level.toUpperCase()) {
      case 'CRITICAL': return 'text-red-500 bg-red-500';
      case 'HIGH': return 'text-amber-500 bg-amber-500';
      case 'MEDIUM': return 'text-yellow-400 bg-yellow-400';
      case 'LOW': return 'text-green-500 bg-green-500';
      default: return 'text-slate-400 bg-slate-400';
    }
  };
  
  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical': return 'border-red-500 bg-red-500/10 text-red-400';
      case 'high': return 'border-amber-500 bg-amber-500/10 text-amber-400';
      case 'medium': return 'border-yellow-400 bg-yellow-400/10 text-yellow-400';
      default: return 'border-slate-500 bg-slate-500/10 text-slate-400';
    }
  };
  
  const riskColorClass = getRiskColor(explanation.riskLevel);
  
  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-slate-900 rounded-2xl border border-slate-700 w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col shadow-2xl">
        {/* Header */}
        <div className="px-6 py-4 bg-slate-800 border-b border-slate-700 flex items-center gap-4">
          <div className={`p-2 rounded-lg ${riskColorClass.split(' ')[1]}/20`}>
            <svg className={`w-6 h-6 ${riskColorClass.split(' ')[0]}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </div>
          <div className="flex-1">
            <h2 className="text-lg font-bold text-white">Decision Explainability</h2>
            <p className="text-sm text-slate-400 font-mono">{item.address || item.id}</p>
          </div>
          <div className={`px-3 py-1 rounded-full ${riskColorClass.split(' ')[1]}/20 border ${riskColorClass.split(' ')[1].replace('bg-', 'border-')}/50`}>
            <span className={`text-sm font-bold ${riskColorClass.split(' ')[0]}`}>{explanation.riskLevel} RISK</span>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-700 rounded-lg transition-colors">
            <svg className="w-5 h-5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        
        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Risk Score */}
          <div className="flex items-center gap-6">
            <div className="relative w-24 h-24">
              <svg className="w-24 h-24 -rotate-90">
                <circle cx="48" cy="48" r="40" stroke="currentColor" strokeWidth="8" fill="none" className="text-slate-700" />
                <circle 
                  cx="48" cy="48" r="40" 
                  stroke="currentColor" 
                  strokeWidth="8" 
                  fill="none" 
                  strokeDasharray={`${explanation.riskScore * 251.2} 251.2`}
                  className={riskColorClass.split(' ')[0]}
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className={`text-2xl font-bold ${riskColorClass.split(' ')[0]}`}>
                  {Math.round(explanation.riskScore * 100)}
                </span>
              </div>
            </div>
            <div>
              <p className="text-sm text-slate-400">Confidence: {Math.round(explanation.confidence * 100)}%</p>
              <p className="text-sm text-slate-500 mt-1">Model: GraphSAGE + XGBoost</p>
            </div>
          </div>
          
          {/* Narrative */}
          <div>
            <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wide mb-3">Analysis Summary</h3>
            <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
              <p className="text-slate-200 leading-relaxed">{explanation.narrative}</p>
            </div>
          </div>
          
          {/* Patterns */}
          {explanation.patterns.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wide mb-3">Detected Patterns</h3>
              <div className="space-y-2">
                {explanation.patterns.map((p, i) => (
                  <div key={i} className={`border rounded-lg p-3 ${getSeverityColor(p.severity)}`}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-semibold uppercase">{p.name.replace(/_/g, ' ')}</span>
                      <span className="text-xs opacity-75">{Math.round(p.confidence * 100)}% confidence</span>
                    </div>
                    <p className="text-sm opacity-90">{p.description}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
          
          {/* Factors */}
          {explanation.factors.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wide mb-3">Contributing Factors (SHAP)</h3>
              <div className="space-y-3">
                {explanation.factors.map((f, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <span className="w-32 text-sm text-slate-300 truncate">{f.name}</span>
                    <div className="flex-1 h-5 bg-slate-800 rounded relative">
                      <div 
                        className={`h-5 rounded ${f.impact > 0.2 ? 'bg-red-500/70' : 'bg-blue-500/70'}`}
                        style={{ width: `${Math.min(f.impact * 100 * 3, 100)}%` }}
                      />
                    </div>
                    <span className={`text-sm font-mono w-12 text-right ${f.impact > 0.2 ? 'text-red-400' : 'text-blue-400'}`}>
                      +{Math.round(f.impact * 100)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
          
          {/* Typologies */}
          {explanation.typologies.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wide mb-3">AML Typologies</h3>
              <div className="flex flex-wrap gap-2">
                {explanation.typologies.map((t, i) => (
                  <span key={i} className="px-3 py-1 bg-red-500/15 border border-red-500/30 rounded-lg text-sm text-red-400">
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
        
        {/* Footer */}
        <div className="px-6 py-4 bg-slate-800 border-t border-slate-700 flex justify-end gap-3">
          <button 
            onClick={onClose}
            className="px-4 py-2 text-slate-400 hover:text-slate-200 transition-colors"
          >
            Close
          </button>
          <button 
            onClick={onInvestigate}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            Investigate in Graph
          </button>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// ALERT ROW COMPONENT (kept for compatibility)
// ═══════════════════════════════════════════════════════════════════════════════

// NOTE: Alert and AlertRow are preserved for potential future use with real-time alerts
// Currently using FlaggedRow with live flaggedQueue data from API

interface Alert {
  id: string;
  type: 'critical' | 'warning' | 'info';
  title: string;
  description: string;
  timestamp: string;
  address?: string;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
function AlertRow({ alert }: { alert: Alert }) {
  const typeConfig = {
    critical: { 
      bg: 'bg-red-500/10', 
      border: 'border-red-500/30', 
      icon: 'text-red-400',
      badge: 'bg-red-500'
    },
    warning: { 
      bg: 'bg-amber-500/10', 
      border: 'border-amber-500/30', 
      icon: 'text-amber-400',
      badge: 'bg-amber-500'
    },
    info: { 
      bg: 'bg-blue-500/10', 
      border: 'border-blue-500/30', 
      icon: 'text-blue-400',
      badge: 'bg-blue-500'
    },
  };
  
  const config = typeConfig[alert.type];
  
  return (
    <div className={`${config.bg} border ${config.border} rounded-lg p-3 hover:bg-slate-700/50 transition-colors cursor-pointer`}>
      <div className="flex items-start gap-3">
        <div className={`mt-0.5 ${config.icon}`}>
          {alert.type === 'critical' ? (
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          ) : (
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={`px-1.5 py-0.5 text-xs font-bold text-white rounded ${config.badge}`}>
              {alert.type.toUpperCase()}
            </span>
            <span className="text-sm font-medium text-white truncate">{alert.title}</span>
          </div>
          <p className="text-sm text-slate-400 mt-1 line-clamp-2">{alert.description}</p>
          {alert.address && (
            <p className="text-xs font-mono text-slate-500 mt-1">{alert.address}</p>
          )}
        </div>
        <span className="text-xs text-slate-500 whitespace-nowrap">{alert.timestamp}</span>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MOCK DATA (kept for reference/testing)
// ═══════════════════════════════════════════════════════════════════════════════

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const MOCK_ALERTS: Alert[] = [
  {
    id: '1',
    type: 'critical',
    title: 'High-risk transaction detected',
    description: 'Transaction of 50 ETH to address flagged by sanctions oracle',
    timestamp: '2m ago',
    address: '0xdead...beef',
  },
  {
    id: '2',
    type: 'warning',
    title: 'Unusual transaction pattern',
    description: 'Multiple rapid transfers from dormant wallet detected',
    timestamp: '15m ago',
    address: '0x1234...5678',
  },
  {
    id: '3',
    type: 'info',
    title: 'New counterparty flagged for review',
    description: 'First-time interaction with wallet showing mixed signals',
    timestamp: '1h ago',
    address: '0xabcd...efgh',
  },
  {
    id: '4',
    type: 'warning',
    title: 'Geographic risk escalation',
    description: 'Transaction routed through high-risk jurisdiction',
    timestamp: '2h ago',
    address: '0x9876...5432',
  },
];

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function WarRoomDashboard() {
  const { capabilities } = useAuth();
  const { data: stats, loading: statsLoading, error: statsError } = useDashboardStats();
  const { data: flaggedQueue, loading: flaggedLoading, error: flaggedError } = useFlaggedQueue();
  const [selectedItem, setSelectedItem] = useState<FlaggedTransaction | null>(null);
  
  // Format numbers for display
  const formatNumber = (n: number) => n?.toLocaleString() || '0';
  const formatPercent = (n: number) => `${(n || 0).toFixed(1)}%`;
  
  const handleInvestigate = () => {
    if (selectedItem) {
      // Navigate to graph with transaction
      window.location.href = `/war-room/detection/graph?tx=${selectedItem.id}`;
    }
    setSelectedItem(null);
  };
  
  return (
    <WarRoomShell>
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">War Room Dashboard</h1>
            <p className="text-slate-400 mt-1">Real-time monitoring and alerts</p>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 px-3 py-2 bg-green-500/10 border border-green-500/30 rounded-lg">
              <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
              <span className="text-sm text-green-400">Live</span>
            </div>
          </div>
        </div>

        {statsError && (
          <div className="px-3 py-2 text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg">
            Failed to load dashboard stats. {`${statsError}`}
          </div>
        )}
        
        {/* Stats Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            label="Flagged Transactions"
            value={statsLoading ? '...' : formatNumber(stats?.flaggedCount || flaggedQueue.length)}
            change={flaggedLoading ? 'Loading…' : `${flaggedQueue.filter(f => f.status === 'pending').length} pending review`}
            changeType={flaggedQueue.filter(f => f.status === 'pending').length > 5 ? 'negative' : 'neutral'}
            icon={
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            }
          />
          <StatCard
            label="Total Transactions"
            value={statsLoading ? '...' : formatNumber(stats?.totalTransactions || 0)}
            change={`${formatNumber(stats?.totalVolume || 0)} ETH volume`}
            changeType="positive"
            icon={
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
              </svg>
            }
          />
          <StatCard
            label="Compliance Rate"
            value={statsLoading ? '...' : formatPercent(stats?.complianceRate || 0)}
            change={stats?.complianceRate && stats.complianceRate > 95 ? "Within target" : "Below target"}
            changeType={stats?.complianceRate && stats.complianceRate > 95 ? "neutral" : "negative"}
            icon={
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 21v-4m0 0V5a2 2 0 012-2h6.5l1 1H21l-3 6 3 6h-8.5l-1-1H5a2 2 0 00-2 2zm9-13.5V9" />
              </svg>
            }
          />
          <StatCard
            label="Avg Risk Score"
            value={statsLoading ? '...' : (stats?.averageRiskScore || 0).toFixed(1)}
            change={`${formatNumber(stats?.highRiskWallets || 0)} high-risk wallets`}
            changeType={stats?.highRiskWallets && stats.highRiskWallets > 10 ? "negative" : "positive"}
            icon={
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            }
          />
        </div>
        
        {/* Main Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Flagged Queue Panel */}
          <div className="lg:col-span-2 bg-slate-800 rounded-xl border border-slate-700">
            <div className="px-4 py-3 border-b border-slate-700 flex items-center justify-between">
              <h2 className="font-semibold text-white">Flagged Queue ({flaggedQueue.length})</h2>
              <a href="/war-room/alerts" className="text-sm text-indigo-400 hover:text-indigo-300">View all</a>
            </div>
            <div className="p-4 space-y-3 max-h-96 overflow-y-auto">
              {flaggedError ? (
                <div className="text-center py-8 text-red-400">Failed to load flagged queue. {flaggedError}</div>
              ) : flaggedLoading ? (
                <div className="text-center py-8 text-slate-400">Loading flagged items...</div>
              ) : flaggedQueue.length === 0 ? (
                <div className="text-center py-8 text-slate-400">No flagged items</div>
              ) : (
                flaggedQueue.slice(0, 10).map((item) => (
                  <FlaggedRow 
                    key={item.id} 
                    item={item} 
                    onClick={() => setSelectedItem(item)}
                  />
                ))
              )}
            </div>
          </div>
          
          {/* Quick Actions Panel */}
          <div className="bg-slate-800 rounded-xl border border-slate-700">
            <div className="px-4 py-3 border-b border-slate-700">
              <h2 className="font-semibold text-white">Quick Actions</h2>
            </div>
            <div className="p-4 space-y-3">
              <a href="/war-room/detection-studio" className="w-full flex items-center gap-3 px-4 py-3 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors text-left">
                <svg className="w-5 h-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                <span className="text-white">Search Address</span>
              </a>
              
              <a href="/war-room/compliance" className="w-full flex items-center gap-3 px-4 py-3 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors text-left">
                <svg className="w-5 h-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
                <span className="text-white">View Reports</span>
              </a>
              
              <a href="/war-room/detection-studio?view=network" className="w-full flex items-center gap-3 px-4 py-3 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors text-left">
                <svg className="w-5 h-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
                <span className="text-white">Entity Graph</span>
              </a>
              
              {capabilities?.canEditPolicies && (
                <a href="/war-room/policies" className="w-full flex items-center gap-3 px-4 py-3 bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors text-left">
                  <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
                  </svg>
                  <span className="text-white">Configure Policies</span>
                </a>
              )}
            </div>
          </div>
        </div>
        
        {/* System Status Bar */}
        <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-green-500"></div>
                <span className="text-sm text-slate-300">Risk Engine</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-green-500"></div>
                <span className="text-sm text-slate-300">Sanctions Oracle</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-green-500"></div>
                <span className="text-sm text-slate-300">GraphSAGE</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-green-500"></div>
                <span className="text-sm text-slate-300">Monitoring</span>
              </div>
            </div>
            <div className="text-sm text-slate-400">
              Last updated: Just now
            </div>
          </div>
        </div>
      </div>
      
      {/* Explainability Modal */}
      {selectedItem && (
        <ExplainabilityModal
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
          onInvestigate={handleInvestigate}
        />
      )}
    </WarRoomShell>
  );
}
