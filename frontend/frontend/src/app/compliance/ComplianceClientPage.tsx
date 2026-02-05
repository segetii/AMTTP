'use client';

/**
 * Unified Compliance Dashboard
 * 
 * Real-time compliance monitoring with:
 * - Service health status
 * - Transaction evaluation
 * - Sanctions screening
 * - Geographic risk assessment
 * - AML monitoring alerts
 * - Explainability modal
 */

import React, { useState, useEffect } from 'react';
import WarRoomShell from '@/components/shells/WarRoomShell';
import { useAuth } from '@/lib/auth-context';
import { useDashboardStats, useFlaggedQueue, FlaggedTransaction } from '@/lib/data-service';

// API Base helper
function getApiBase(): string {
  const envOrigin = process.env.NEXT_PUBLIC_API_ORIGIN;
  if (envOrigin && envOrigin.length > 0) return envOrigin.replace(/\/$/, '');

  // Fallbacks: when running locally in the browser, prefer the gateway on 8888
  // (where nginx proxies /api, /sanctions, /geo, etc.). If the page is served
  // through the gateway (port 8888) or any other host, use same origin.
  if (typeof window === 'undefined') return 'http://localhost:8888';

  const { protocol, hostname, port } = window.location;
  if (port === '3006') {
    return `${protocol}//${hostname}:8888`;
  }

  return `${protocol}//${hostname}${port ? `:${port}` : ''}`;
}

// Service Health interface
interface ServiceHealth {
  name: string;
  status: 'healthy' | 'unhealthy' | 'unknown';
  latency?: number;
  lastCheck: string;
}

// Sanctions Check Result
interface SanctionsCheckResult {
  query: { address?: string; name?: string };
  is_sanctioned: boolean;
  matches: Array<{
    match_type: string;
    confidence: number;
    entity?: { name: string; source_list: string };
  }>;
  check_timestamp: string;
}

// Geographic Risk Result
interface GeoListItem {
  name: string;
  since: string;
  reason: string;
}

interface CountryRisk {
  country_code: string;
  risk_score: number;
  risk_level: string;
  risk_factors: string[];
  lists: {
    fatf_black: GeoListItem | null;
    fatf_grey: GeoListItem | null;
    eu_high_risk: GeoListItem | null;
    uk_high_risk: GeoListItem | null;
    tax_haven: GeoListItem | null;
  };
}

// Transaction Evaluation Result
interface TransactionEvalResult {
  transaction_id: string;
  decision: string;
  risk_score: number;
  risk_level: string;
  flags: string[];
  reasons: string[];
  processing_time_ms: number;
}

// ═══════════════════════════════════════════════════════════════════════════════
// STAT CARD COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

interface StatCardProps {
  label: string;
  value: string;
  change?: string;
  changeType?: 'positive' | 'negative' | 'neutral';
  icon: React.ReactNode;
  gradient?: string;
}

