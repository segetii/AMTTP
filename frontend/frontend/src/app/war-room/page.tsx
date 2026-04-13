'use client';

/**
 * War Room - Dashboard Page
 * 
 * Main monitoring dashboard for institutional users (R3/R4)
 * 
 * Features:
 * - Live alerts with sparkline trends
 * - Transaction flow summary
 * - System status
 * - Quick actions
 * - Clickable flagged items with explainability modal
 */

import React, { useState, useMemo } from 'react';
import Link from 'next/link';
import dynamic from 'next/dynamic';
import { useAuth } from '@/lib/auth-context';
import { useDashboardStats, useFlaggedQueue, useTimeSeriesData, FlaggedTransaction } from '@/lib/data-service';
import ExplainabilityModal from '@/components/shared/ExplainabilityModal';

const ReactEChartsCore = dynamic(() => import('echarts-for-react'), { ssr: false });

// ═══════════════════════════════════════════════════════════════════════════════
// SPARKLINE COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

function Sparkline({ data, color = '#6366f1', areaColor }: { data: number[]; color?: string; areaColor?: string }) {
  if (!data || data.length < 2) return null;
  const option = useMemo(() => ({
    animation: false,
    grid: { top: 2, right: 0, bottom: 2, left: 0 },
    xAxis: { type: 'category' as const, show: false, data: data.map((_, i) => i) },
    yAxis: { type: 'value' as const, show: false, min: Math.min(...data) * 0.9, max: Math.max(...data) * 1.1 },
    series: [{
      type: 'line',
      data,
      smooth: true,
      symbol: 'none',
      lineStyle: { color, width: 1.5 },
      areaStyle: { color: areaColor || `${color}20` },
    }],
  }), [data, color, areaColor]);
  return <ReactEChartsCore option={option} style={{ height: 32, width: '100%' }} opts={{ renderer: 'svg' }} />;
}

// ═══════════════════════════════════════════════════════════════════════════════
// STAT CARD COMPONENT (with sparkline)
// ═══════════════════════════════════════════════════════════════════════════════

interface StatCardProps {
  label: string;
  value: string;
  change?: string;
  changeType?: 'positive' | 'negative' | 'neutral';
  icon: React.ReactNode;
  sparkData?: number[];
  sparkColor?: string;
}

