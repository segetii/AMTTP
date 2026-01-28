// Improved SIEM Dashboard with React Query, Error Boundaries, and Accessibility
'use client';

import { useState, useMemo, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import dynamic from 'next/dynamic';
import {
  Shield, AlertTriangle, AlertCircle, Activity,
  TrendingUp, TrendingDown, Eye, Ban, Clock,
  Search, Filter, RefreshCw, Settings, Wifi, WifiOff
} from 'lucide-react';
import { useDashboardStats, useAlerts, useTimelineData, useRiskEngineHealth } from '@/lib/hooks';
import type { DashboardStats } from '@/types/siem';
import { ErrorBoundary, StatCardSkeleton, TableRowSkeleton } from './ErrorBoundary';
import { AlertsTableImproved } from './AlertsTableImproved';

// Lazy load heavy chart components
const TimelineChart = dynamic(
  () => import('./TimelineChart').then(mod => ({ default: mod.TimelineChart })),
  {
    loading: () => <ChartSkeleton />,
    ssr: false,
  }
);

const RiskDistributionChart = dynamic(
  () => import('./RiskDistributionChart').then(mod => ({ default: mod.RiskDistributionChart })),
  {
    loading: () => <ChartSkeleton height="h-48" />,
    ssr: false,
  }
);

export function SIEMDashboardImproved() {
  const router = useRouter();
  const [timeRange, setTimeRange] = useState<'1h' | '24h' | '7d' | '30d'>('24h');
  const [selectedRiskLevels, setSelectedRiskLevels] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState('');

  // React Query hooks with automatic refetching and error handling
  const {
    data: stats,
    isLoading: statsLoading,
    isError: statsError,
    refetch: refetchStats,
  } = useDashboardStats();

  const {
    data: alerts = [],
    isLoading: alertsLoading,
    isError: alertsError,
    refetch: refetchAlerts,
  } = useAlerts({ limit: 50 });

  const {
    data: timeline = [],
    isLoading: timelineLoading,
  } = useTimelineData(timeRange);

  const {
    data: healthStatus,
    isError: healthError,
  } = useRiskEngineHealth();

  // Memoized filtered alerts for performance
  const filteredAlerts = useMemo(() => {
    return alerts.filter(alert => {
      if (selectedRiskLevels.length > 0 && !selectedRiskLevels.includes(alert.riskLevel)) {
        return false;
      }
      if (searchQuery && !alert.address.toLowerCase().includes(searchQuery.toLowerCase())) {
        return false;
      }
      return true;
    });
  }, [alerts, selectedRiskLevels, searchQuery]);

  const totalAlertsDisplay = stats?.totalAlerts ?? alerts.length;

  // Refresh all data
  const handleRefresh = useCallback(() => {
    refetchStats();
    refetchAlerts();
  }, [refetchStats, refetchAlerts]);

  // Check for 'ok' OR 'healthy' status - services may return either
  const isOnline = !healthError && (healthStatus?.status === 'ok' || healthStatus?.status === 'healthy');

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-900/50 backdrop-blur sticky top-0 z-50">
        <div className="max-w-[1800px] mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Shield className="w-8 h-8 text-blue-500" aria-hidden="true" />
              <div>
                <h1 className="text-xl font-bold">AMTTP Security Operations</h1>
                <p className="text-sm text-gray-400">Blockchain Fraud Detection & Response</p>
              </div>
              
              {/* Connection Status */}
              <div
                className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium ${
                  isOnline
                    ? 'bg-green-500/20 text-green-400'
                    : 'bg-red-500/20 text-red-400'
                }`}
                role="status"
                aria-live="polite"
              >
                {isOnline ? (
                  <>
                    <Wifi className="w-3 h-3" aria-hidden="true" />
                    <span>Connected</span>
                  </>
                ) : (
                  <>
                    <WifiOff className="w-3 h-3" aria-hidden="true" />
                    <span>Offline</span>
                  </>
                )}
              </div>

              {/* Navigation */}
              <nav className="flex items-center gap-2 ml-4" aria-label="Main navigation">
                <button
                  onClick={() => router.push('/policies')}
                  className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition-colors focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-gray-950"
                  aria-label="Go to policy management"
                >
                  <Settings className="w-4 h-4" aria-hidden="true" />
                  Policies
                </button>
              </nav>
            </div>

            <div className="flex items-center gap-4">
              {/* Search */}
              <div className="relative">
                <label htmlFor="address-search" className="sr-only">
                  Search by address
                </label>
                <Search
                  className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500"
                  aria-hidden="true"
                />
                <input
                  id="address-search"
                  type="search"
                  placeholder="Search address..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 w-64"
                  aria-describedby="search-hint"
                />
                <span id="search-hint" className="sr-only">
                  Enter an Ethereum address to filter alerts
                </span>
              </div>

              {/* Time Range */}
              <fieldset className="flex bg-gray-800 rounded-lg p-1" role="radiogroup" aria-label="Time range">
                <legend className="sr-only">Select time range</legend>
                {(['1h', '24h', '7d', '30d'] as const).map((range) => (
                  <button
                    key={range}
                    onClick={() => setTimeRange(range)}
                    role="radio"
                    aria-checked={timeRange === range}
                    className={`px-3 py-1.5 text-sm rounded-md transition-colors focus:ring-2 focus:ring-blue-500 ${
                      timeRange === range
                        ? 'bg-blue-600 text-white'
                        : 'text-gray-400 hover:text-white'
                    }`}
                  >
                    {range}
                  </button>
                ))}
              </fieldset>

              {/* Manual Refresh */}
              <button
                onClick={handleRefresh}
                disabled={statsLoading || alertsLoading}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-gray-950"
                aria-label={statsLoading || alertsLoading ? 'Loading data' : 'Refresh dashboard data'}
              >
                <RefreshCw
                  className={`w-4 h-4 ${statsLoading || alertsLoading ? 'animate-spin' : ''}`}
                  aria-hidden="true"
                />
                {statsLoading || alertsLoading ? 'Loading...' : 'Refresh'}
              </button>
            </div>
          </div>
        </div>
      </header>

      <main id="main-content" className="max-w-[1800px] mx-auto px-6 py-6 space-y-6">
        {/* Error Banner */}
        {(statsError || alertsError) && (
          <div
            className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center gap-3"
            role="alert"
            aria-live="assertive"
          >
            <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" aria-hidden="true" />
            <div>
              <p className="font-medium text-red-400">Unable to load dashboard data</p>
              <p className="text-sm text-gray-400">
                Some services may be unavailable. Displaying cached or mock data.
              </p>
            </div>
            <button
              onClick={handleRefresh}
              className="ml-auto px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white text-sm rounded transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        {/* Stats Cards */}
        <section aria-labelledby="stats-heading">
          <h2 id="stats-heading" className="sr-only">Dashboard Statistics</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
            {statsLoading ? (
              <>
                {Array.from({ length: 6 }).map((_, i) => (
                  <StatCardSkeleton key={i} />
                ))}
              </>
            ) : (
              <>
                <StatCard
                  title="Total Alerts"
                  value={stats?.totalAlerts ?? 0}
                  icon={<AlertCircle className="w-5 h-5" />}
                  trend={stats?.alertsTrend}
                  color="blue"
                />
                <StatCard
                  title="Critical"
                  value={stats?.criticalAlerts ?? 0}
                  icon={<AlertTriangle className="w-5 h-5" />}
                  color="red"
                  onClick={() => setSelectedRiskLevels(['CRITICAL'])}
                  description="Click to filter critical alerts"
                />
                <StatCard
                  title="High Risk"
                  value={stats?.highAlerts ?? 0}
                  icon={<AlertTriangle className="w-5 h-5" />}
                  color="orange"
                  onClick={() => setSelectedRiskLevels(['HIGH'])}
                  description="Click to filter high risk alerts"
                />
                <StatCard
                  title="Pending"
                  value={stats?.pendingInvestigation ?? 0}
                  icon={<Clock className="w-5 h-5" />}
                  color="yellow"
                />
                <StatCard
                  title="Blocked"
                  value={stats?.blockedAddresses ?? 0}
                  icon={<Ban className="w-5 h-5" />}
                  color="purple"
                />
                <StatCard
                  title="Flagged TX"
                  value={stats?.flaggedTransactions ?? 0}
                  icon={<Eye className="w-5 h-5" />}
                  color="cyan"
                />
              </>
            )}
          </div>
        </section>

        {/* Charts Row */}
        <section aria-labelledby="charts-heading">
          <h2 id="charts-heading" className="sr-only">Alert Analytics</h2>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Timeline Chart */}
            <div className="lg:col-span-2 bg-gray-900 rounded-xl border border-gray-800 p-6">
              <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <Activity className="w-5 h-5 text-blue-400" aria-hidden="true" />
                Alert Timeline
              </h3>
              <ErrorBoundary name="TimelineChart" fallback={<ChartErrorFallback />}>
                {timelineLoading ? (
                  <ChartSkeleton />
                ) : (
                  <TimelineChart data={timeline} />
                )}
              </ErrorBoundary>
            </div>

            {/* Risk Distribution */}
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
              <h3 className="text-lg font-semibold mb-4">Risk Distribution</h3>
              <ErrorBoundary name="RiskDistributionChart" fallback={<ChartErrorFallback />}>
                <RiskDistributionChart stats={stats ?? null} />
              </ErrorBoundary>
            </div>
          </div>
        </section>

        {/* Filters */}
        <section aria-labelledby="filters-heading">
          <h2 id="filters-heading" className="sr-only">Alert Filters</h2>
          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-2 text-sm text-gray-400">
              <Filter className="w-4 h-4" aria-hidden="true" />
              <span id="filter-label">Filter by risk:</span>
            </div>
            <div role="group" aria-labelledby="filter-label" className="flex gap-2 flex-wrap">
              {['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((level) => (
                <button
                  key={level}
                  onClick={() => {
                    setSelectedRiskLevels(prev =>
                      prev.includes(level)
                        ? prev.filter(l => l !== level)
                        : [...prev, level]
                    );
                  }}
                  aria-pressed={selectedRiskLevels.includes(level)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors focus:ring-2 focus:ring-blue-500 ${
                    selectedRiskLevels.includes(level)
                      ? level === 'CRITICAL' ? 'bg-red-600 text-white' :
                        level === 'HIGH' ? 'bg-orange-600 text-white' :
                        level === 'MEDIUM' ? 'bg-yellow-600 text-black' :
                        'bg-green-600 text-white'
                      : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                  }`}
                >
                  {level}
                </button>
              ))}
            </div>
            {selectedRiskLevels.length > 0 && (
              <button
                onClick={() => setSelectedRiskLevels([])}
                className="text-xs text-gray-500 hover:text-gray-300 underline focus:ring-2 focus:ring-blue-500"
              >
                Clear filters
              </button>
            )}
          </div>
        </section>

        {/* Alerts Table */}
        <section aria-labelledby="alerts-heading">
          <div className="bg-gray-900 rounded-xl border border-gray-800">
            <div className="p-4 border-b border-gray-800">
              <h2 id="alerts-heading" className="text-lg font-semibold flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-orange-400" aria-hidden="true" />
                Active Alerts
                <span className="text-sm font-normal text-gray-400">
                  ({filteredAlerts.length} of {totalAlertsDisplay.toLocaleString()})
                </span>
              </h2>
            </div>
            <ErrorBoundary name="AlertsTable" fallback={<TableErrorFallback />}>
              {alertsLoading ? (
                <table className="w-full">
                  <tbody>
                    {Array.from({ length: 5 }).map((_, i) => (
                      <TableRowSkeleton key={i} />
                    ))}
                  </tbody>
                </table>
              ) : (
                <AlertsTableImproved alerts={filteredAlerts} />
              )}
            </ErrorBoundary>
          </div>
        </section>
      </main>
    </div>
  );
}