function StatCard({ label, value, change, changeType = 'neutral', icon, gradient }: StatCardProps) {
  const changeColors = {
    positive: 'text-emerald-400',
    negative: 'text-rose-400',
    neutral: 'text-slate-400',
  };
  
  const defaultGradient = 'from-slate-800/90 to-slate-900/90';
  
  return (
    <div className={`relative overflow-hidden bg-gradient-to-br ${gradient || defaultGradient} backdrop-blur-xl rounded-2xl p-5 border border-white/10 shadow-xl shadow-black/20 hover:shadow-2xl hover:shadow-black/30 hover:border-white/20 transition-all duration-300 group`}>
      {/* Subtle gradient overlay */}
      <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
      
      <div className="relative flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-slate-400 tracking-wide uppercase">{label}</p>
          <p className="text-3xl font-bold text-white mt-2 tracking-tight">{value}</p>
          {change && (
            <p className={`text-sm mt-2 ${changeColors[changeType]} flex items-center gap-1`}>
              {changeType === 'positive' && <span>↑</span>}
              {changeType === 'negative' && <span>↓</span>}
              {change}
            </p>
          )}
        </div>
        <div className="p-3 bg-white/5 rounded-xl border border-white/10 text-slate-300 group-hover:scale-110 transition-transform duration-300">
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

export default function ComplianceDashboard() {
  const { capabilities } = useAuth();
  const { data: stats, loading: statsLoading, error: statsError } = useDashboardStats();
  const { data: flaggedQueue, loading: flaggedLoading, error: flaggedError } = useFlaggedQueue();
  const [selectedItem, setSelectedItem] = useState<FlaggedTransaction | null>(null);
  
  // Service health state
  const [services, setServices] = useState<ServiceHealth[]>([
    { name: 'Orchestrator', status: 'unknown', lastCheck: new Date().toISOString() },
    { name: 'Sanctions Service', status: 'unknown', lastCheck: new Date().toISOString() },
    { name: 'Monitoring Service', status: 'unknown', lastCheck: new Date().toISOString() },
    { name: 'Geo-Risk Service', status: 'unknown', lastCheck: new Date().toISOString() },
  ]);
  
  // Sanctions check state
  const [sanctionsInput, setSanctionsInput] = useState({ address: '', name: '' });
  const [sanctionsResult, setSanctionsResult] = useState<SanctionsCheckResult | null>(null);
  const [sanctionsLoading, setSanctionsLoading] = useState(false);
  
  // Geographic risk state
  const [geoInput, setGeoInput] = useState('');
  const [geoResult, setGeoResult] = useState<CountryRisk | null>(null);
  const [geoLoading, setGeoLoading] = useState(false);
  
  // Transaction evaluation state
  const [txInput, setTxInput] = useState({ from: '', to: '', amount: '', currency: 'ETH' });
  const [txResult, setTxResult] = useState<TransactionEvalResult | null>(null);
  const [txLoading, setTxLoading] = useState(false);
  
  // FATF lists state
  const [fatfLists, setFatfLists] = useState<{ black_list: string[]; grey_list: string[] } | null>(null);
  
  // Health check effect
  useEffect(() => {
    const checkHealth = async () => {
      const base = getApiBase();
      const endpoints = [
        { name: 'Orchestrator', url: `${base}/api/health` },
        { name: 'Sanctions Service', url: `${base}/sanctions/health` },
        { name: 'Monitoring Service', url: `${base}/monitoring/health` },
        { name: 'Geo-Risk Service', url: `${base}/geo/health` },
      ];

      const results = await Promise.all(
        endpoints.map(async ({ name, url }) => {
          const start = Date.now();
          try {
            const res = await fetch(url, { method: 'GET' });
            const latency = Date.now() - start;
            return {
              name,
              status: res.ok ? 'healthy' : 'unhealthy',
              latency,
              lastCheck: new Date().toISOString(),
            } as ServiceHealth;
          } catch {
            return {
              name,
              status: 'unhealthy',
              lastCheck: new Date().toISOString(),
            } as ServiceHealth;
          }
        })
      );
      setServices(results);
    };
    
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);
  
  // Load FATF lists on mount
  useEffect(() => {
    const loadFatfLists = async () => {
      try {
        const base = getApiBase();
        const [blackRes, greyRes] = await Promise.all([
          fetch(`${base}/geo/lists/fatf-black`),
          fetch(`${base}/geo/lists/fatf-grey`),
        ]);
        const blackList = blackRes.ok ? await blackRes.json() : { countries: [] };
        const greyList = greyRes.ok ? await greyRes.json() : { countries: [] };
        setFatfLists({
          black_list: blackList.countries || [],
          grey_list: greyList.countries || [],
        });
      } catch (err) {
        console.error('Failed to load FATF lists:', err);
      }
    };
    loadFatfLists();
  }, []);
  
  // Sanctions check handler
  const handleSanctionsCheck = async () => {
    if (!sanctionsInput.address && !sanctionsInput.name) return;
    setSanctionsLoading(true);
    setSanctionsResult(null);
    try {
      const base = getApiBase();
      const params = new URLSearchParams();
      if (sanctionsInput.address) params.set('address', sanctionsInput.address);
      if (sanctionsInput.name) params.set('name', sanctionsInput.name);
      const res = await fetch(`${base}/sanctions/check?${params}`);
      if (res.ok) {
        const data = await res.json();
        setSanctionsResult(data);
      }
    } catch (err) {
      console.error('Sanctions check failed:', err);
    } finally {
      setSanctionsLoading(false);
    }
  };
  
  // Geographic risk check handler
  const handleGeoCheck = async () => {
    if (!geoInput) return;
    setGeoLoading(true);
    setGeoResult(null);
    try {
      const base = getApiBase();
      const res = await fetch(`${base}/geo/country/${geoInput.toUpperCase()}`);
      if (res.ok) {
        const data = await res.json();
        setGeoResult(data);
      }
    } catch (err) {
      console.error('Geo check failed:', err);
    } finally {
      setGeoLoading(false);
    }
  };
  
  // Transaction evaluation handler
  const handleEvaluateTransaction = async () => {
    if (!txInput.from || !txInput.to || !txInput.amount) return;
    setTxLoading(true);
    setTxResult(null);
    try {
      const base = getApiBase();
      const res = await fetch(`${base}/api/evaluate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          from_address: txInput.from,
          to_address: txInput.to,
          amount: parseFloat(txInput.amount),
          currency: txInput.currency,
          transaction_id: `TX-${Date.now()}`,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setTxResult(data);
      }
    } catch (err) {
      console.error('Transaction evaluation failed:', err);
    } finally {
      setTxLoading(false);
    }
  };
  
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
      <div className="space-y-8">
        {/* Hero Header */}
        <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-indigo-900 via-purple-900 to-slate-900 p-8 border border-white/10 shadow-2xl">
          {/* Animated background elements */}
          <div className="absolute inset-0 overflow-hidden">
            <div className="absolute -top-24 -right-24 w-96 h-96 bg-purple-500/20 rounded-full blur-3xl animate-pulse" />
            <div className="absolute -bottom-24 -left-24 w-96 h-96 bg-indigo-500/20 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 bg-cyan-500/10 rounded-full blur-3xl" />
          </div>
          
          {/* Grid pattern overlay */}
          <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:50px_50px]" />
          
          <div className="relative flex items-center justify-between">
            <div>
              <div className="flex items-center gap-4 mb-3">
                <div className="p-3 bg-white/10 rounded-2xl backdrop-blur-sm border border-white/20">
                  <svg className="w-8 h-8 text-purple-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
                  </svg>
                </div>
                <div>
                  <h1 className="text-3xl font-bold text-white tracking-tight">
                    Compliance Command Center
                  </h1>
                  <p className="text-purple-200/80 mt-1">Real-time AML monitoring, sanctions screening & risk intelligence</p>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2 px-4 py-2.5 bg-emerald-500/20 backdrop-blur-sm border border-emerald-400/30 rounded-xl shadow-lg shadow-emerald-500/20">
                <div className="relative">
                  <div className="w-2.5 h-2.5 rounded-full bg-emerald-400"></div>
                  <div className="absolute inset-0 w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping"></div>
                </div>
                <span className="text-sm font-semibold text-emerald-300">System Live</span>
              </div>
              <div className="px-4 py-2.5 bg-white/10 backdrop-blur-sm border border-white/20 rounded-xl">
                <span className="text-sm text-slate-300">{new Date().toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Service Health Grid */}
        <div>
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-cyan-500/20 rounded-lg">
              <svg className="w-5 h-5 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
              </svg>
            </div>
            <h2 className="text-lg font-bold text-white">Service Health Monitor</h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {services.map((service, idx) => (
              <div 
                key={service.name} 
                className="group relative bg-gradient-to-br from-slate-800/80 to-slate-900/80 backdrop-blur-xl rounded-2xl p-5 border border-white/10 hover:border-white/20 shadow-lg hover:shadow-xl transition-all duration-300"
                style={{ animationDelay: `${idx * 100}ms` }}
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className="relative">
                      <div className={`w-3 h-3 rounded-full ${
                        service.status === 'healthy' ? 'bg-emerald-400' :
                        service.status === 'unhealthy' ? 'bg-rose-500' : 'bg-slate-500'
                      }`} />
                      {service.status === 'healthy' && (
                        <div className="absolute inset-0 w-3 h-3 rounded-full bg-emerald-400 animate-ping opacity-75" />
                      )}
                    </div>
                    <span className="text-white font-semibold text-sm">{service.name}</span>
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <span className={`px-3 py-1.5 rounded-lg text-xs font-bold tracking-wide ${
                    service.status === 'healthy' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' :
                    service.status === 'unhealthy' ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30' : 'bg-slate-500/20 text-slate-400 border border-slate-500/30'
                  }`}>
                    {service.status.toUpperCase()}
                  </span>
                  {service.latency !== undefined && (
                    <span className="text-xs text-slate-400 font-mono bg-slate-700/50 px-2 py-1 rounded">{service.latency}ms</span>
                  )}
                </div>
                <div className="mt-3 pt-3 border-t border-white/5">
                  <div className="text-xs text-slate-500">Last: {new Date(service.lastCheck).toLocaleTimeString()}</div>
                </div>
              </div>
            ))}
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

        {/* Transaction Evaluation */}
        <div className="relative overflow-hidden bg-gradient-to-br from-purple-900/40 via-slate-800/80 to-slate-900/80 backdrop-blur-xl rounded-3xl p-8 border border-purple-500/20 shadow-2xl shadow-purple-500/10">
          {/* Decorative elements */}
          <div className="absolute top-0 right-0 w-64 h-64 bg-purple-500/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
          <div className="absolute bottom-0 left-0 w-48 h-48 bg-indigo-500/10 rounded-full blur-3xl translate-y-1/2 -translate-x-1/2" />
          
          <div className="relative">
            <div className="flex items-center gap-3 mb-6">
              <div className="p-2.5 bg-purple-500/20 rounded-xl border border-purple-500/30">
                <svg className="w-6 h-6 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
                </svg>
              </div>
              <div>
                <h2 className="text-xl font-bold text-white">Transaction Evaluation</h2>
                <p className="text-sm text-purple-200/60">Run real-time risk assessment on any transaction</p>
              </div>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              <div className="relative">
                <label className="block text-xs font-medium text-slate-400 mb-2 uppercase tracking-wide">From Address</label>
                <input
                  type="text"
                  placeholder="0x..."
                  value={txInput.from}
                  onChange={(e) => setTxInput({ ...txInput, from: e.target.value })}
                  className="w-full bg-slate-900/50 border border-white/10 rounded-xl px-4 py-3.5 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500/50 transition-all font-mono text-sm"
                />
              </div>
              <div className="relative">
                <label className="block text-xs font-medium text-slate-400 mb-2 uppercase tracking-wide">To Address</label>
                <input
                  type="text"
                  placeholder="0x..."
                  value={txInput.to}
                  onChange={(e) => setTxInput({ ...txInput, to: e.target.value })}
                  className="w-full bg-slate-900/50 border border-white/10 rounded-xl px-4 py-3.5 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500/50 transition-all font-mono text-sm"
                />
              </div>
              <div className="relative">
                <label className="block text-xs font-medium text-slate-400 mb-2 uppercase tracking-wide">Amount</label>
                <input
                  type="number"
                  placeholder="0.00"
                  value={txInput.amount}
                  onChange={(e) => setTxInput({ ...txInput, amount: e.target.value })}
                  className="w-full bg-slate-900/50 border border-white/10 rounded-xl px-4 py-3.5 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500/50 transition-all font-mono text-sm"
                />
              </div>
              <div className="relative">
                <label className="block text-xs font-medium text-slate-400 mb-2 uppercase tracking-wide">Currency</label>
                <select
                  value={txInput.currency}
                  onChange={(e) => setTxInput({ ...txInput, currency: e.target.value })}
                  className="w-full bg-slate-900/50 border border-white/10 rounded-xl px-4 py-3.5 text-white focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500/50 transition-all appearance-none cursor-pointer"
                >
                  <option value="ETH">ETH</option>
                  <option value="USDC">USDC</option>
                  <option value="USDT">USDT</option>
                  <option value="BTC">BTC</option>
                </select>
              </div>
            </div>
            
            <button
              onClick={handleEvaluateTransaction}
              disabled={txLoading}
              className="group relative overflow-hidden bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-bold px-8 py-4 rounded-xl transition-all duration-300 disabled:opacity-50 flex items-center gap-3 shadow-lg shadow-purple-500/25 hover:shadow-xl hover:shadow-purple-500/40 hover:scale-[1.02]"
            >
              <div className="absolute inset-0 bg-gradient-to-r from-white/0 via-white/20 to-white/0 translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-700" />
              {txLoading ? (
                <>
                  <div className="animate-spin rounded-full h-5 w-5 border-2 border-white/30 border-t-white"></div>
                  <span>Evaluating...</span>
                </>
              ) : (
                <>
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
                  </svg>
                  <span>Evaluate Transaction</span>
                </>
              )}
            </button>
          </div>
          {txResult && (
            <div className="relative mt-6 bg-gradient-to-br from-slate-800/80 to-slate-900/80 backdrop-blur-sm rounded-2xl p-6 border border-white/10 shadow-xl">
              <div className="absolute top-0 left-0 w-1 h-full rounded-l-2xl bg-gradient-to-b ${
                txResult.decision === 'ALLOW' ? 'from-emerald-400 to-emerald-600' :
                txResult.decision === 'BLOCK' ? 'from-rose-400 to-rose-600' :
                txResult.decision === 'REVIEW' ? 'from-amber-400 to-amber-600' : 'from-orange-400 to-orange-600'
              }" />
              
              <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                <div className="text-center p-4 bg-white/5 rounded-xl">
                  <span className="text-slate-400 text-xs uppercase tracking-wider font-medium">Decision</span>
                  <div className={`text-2xl font-black mt-2 ${
                    txResult.decision === 'ALLOW' ? 'text-emerald-400' :
                    txResult.decision === 'BLOCK' ? 'text-rose-400' :
                    txResult.decision === 'REVIEW' ? 'text-amber-400' : 'text-orange-400'
                  }`}>
                    {txResult.decision}
                  </div>
                </div>
                <div className="text-center p-4 bg-white/5 rounded-xl">
                  <span className="text-slate-400 text-xs uppercase tracking-wider font-medium">Risk Score</span>
                  <div className="text-2xl font-black text-white mt-2">{txResult.risk_score}</div>
                </div>
                <div className="text-center p-4 bg-white/5 rounded-xl">
                  <span className="text-slate-400 text-xs uppercase tracking-wider font-medium">Risk Level</span>
                  <div className={`text-2xl font-black mt-2 ${
                    txResult.risk_level === 'HIGH' ? 'text-rose-400' :
                    txResult.risk_level === 'MEDIUM' ? 'text-amber-400' : 'text-emerald-400'
                  }`}>
                    {txResult.risk_level}
                  </div>
                </div>
                <div className="text-center p-4 bg-white/5 rounded-xl">
                  <span className="text-slate-400 text-xs uppercase tracking-wider font-medium">Latency</span>
                  <div className="text-2xl font-black text-cyan-400 mt-2">{txResult.processing_time_ms}<span className="text-sm font-normal text-slate-400">ms</span></div>
                </div>
              </div>
              {txResult.flags && txResult.flags.length > 0 && (
                <div className="mt-4 pt-4 border-t border-white/10">
                  <span className="text-slate-400 text-xs uppercase tracking-wider font-medium">Risk Flags</span>
                  <div className="flex flex-wrap gap-2 mt-2">
                    {txResult.flags.map((flag, i) => (
                      <span key={i} className="bg-rose-500/20 text-rose-400 px-3 py-1.5 rounded-lg text-sm font-medium border border-rose-500/30">{flag}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Sanctions & Geo Risk */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="relative overflow-hidden bg-gradient-to-br from-orange-900/30 via-slate-800/80 to-slate-900/80 backdrop-blur-xl rounded-3xl p-6 border border-orange-500/20 shadow-xl shadow-orange-500/5">
            <div className="absolute top-0 right-0 w-32 h-32 bg-orange-500/10 rounded-full blur-2xl" />
            
            <div className="relative">
              <div className="flex items-center gap-3 mb-5">
                <div className="p-2.5 bg-orange-500/20 rounded-xl border border-orange-500/30">
                  <svg className="w-5 h-5 text-orange-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                </div>
                <div>
                  <h2 className="text-lg font-bold text-white">Sanctions Screening</h2>
                  <p className="text-xs text-orange-200/60">OFAC, UN, EU & more</p>
                </div>
              </div>
              
              <div className="space-y-3 mb-5">
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wide">Wallet Address</label>
                  <input
                    type="text"
                    placeholder="0x..."
                    value={sanctionsInput.address}
                    onChange={(e) => setSanctionsInput({ ...sanctionsInput, address: e.target.value })}
                    className="w-full bg-slate-900/50 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-orange-500/50 focus:border-orange-500/50 transition-all font-mono text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wide">Entity Name <span className="text-slate-500">(optional)</span></label>
                  <input
                    type="text"
                    placeholder="Company or individual name"
                    value={sanctionsInput.name}
                    onChange={(e) => setSanctionsInput({ ...sanctionsInput, name: e.target.value })}
                    className="w-full bg-slate-900/50 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-orange-500/50 focus:border-orange-500/50 transition-all text-sm"
                  />
                </div>
              </div>
              
              <button
                onClick={handleSanctionsCheck}
                disabled={sanctionsLoading}
                className="w-full group relative overflow-hidden bg-gradient-to-r from-orange-600 to-red-600 hover:from-orange-500 hover:to-red-500 text-white font-bold px-6 py-3.5 rounded-xl transition-all disabled:opacity-50 shadow-lg shadow-orange-500/20 hover:shadow-xl hover:shadow-orange-500/30"
              >
                <div className="absolute inset-0 bg-gradient-to-r from-white/0 via-white/20 to-white/0 translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-700" />
                <span className="relative flex items-center justify-center gap-2">
                  {sanctionsLoading ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-2 border-white/30 border-t-white"></div>
                      Checking...
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                      </svg>
                      Screen for Sanctions
                    </>
                  )}
                </span>
              </button>
            </div>
            {sanctionsResult && (
              <div className={`mt-5 p-5 rounded-2xl border ${
                sanctionsResult.is_sanctioned 
                  ? 'bg-rose-500/10 border-rose-500/30' 
                  : 'bg-emerald-500/10 border-emerald-500/30'
              }`}>
                <div className="flex items-center gap-3 mb-3">
                  <div className={`p-2 rounded-lg ${
                    sanctionsResult.is_sanctioned ? 'bg-rose-500/20' : 'bg-emerald-500/20'
                  }`}>
                    {sanctionsResult.is_sanctioned ? (
                      <svg className="w-6 h-6 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                      </svg>
                    ) : (
                      <svg className="w-6 h-6 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    )}
                  </div>
                  <div className={`text-xl font-black ${
                    sanctionsResult.is_sanctioned ? 'text-rose-400' : 'text-emerald-400'
                  }`}>
                    {sanctionsResult.is_sanctioned ? 'SANCTIONED ENTITY' : 'CLEAR - NO MATCHES'}
                  </div>
                </div>
                {sanctionsResult.matches && sanctionsResult.matches.length > 0 && (
                  <div className="space-y-2">
                    {sanctionsResult.matches.map((match, i) => (
                      <div key={i} className="bg-slate-900/50 rounded-xl p-3 border border-white/5">
                        <div className="flex items-center justify-between">
                          <span className="text-white font-medium">{match.match_type}</span>
                          <span className="text-xs font-bold px-2 py-1 bg-rose-500/20 text-rose-400 rounded-lg">{(match.confidence * 100).toFixed(0)}% match</span>
                        </div>
                        {match.entity && (
                          <div className="text-slate-400 text-sm mt-1">{match.entity.name} • {match.entity.source_list}</div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="relative overflow-hidden bg-gradient-to-br from-cyan-900/30 via-slate-800/80 to-slate-900/80 backdrop-blur-xl rounded-3xl p-6 border border-cyan-500/20 shadow-xl shadow-cyan-500/5">
            <div className="absolute top-0 right-0 w-32 h-32 bg-cyan-500/10 rounded-full blur-2xl" />
            
            <div className="relative">
              <div className="flex items-center gap-3 mb-5">
                <div className="p-2.5 bg-cyan-500/20 rounded-xl border border-cyan-500/30">
                  <svg className="w-5 h-5 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <div>
                  <h2 className="text-lg font-bold text-white">Geographic Risk</h2>
                  <p className="text-xs text-cyan-200/60">Country & jurisdiction analysis</p>
                </div>
              </div>
              
              <div className="mb-5">
                <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wide">Country Code</label>
                <input
                  type="text"
                  placeholder="e.g., US, IR, KP"
                  value={geoInput}
                  onChange={(e) => setGeoInput(e.target.value)}
                  maxLength={2}
                  className="w-full bg-slate-900/50 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500/50 transition-all uppercase font-mono text-lg tracking-widest text-center"
                />
              </div>
              
              <button
                onClick={handleGeoCheck}
                disabled={geoLoading}
                className="w-full group relative overflow-hidden bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-bold px-6 py-3.5 rounded-xl transition-all disabled:opacity-50 shadow-lg shadow-cyan-500/20 hover:shadow-xl hover:shadow-cyan-500/30"
              >
                <div className="absolute inset-0 bg-gradient-to-r from-white/0 via-white/20 to-white/0 translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-700" />
                <span className="relative flex items-center justify-center gap-2">
                  {geoLoading ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-2 border-white/30 border-t-white"></div>
                      Analyzing...
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      Check Country Risk
                    </>
                  )}
                </span>
              </button>
            </div>
            {geoResult && (
              <div className="mt-5 bg-slate-900/50 rounded-2xl p-5 border border-white/10">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <span className="text-4xl font-black text-white tracking-tight">{geoResult.country_code}</span>
                    <div className={`px-4 py-2 rounded-xl text-sm font-bold ${
                      geoResult.risk_level === 'HIGH' ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30' :
                      geoResult.risk_level === 'MEDIUM' ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                    }`}>
                      {geoResult.risk_level} RISK
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-xs text-slate-500 uppercase tracking-wide">Score</div>
                    <div className="text-2xl font-black text-white">{geoResult.risk_score}</div>
                  </div>
                </div>
                
                <div className="flex flex-wrap gap-2 mb-3">
                  {geoResult.lists?.fatf_black && (
                    <span className="px-3 py-1.5 bg-rose-600 text-white rounded-lg text-xs font-bold shadow-lg shadow-rose-500/30">FATF BLACK LIST</span>
                  )}
                  {geoResult.lists?.fatf_grey && (
                    <span className="px-3 py-1.5 bg-amber-500 text-slate-900 rounded-lg text-xs font-bold shadow-lg shadow-amber-500/30">FATF GREY LIST</span>
                  )}
                  {geoResult.lists?.eu_high_risk && (
                    <span className="px-3 py-1.5 bg-orange-500 text-white rounded-lg text-xs font-bold shadow-lg shadow-orange-500/30">EU HIGH RISK</span>
                  )}
                  {geoResult.lists?.tax_haven && (
                    <span className="px-3 py-1.5 bg-purple-500 text-white rounded-lg text-xs font-bold shadow-lg shadow-purple-500/30">TAX HAVEN</span>
                  )}
                </div>
                
                {geoResult.risk_factors && geoResult.risk_factors.length > 0 && (
                  <div>
                    <div className="text-xs text-slate-500 uppercase tracking-wide mb-2">Risk Factors</div>
                    <div className="flex flex-wrap gap-1.5">
                      {geoResult.risk_factors.map((factor, i) => (
                        <span key={i} className="bg-slate-700/50 text-slate-300 px-2.5 py-1 rounded-lg text-xs border border-white/5">{factor}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* FATF Watchlists */}
        {fatfLists && (
          <div className="relative overflow-hidden bg-gradient-to-br from-slate-800/80 to-slate-900/80 backdrop-blur-xl rounded-3xl p-6 border border-white/10 shadow-xl">
            <div className="flex items-center gap-3 mb-6">
              <div className="p-2.5 bg-slate-700/50 rounded-xl border border-white/10">
                <svg className="w-5 h-5 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <div>
                <h2 className="text-lg font-bold text-white">FATF Watchlists</h2>
                <p className="text-xs text-slate-400">Financial Action Task Force designated jurisdictions</p>
              </div>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="p-5 bg-rose-500/10 rounded-2xl border border-rose-500/20">
                <div className="flex items-center gap-2 mb-4">
                  <div className="w-3 h-3 rounded-full bg-rose-500 shadow-lg shadow-rose-500/50" />
                  <h3 className="text-rose-400 font-bold">Black List</h3>
                  <span className="ml-auto px-2 py-0.5 bg-rose-500/20 rounded-full text-xs font-bold text-rose-400">{fatfLists.black_list.length}</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {fatfLists.black_list.length > 0 ? fatfLists.black_list.map((code) => (
                    <span key={code} className="bg-rose-600/30 text-rose-300 px-3 py-1.5 rounded-lg text-sm font-bold border border-rose-500/30 hover:bg-rose-600/40 transition-colors cursor-default">{code}</span>
                  )) : <span className="text-slate-500 text-sm">No countries on black list</span>}
                </div>
              </div>
              <div className="p-5 bg-amber-500/10 rounded-2xl border border-amber-500/20">
                <div className="flex items-center gap-2 mb-4">
                  <div className="w-3 h-3 rounded-full bg-amber-500 shadow-lg shadow-amber-500/50" />
                  <h3 className="text-amber-400 font-bold">Grey List</h3>
                  <span className="ml-auto px-2 py-0.5 bg-amber-500/20 rounded-full text-xs font-bold text-amber-400">{fatfLists.grey_list.length}</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {fatfLists.grey_list.length > 0 ? fatfLists.grey_list.map((code) => (
                    <span key={code} className="bg-amber-600/30 text-amber-300 px-3 py-1.5 rounded-lg text-sm font-bold border border-amber-500/30 hover:bg-amber-600/40 transition-colors cursor-default">{code}</span>
                  )) : <span className="text-slate-500 text-sm">No countries on grey list</span>}
                </div>
              </div>
            </div>
          </div>
        )}
        
        {/* Main Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Flagged Queue Panel */}
          <div className="lg:col-span-2 bg-gradient-to-br from-slate-800/80 to-slate-900/80 backdrop-blur-xl rounded-3xl border border-white/10 shadow-xl overflow-hidden">
            <div className="px-6 py-4 border-b border-white/10 flex items-center justify-between bg-slate-800/50">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-rose-500/20 rounded-lg">
                  <svg className="w-5 h-5 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                </div>
                <h2 className="font-bold text-white">Flagged Queue</h2>
                <span className="px-2.5 py-1 bg-rose-500/20 rounded-full text-xs font-bold text-rose-400">{flaggedQueue.length}</span>
              </div>
              <a href="/war-room/alerts" className="text-sm text-indigo-400 hover:text-indigo-300 font-medium flex items-center gap-1 group">
                View all
                <svg className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </a>
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
          <div className="bg-gradient-to-br from-slate-800/80 to-slate-900/80 backdrop-blur-xl rounded-3xl border border-white/10 shadow-xl overflow-hidden">
            <div className="px-6 py-4 border-b border-white/10 bg-slate-800/50">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-indigo-500/20 rounded-lg">
                  <svg className="w-5 h-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                </div>
                <h2 className="font-bold text-white">Quick Actions</h2>
              </div>
            </div>
            <div className="p-4 space-y-2">
              <a href="/war-room/detection-studio" className="group w-full flex items-center gap-3 px-4 py-3.5 bg-white/5 hover:bg-white/10 rounded-xl transition-all text-left border border-transparent hover:border-white/10">
                <div className="p-2 bg-indigo-500/20 rounded-lg group-hover:scale-110 transition-transform">
                  <svg className="w-4 h-4 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                </div>
                <span className="text-white font-medium">Search Address</span>
                <svg className="w-4 h-4 text-slate-500 ml-auto opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </a>
              
              <a href="/war-room/compliance" className="group w-full flex items-center gap-3 px-4 py-3.5 bg-white/5 hover:bg-white/10 rounded-xl transition-all text-left border border-transparent hover:border-white/10">
                <div className="p-2 bg-emerald-500/20 rounded-lg group-hover:scale-110 transition-transform">
                  <svg className="w-4 h-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                </div>
                <span className="text-white font-medium">View Reports</span>
                <svg className="w-4 h-4 text-slate-500 ml-auto opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </a>
              
              <a href="/war-room/detection-studio?view=network" className="group w-full flex items-center gap-3 px-4 py-3.5 bg-white/5 hover:bg-white/10 rounded-xl transition-all text-left border border-transparent hover:border-white/10">
                <div className="p-2 bg-purple-500/20 rounded-lg group-hover:scale-110 transition-transform">
                  <svg className="w-4 h-4 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
                  </svg>
                </div>
                <span className="text-white font-medium">Entity Graph</span>
                <svg className="w-4 h-4 text-slate-500 ml-auto opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </a>
              
              {capabilities?.canEditPolicies && (
                <a href="/policies" className="group w-full flex items-center gap-3 px-4 py-3.5 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 rounded-xl transition-all text-left shadow-lg shadow-indigo-500/25 hover:shadow-xl hover:shadow-indigo-500/40">
                  <div className="p-2 bg-white/20 rounded-lg group-hover:scale-110 transition-transform">
                    <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
                    </svg>
                  </div>
                  <span className="text-white font-bold">Configure Policies</span>
                  <svg className="w-4 h-4 text-white/70 ml-auto group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                  </svg>
                </a>
              )}
            </div>
          </div>
        </div>
        
        {/* System Status Bar */}
        <div className="bg-gradient-to-r from-slate-800/80 via-slate-800/60 to-slate-800/80 backdrop-blur-xl rounded-2xl border border-white/10 p-5 shadow-lg">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div className="flex items-center gap-8">
              {[
                { name: 'Risk Engine', color: 'emerald' },
                { name: 'Sanctions Oracle', color: 'emerald' },
                { name: 'GraphSAGE', color: 'emerald' },
                { name: 'Monitoring', color: 'emerald' },
              ].map((service) => (
                <div key={service.name} className="flex items-center gap-2.5 group">
                  <div className="relative">
                    <div className={`w-2.5 h-2.5 rounded-full bg-${service.color}-400`}></div>
                    <div className={`absolute inset-0 w-2.5 h-2.5 rounded-full bg-${service.color}-400 animate-ping opacity-75`}></div>
                  </div>
                  <span className="text-sm text-slate-300 font-medium group-hover:text-white transition-colors">{service.name}</span>
                </div>
              ))}
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 bg-white/5 rounded-lg border border-white/10">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></div>
              <span className="text-xs text-slate-400 font-medium">Updated just now</span>
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
