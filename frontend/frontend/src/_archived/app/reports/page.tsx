'use client';

import { useState, useEffect } from 'react';
import AppLayout, { useProfile } from '@/components/AppLayout';

const ORCHESTRATOR_API = 'http://127.0.0.1:8007';

interface Decision {
  decision_id: string;
  timestamp: string;
  from_address: string;
  to_address: string;
  value_eth: number;
  action: string;
  risk_score: number;
  requires_sar: boolean;
}

function ReportsContent() {
  const { profile } = useProfile();
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [loading, setLoading] = useState(true);
  const [backendOffline, setBackendOffline] = useState(false);
  const [dateRange, setDateRange] = useState<'day' | 'week' | 'month' | 'all'>('week');

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const res = await fetch(`${ORCHESTRATOR_API}/decisions?limit=1000`);
      if (res.ok) {
        const data = await res.json();
        setDecisions(data.decisions || []);
      }
    } catch (e) {
      console.warn('[Reports] Backend unavailable, showing offline state.');
      setBackendOffline(true);
    }
    setLoading(false);
  }

  // Filter by date range
  const filterByDate = (d: Decision) => {
    const date = new Date(d.timestamp);
    const now = new Date();
    
    switch (dateRange) {
      case 'day':
        return (now.getTime() - date.getTime()) < 24 * 60 * 60 * 1000;
      case 'week':
        return (now.getTime() - date.getTime()) < 7 * 24 * 60 * 60 * 1000;
      case 'month':
        return (now.getTime() - date.getTime()) < 30 * 24 * 60 * 60 * 1000;
      default:
        return true;
    }
  };

  const filtered = decisions.filter(filterByDate);

  // Calculate stats
  const stats = {
    total: filtered.length,
    approved: filtered.filter(d => d.action === 'APPROVE').length,
    blocked: filtered.filter(d => d.action === 'BLOCK').length,
    escrow: filtered.filter(d => d.action === 'ESCROW').length,
    review: filtered.filter(d => d.action === 'REVIEW').length,
    sarRequired: filtered.filter(d => d.requires_sar).length,
    totalVolume: filtered.reduce((sum, d) => sum + d.value_eth, 0),
    avgRisk: filtered.length > 0 
      ? filtered.reduce((sum, d) => sum + d.risk_score, 0) / filtered.length 
      : 0,
    highRisk: filtered.filter(d => d.risk_score > 70).length,
  };

  // Access check
  if (!profile || !['INSTITUTIONAL', 'VASP', 'HIGH_NET_WORTH'].includes(profile.entity_type)) {
    return (
      <div className="bg-gray-800 rounded-lg p-8 text-center">
        <h2 className="text-xl font-semibold mb-2">🚫 Access Restricted</h2>
        <p className="text-gray-400">
          Reports are only available for INSTITUTIONAL, VASP, and HIGH_NET_WORTH accounts.
        </p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-3xl font-bold mb-2">📈 Compliance Reports</h1>
      <p className="text-gray-400 mb-6">Transaction analytics and compliance metrics</p>

      {backendOffline && (
        <div className="bg-yellow-900/30 border border-yellow-700/50 rounded-lg p-3 mb-4 flex items-center gap-2 text-yellow-300 text-sm">
          <span>⚠️</span>
          <span>Backend services are offline. No report data available.</span>
        </div>
      )}

      {/* Date Range Filter */}
      <div className="flex gap-2 mb-6">
        {[
          { value: 'day', label: 'Last 24h' },
          { value: 'week', label: 'Last 7 Days' },
          { value: 'month', label: 'Last 30 Days' },
          { value: 'all', label: 'All Time' },
        ].map(r => (
          <button
            key={r.value}
            onClick={() => setDateRange(r.value as typeof dateRange)}
            className={`px-4 py-2 rounded text-sm ${
              dateRange === r.value ? 'bg-blue-600' : 'bg-gray-700 hover:bg-gray-600'
            }`}
          >
            {r.label}
          </button>
        ))}
        <button
          onClick={loadData}
          className="ml-auto bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded text-sm"
        >
          🔄 Refresh
        </button>
      </div>

      {loading ? (
        <div className="text-center py-8 text-gray-500">Loading...</div>
      ) : (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-4 gap-4 mb-6">
            <div className="bg-gradient-to-br from-blue-900 to-blue-800 rounded-lg p-4">
              <p className="text-3xl font-bold">{stats.total}</p>
              <p className="text-sm text-blue-300">Total Decisions</p>
            </div>
            <div className="bg-gradient-to-br from-green-900 to-green-800 rounded-lg p-4">
              <p className="text-3xl font-bold">{stats.totalVolume.toFixed(2)} ETH</p>
              <p className="text-sm text-green-300">Total Volume</p>
            </div>
            <div className="bg-gradient-to-br from-purple-900 to-purple-800 rounded-lg p-4">
              <p className="text-3xl font-bold">{stats.avgRisk.toFixed(1)}%</p>
              <p className="text-sm text-purple-300">Avg Risk Score</p>
            </div>
            <div className="bg-gradient-to-br from-red-900 to-red-800 rounded-lg p-4">
              <p className="text-3xl font-bold">{stats.sarRequired}</p>
              <p className="text-sm text-red-300">SAR Required</p>
            </div>
          </div>

          {/* Action Breakdown */}
          <div className="grid grid-cols-2 gap-6 mb-6">
            <div className="bg-gray-800 rounded-lg p-6">
              <h3 className="text-lg font-semibold mb-4">Decision Breakdown</h3>
              <div className="space-y-3">
                {[
                  { label: 'Approved', value: stats.approved, color: 'bg-green-500', percent: (stats.approved / stats.total * 100) || 0 },
                  { label: 'Blocked', value: stats.blocked, color: 'bg-red-500', percent: (stats.blocked / stats.total * 100) || 0 },
                  { label: 'Escrow', value: stats.escrow, color: 'bg-yellow-500', percent: (stats.escrow / stats.total * 100) || 0 },
                  { label: 'Review', value: stats.review, color: 'bg-orange-500', percent: (stats.review / stats.total * 100) || 0 },
                ].map(item => (
                  <div key={item.label}>
                    <div className="flex justify-between text-sm mb-1">
                      <span>{item.label}</span>
                      <span>{item.value} ({item.percent.toFixed(1)}%)</span>
                    </div>
                    <div className="h-2 bg-gray-700 rounded overflow-hidden">
                      <div className={`h-full ${item.color}`} style={{ width: `${item.percent}%` }}></div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="bg-gray-800 rounded-lg p-6">
              <h3 className="text-lg font-semibold mb-4">Risk Distribution</h3>
              <div className="space-y-3">
                {[
                  { label: 'Low Risk (0-30%)', count: filtered.filter(d => d.risk_score <= 30).length, color: 'bg-green-500' },
                  { label: 'Medium Risk (30-50%)', count: filtered.filter(d => d.risk_score > 30 && d.risk_score <= 50).length, color: 'bg-yellow-500' },
                  { label: 'High Risk (50-70%)', count: filtered.filter(d => d.risk_score > 50 && d.risk_score <= 70).length, color: 'bg-orange-500' },
                  { label: 'Critical Risk (70%+)', count: filtered.filter(d => d.risk_score > 70).length, color: 'bg-red-500' },
                ].map(item => (
                  <div key={item.label}>
                    <div className="flex justify-between text-sm mb-1">
                      <span>{item.label}</span>
                      <span>{item.count}</span>
                    </div>
                    <div className="h-2 bg-gray-700 rounded overflow-hidden">
                      <div 
                        className={`h-full ${item.color}`} 
                        style={{ width: `${stats.total > 0 ? (item.count / stats.total * 100) : 0}%` }}
                      ></div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Key Metrics */}
          <div className="bg-gray-800 rounded-lg p-6 mb-6">
            <h3 className="text-lg font-semibold mb-4">Key Metrics</h3>
            <div className="grid grid-cols-5 gap-4">
              <div className="text-center p-4 bg-gray-700 rounded">
                <p className="text-2xl font-bold text-green-400">
                  {stats.total > 0 ? ((stats.approved / stats.total) * 100).toFixed(1) : 0}%
                </p>
                <p className="text-xs text-gray-400">Approval Rate</p>
              </div>
              <div className="text-center p-4 bg-gray-700 rounded">
                <p className="text-2xl font-bold text-red-400">
                  {stats.total > 0 ? ((stats.blocked / stats.total) * 100).toFixed(1) : 0}%
                </p>
                <p className="text-xs text-gray-400">Block Rate</p>
              </div>
              <div className="text-center p-4 bg-gray-700 rounded">
                <p className="text-2xl font-bold text-yellow-400">{stats.highRisk}</p>
                <p className="text-xs text-gray-400">High Risk TXs</p>
              </div>
              <div className="text-center p-4 bg-gray-700 rounded">
                <p className="text-2xl font-bold">
                  {stats.total > 0 ? (stats.totalVolume / stats.total).toFixed(3) : 0}
                </p>
                <p className="text-xs text-gray-400">Avg TX (ETH)</p>
              </div>
              <div className="text-center p-4 bg-gray-700 rounded">
                <p className="text-2xl font-bold text-purple-400">{stats.sarRequired}</p>
                <p className="text-xs text-gray-400">SAR Filings</p>
              </div>
            </div>
          </div>

          {/* Export */}
          <div className="flex justify-end gap-2">
            <button className="bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded text-sm">
              📄 Export CSV
            </button>
            <button className="bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded text-sm">
              📊 Export PDF
            </button>
            <button className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded text-sm">
              📧 Schedule Report
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export default function ReportsPage() {
  return (
    <AppLayout>
      <ReportsContent />
    </AppLayout>
  );
}