// Stat Card Component with accessibility improvements
function StatCard({
  title,
  value,
  icon,
  trend,
  color,
  onClick,
  description,
}: {
  title: string;
  value: number;
  icon: React.ReactNode;
  trend?: number;
  color: 'blue' | 'red' | 'orange' | 'yellow' | 'purple' | 'cyan' | 'green';
  onClick?: () => void;
  description?: string;
}) {
  const colorClasses = {
    blue: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    red: 'bg-red-500/10 text-red-400 border-red-500/20',
    orange: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
    yellow: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
    purple: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    cyan: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
    green: 'bg-green-500/10 text-green-400 border-green-500/20',
  };

  const Component = onClick ? 'button' : 'div';

  return (
    <Component
      className={`p-4 rounded-xl border ${colorClasses[color]} ${
        onClick ? 'cursor-pointer hover:bg-opacity-20 transition-colors focus:ring-2 focus:ring-blue-500' : ''
      }`}
      onClick={onClick}
      aria-label={description}
      title={description}
    >
      <div className="flex items-center justify-between mb-2">
        <span aria-hidden="true">{icon}</span>
        {trend !== undefined && (
          <div
            className={`flex items-center text-xs ${trend >= 0 ? 'text-red-400' : 'text-green-400'}`}
            aria-label={`${trend >= 0 ? 'Increased' : 'Decreased'} by ${Math.abs(trend)}%`}
          >
            {trend >= 0 ? (
              <TrendingUp className="w-3 h-3 mr-1" aria-hidden="true" />
            ) : (
              <TrendingDown className="w-3 h-3 mr-1" aria-hidden="true" />
            )}
            {Math.abs(trend)}%
          </div>
        )}
      </div>
      <div className="text-2xl font-bold" aria-label={`${value.toLocaleString()} ${title}`}>
        {value.toLocaleString()}
      </div>
      <div className="text-xs text-gray-400 mt-1">{title}</div>
    </Component>
  );
}

// Skeleton components for loading states
function ChartSkeleton({ height = 'h-64' }: { height?: string }) {
  return (
    <div className={`${height} bg-gray-800/50 rounded-lg animate-pulse flex items-center justify-center`}>
      <span className="text-gray-500 text-sm">Loading chart...</span>
    </div>
  );
}

function ChartErrorFallback() {
  return (
    <div className="h-64 bg-gray-800/50 rounded-lg flex items-center justify-center">
      <div className="text-center">
        <AlertTriangle className="w-8 h-8 text-yellow-400 mx-auto mb-2" />
        <p className="text-gray-400 text-sm">Failed to load chart</p>
      </div>
    </div>
  );
}

function TableErrorFallback() {
  return (
    <div className="p-12 text-center">
      <AlertTriangle className="w-12 h-12 text-yellow-400 mx-auto mb-4" />
      <p className="text-gray-400">Failed to load alerts table</p>
    </div>
  );
}