function StatCard({ label, value, change, changeType = 'neutral', icon, sparkData, sparkColor }: StatCardProps) {
  const changeColors = {
    positive: 'text-green-400',
    negative: 'text-red-400',
    neutral: 'text-mutedText',
  };
  
  return (
    <div className="bg-surface rounded-xl p-4 border border-borderSubtle">
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-mutedText">{label}</p>
          <p className="text-2xl font-bold text-text mt-1">{value}</p>
          {change && (
            <p className={`text-sm mt-1 ${changeColors[changeType]}`}>
              {change}
            </p>
          )}
        </div>
        <div className="text-mutedText">
          {icon}
        </div>
      </div>
      {sparkData && sparkData.length > 1 && (
        <div className="mt-2 -mx-1">
          <Sparkline data={sparkData} color={sparkColor} />
        </div>
      )}
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
            <span className={`px-1.5 py-0.5 text-xs font-bold text-text rounded ${config.badge}`}>
              {item.riskLevel || 'FLAGGED'}
            </span>
            <span className="text-sm font-medium text-text truncate">
              {item.reason || 'Flagged for review'}
            </span>
          </div>
          <p className="text-sm text-mutedText mt-1 line-clamp-2">
            Risk Score: {item.riskScore?.toFixed(1) || 'N/A'} • {item.status?.replace('_', ' ') || 'pending'}
          </p>
          {item.address && (
            <p className="text-xs font-mono text-mutedText mt-1">{item.address}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-mutedText whitespace-nowrap">{timeAgo}</span>
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
            <span className={`px-1.5 py-0.5 text-xs font-bold text-text rounded ${config.badge}`}>
              {alert.type.toUpperCase()}
            </span>
            <span className="text-sm font-medium text-text truncate">{alert.title}</span>
          </div>
          <p className="text-sm text-mutedText mt-1 line-clamp-2">{alert.description}</p>
          {alert.address && (
            <p className="text-xs font-mono text-mutedText mt-1">{alert.address}</p>
          )}
        </div>
        <span className="text-xs text-mutedText whitespace-nowrap">{alert.timestamp}</span>
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
// LIVE SYSTEM STATUS BAR
// ═══════════════════════════════════════════════════════════════════════════════

const SERVICES = [
  { name: 'Orchestrator', prefix: '/api', path: '/health' },
  { name: 'Risk Engine', prefix: '/risk', path: '/health' },
  { name: 'Sanctions', prefix: '/sanctions', path: '/health' },
  { name: 'Monitoring', prefix: '/monitoring', path: '/health' },
  { name: 'Policy', prefix: '/policy', path: '/health' },
  { name: 'FCA', prefix: '/fca', path: '/compliance/health' },
  { name: 'Geo-Risk', prefix: '/geo', path: '/health' },
  { name: 'Integrity', prefix: '/integrity', path: '/health' },
  { name: 'Explainability', prefix: '/explain', path: '/health' },
  { name: 'zkNAF', prefix: '/zknaf', path: '/health' },
  { name: 'Graph', prefix: '/graph', path: '/health' },
  { name: 'Oracle', prefix: '/oracle', path: '/health' },
];

function SystemStatusBar() {
  const [statuses, setStatuses] = React.useState<Record<string, 'up' | 'down' | 'checking'>>(
    Object.fromEntries(SERVICES.map(s => [s.name, 'checking']))
  );
  const [lastChecked, setLastChecked] = React.useState<Date | null>(null);

  React.useEffect(() => {
    const check = async () => {
      const results: Record<string, 'up' | 'down'> = {};
      await Promise.allSettled(SERVICES.map(async svc => {
        try {
          const r = await fetch(`${svc.prefix}${svc.path}`, {
            signal: AbortSignal.timeout(2000),
          });
          results[svc.name] = r.ok ? 'up' : 'down';
        } catch {
          results[svc.name] = 'down';
        }
      }));
      setStatuses(results);
      setLastChecked(new Date());
    };
    check();
    const t = setInterval(check, 30000);
    return () => clearInterval(t);
  }, []);

  const upCount = Object.values(statuses).filter(s => s === 'up').length;

  return (
    <div className="bg-surface rounded-xl border border-borderSubtle p-4">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-6">
          {SERVICES.map(svc => (
            <div key={svc.name} className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${
                statuses[svc.name] === 'up' ? 'bg-green-500' :
                statuses[svc.name] === 'down' ? 'bg-red-500' :
                'bg-gray-500 animate-pulse'
              }`} />
              <span className="text-sm text-slate-300">{svc.name}</span>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <span className={`text-xs px-2 py-1 rounded-full ${
            upCount === SERVICES.length ? 'bg-green-500/10 text-green-400' :
            upCount > 0 ? 'bg-amber-500/10 text-amber-400' :
            'bg-red-500/10 text-red-400'
          }`}>
            {upCount}/{SERVICES.length} online
          </span>
          {lastChecked && (
            <span className="text-sm text-mutedText">
              Updated {lastChecked.toLocaleTimeString()}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function WarRoomDashboard() {
  const { capabilities } = useAuth();
  const { data: stats, loading: statsLoading, error: statsError } = useDashboardStats();
  const { data: flaggedQueue, loading: flaggedLoading, error: flaggedError } = useFlaggedQueue();
  const { data: timeseries } = useTimeSeriesData();
  const [selectedItem, setSelectedItem] = useState<FlaggedTransaction | null>(null);
  
  // Build sparkline data from timeseries
  const txSparkData = useMemo(() => timeseries.map(p => p.value), [timeseries]);
  const riskSparkData = useMemo(() => timeseries.map(p => p.baseline ?? 0), [timeseries]);
  const flagSparkData = useMemo(() =>
    timeseries.map(p => p.isAnomaly ? (p.baseline ?? 0) * 1.5 : (p.baseline ?? 0) * 0.5), [timeseries]);
  const compSparkData = useMemo(() => {
    if (!timeseries.length) return [];
    return timeseries.map(p => {
      const total = p.value || 1;
      const flagged = p.isAnomaly ? total * 0.05 : total * 0.002;
      return ((total - flagged) / total) * 100;
    });
  }, [timeseries]);
  
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
    <>
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-text">War Room Dashboard</h1>
            <p className="text-mutedText mt-1">Real-time monitoring and alerts</p>
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
            sparkData={flagSparkData}
            sparkColor="#f59e0b"
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
            sparkData={txSparkData}
            sparkColor="#22c55e"
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
            sparkData={compSparkData}
            sparkColor="#6366f1"
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
            sparkData={riskSparkData}
            sparkColor="#ef4444"
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
          <div className="lg:col-span-2 bg-surface rounded-xl border border-borderSubtle">
            <div className="px-4 py-3 border-b border-borderSubtle flex items-center justify-between">
              <h2 className="font-semibold text-text">Flagged Queue ({flaggedQueue.length})</h2>
              <Link href="/war-room/alerts" className="text-sm text-indigo-400 hover:text-indigo-300">View all</Link>
            </div>
            <div className="p-4 space-y-3 max-h-96 overflow-y-auto">
              {flaggedError ? (
                <div className="text-center py-8 text-red-400">Failed to load flagged queue. {flaggedError}</div>
              ) : flaggedLoading ? (
                <div className="text-center py-8 text-mutedText">Loading flagged items...</div>
              ) : flaggedQueue.length === 0 ? (
                <div className="text-center py-8 text-mutedText">No flagged items</div>
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
          <div className="bg-surface rounded-xl border border-borderSubtle">
            <div className="px-4 py-3 border-b border-borderSubtle">
              <h2 className="font-semibold text-text">Quick Actions</h2>
            </div>
            <div className="p-4 space-y-3">
              <Link href="/war-room/detection-studio" className="w-full flex items-center gap-3 px-4 py-3 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors text-left">
                <svg className="w-5 h-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                <span className="text-text">Search Address</span>
              </Link>
              
              <Link href="/war-room/compliance" className="w-full flex items-center gap-3 px-4 py-3 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors text-left">
                <svg className="w-5 h-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
                <span className="text-text">View Reports</span>
              </Link>
              
              <Link href="/war-room/detection-studio?view=network" className="w-full flex items-center gap-3 px-4 py-3 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors text-left">
                <svg className="w-5 h-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
                <span className="text-text">Entity Graph</span>
              </Link>
              
              {capabilities?.canEditPolicies && (
                <Link href="/war-room/policies" className="w-full flex items-center gap-3 px-4 py-3 bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors text-left">
                  <svg className="w-5 h-5 text-text" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
                  </svg>
                  <span className="text-text">Configure Policies</span>
                </Link>
              )}
            </div>
          </div>
        </div>
        
        {/* System Status Bar with live checks */}
        <SystemStatusBar />
      </div>
      {/* Explainability Modal */}
      {selectedItem !== null && selectedItem && (
        <ExplainabilityModal
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
          onInvestigate={handleInvestigate}
        />
      )}
    </>
  );
}
