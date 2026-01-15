'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { 
  Shield, AlertTriangle, AlertCircle, Activity, 
  TrendingUp, TrendingDown, Eye, Ban, Clock,
  Search, Filter, RefreshCw, Settings
} from 'lucide-react';
import { fetchDashboardStats, fetchAlerts, fetchTimelineData } from '@/lib/api';
import type { Alert, DashboardStats, TimelineDataPoint } from '@/types/siem';
import { AlertsTable } from './AlertsTable';
import { TimelineChart } from './TimelineChart';
import { RiskDistributionChart } from './RiskDistributionChart';

export function SIEMDashboard() {
  const router = useRouter();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [timeline, setTimeline] = useState<TimelineDataPoint[]>([]);
  const [timeRange, setTimeRange] = useState<'1h' | '24h' | '7d' | '30d'>('24h');
  const [loading, setLoading] = useState(true);
  const [selectedRiskLevels, setSelectedRiskLevels] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [autoRefresh, setAutoRefresh] = useState(true);

  useEffect(() => {
    loadData();
    
    // Auto-refresh every 30 seconds
    const interval = autoRefresh ? setInterval(loadData, 30000) : null;
    return () => { if (interval) clearInterval(interval); };
  }, [timeRange, autoRefresh]);

  async function loadData() {
    setLoading(true);
    try {
      const [statsData, alertsData, timelineData] = await Promise.all([
        fetchDashboardStats(),
        fetchAlerts({ limit: 50 }),
        fetchTimelineData(timeRange)
      ]);
      setStats(statsData);
      setAlerts(alertsData);
      setTimeline(timelineData);
    } catch (error) {
      console.error('Failed to load data:', error);
    }
    setLoading(false);
  }

  const filteredAlerts = alerts.filter(alert => {
    if (selectedRiskLevels.length > 0 && !selectedRiskLevels.includes(alert.riskLevel)) {
      return false;
    }
    if (searchQuery && !alert.address.toLowerCase().includes(searchQuery.toLowerCase())) {
      return false;
    }
    return true;
  });

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-900/50 backdrop-blur sticky top-0 z-50">
        <div className="max-w-[1800px] mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Shield className="w-8 h-8 text-blue-500" />
              <div>
                <h1 className="text-xl font-bold">AMTTP Security Operations</h1>
                <p className="text-sm text-gray-400">Blockchain Fraud Detection & Response</p>
              </div>
              {/* Navigation */}
              <nav className="flex items-center gap-2 ml-8">
                <button
                  onClick={() => router.push('/policies')}
                  className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition-colors"
                >
                  <Settings className="w-4 h-4" />
                  Policies
                </button>
              </nav>
            </div>
            
            <div className="flex items-center gap-4">
              {/* Search */}
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                <input
                  type="text"
                  placeholder="Search address..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-blue-500 w-64"
                />
              </div>
              
              {/* Time Range */}
              <div className="flex bg-gray-800 rounded-lg p-1">
                {(['1h', '24h', '7d', '30d'] as const).map((range) => (
                  <button
                    key={range}
                    onClick={() => setTimeRange(range)}
                    className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                      timeRange === range 
                        ? 'bg-blue-600 text-white' 
                        : 'text-gray-400 hover:text-white'
                    }`}
                  >
                    {range}
                  </button>
                ))}
              </div>
              
              {/* Auto Refresh */}
              <button
                onClick={() => setAutoRefresh(!autoRefresh)}
                className={`p-2 rounded-lg transition-colors ${
                  autoRefresh ? 'bg-green-600/20 text-green-400' : 'bg-gray-800 text-gray-400'
                }`}
                title={autoRefresh ? 'Auto-refresh ON' : 'Auto-refresh OFF'}
              >
                <RefreshCw className={`w-4 h-4 ${autoRefresh ? 'animate-spin' : ''}`} style={{ animationDuration: '3s' }} />
              </button>
              
              {/* Manual Refresh */}
              <button
                onClick={loadData}
                disabled={loading}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
              >
                {loading ? 'Loading...' : 'Refresh'}
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-[1800px] mx-auto px-6 py-6 space-y-6">
        {/* Stats Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
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
          />
          <StatCard
            title="High Risk"
            value={stats?.highAlerts ?? 0}
            icon={<AlertTriangle className="w-5 h-5" />}
            color="orange"
            onClick={() => setSelectedRiskLevels(['HIGH'])}
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
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Timeline Chart */}
          <div className="lg:col-span-2 bg-gray-900 rounded-xl border border-gray-800 p-6">
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <Activity className="w-5 h-5 text-blue-400" />
              Alert Timeline
            </h2>
            <TimelineChart data={timeline} />
          </div>
          
          {/* Risk Distribution */}
          <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
            <h2 className="text-lg font-semibold mb-4">Risk Distribution</h2>
            <RiskDistributionChart stats={stats} />
          </div>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <Filter className="w-4 h-4" />
            Filter by risk:
          </div>
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
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
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
          {selectedRiskLevels.length > 0 && (
            <button
              onClick={() => setSelectedRiskLevels([])}
              className="text-xs text-gray-500 hover:text-gray-300"
            >
              Clear filters
            </button>
          )}
        </div>

        {/* Alerts Table */}
        <div className="bg-gray-900 rounded-xl border border-gray-800">
          <div className="p-4 border-b border-gray-800">
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-orange-400" />
              Active Alerts
              <span className="text-sm font-normal text-gray-400">
                ({filteredAlerts.length} of {alerts.length})
              </span>
            </h2>
          </div>
          <AlertsTable alerts={filteredAlerts} onRefresh={loadData} />
        </div>
      </main>
    </div>
  );
}

// Stat Card Component
function StatCard({ 
  title, 
  value, 
  icon, 
  trend, 
  color,
  onClick 
}: { 
  title: string; 
  value: number; 
  icon: React.ReactNode;
  trend?: number;
  color: 'blue' | 'red' | 'orange' | 'yellow' | 'purple' | 'cyan' | 'green';
  onClick?: () => void;
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

  return (
    <div 
      className={`p-4 rounded-xl border ${colorClasses[color]} ${onClick ? 'cursor-pointer hover:bg-opacity-20 transition-colors' : ''}`}
      onClick={onClick}
    >
      <div className="flex items-center justify-between mb-2">
        {icon}
        {trend !== undefined && (
          <div className={`flex items-center text-xs ${trend >= 0 ? 'text-red-400' : 'text-green-400'}`}>
            {trend >= 0 ? <TrendingUp className="w-3 h-3 mr-1" /> : <TrendingDown className="w-3 h-3 mr-1" />}
            {Math.abs(trend)}%
          </div>
        )}
      </div>
      <div className="text-2xl font-bold">{value.toLocaleString()}</div>
      <div className="text-xs text-gray-400 mt-1">{title}</div>
    </div>
  );
}
