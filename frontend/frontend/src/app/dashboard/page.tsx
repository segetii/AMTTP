'use client';

import { useState, useEffect } from 'react';
import AppLayout, { useProfile } from '@/components/AppLayout';

const ORCHESTRATOR_API = 'http://127.0.0.1:8007';

interface ServiceStatus {
  status: string;
  service: string;
  profiles_loaded?: number;
  connected_services?: Record<string, string>;
}

interface RecentDecision {
  decision_id: string;
  timestamp: string;
  from_address: string;
  to_address: string;
  value_eth: number;
  action: string;
  risk_score: number;
}

function DashboardContent() {
  const { profile, address } = useProfile();
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus | null>(null);
  const [recentDecisions, setRecentDecisions] = useState<RecentDecision[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [healthRes, decisionsRes] = await Promise.all([
        fetch(`${ORCHESTRATOR_API}/health`),
        fetch(`${ORCHESTRATOR_API}/decisions?limit=10`)
      ]);
      
      if (healthRes.ok) setServiceStatus(await healthRes.json());
      if (decisionsRes.ok) {
        const data = await decisionsRes.json();
        setRecentDecisions(data.decisions || []);
      }
    } catch (e) {
      console.error('Failed to load dashboard data:', e);
    }
    setLoading(false);
  }

  const getActionColor = (action: string) => {
    switch (action) {
      case 'APPROVE': return 'bg-green-600';
      case 'ESCROW': return 'bg-yellow-600';
      case 'REVIEW': return 'bg-orange-500';
      case 'BLOCK': return 'bg-red-600';
      case 'REQUIRE_INFO': return 'bg-purple-600';
      default: return 'bg-gray-600';
    }
  };

  return (
    <div>
      <h1 className="text-3xl font-bold mb-2">📊 Dashboard</h1>
      <p className="text-gray-400 mb-6">Welcome to AMTTP Compliance Platform</p>

      {/* Profile Summary */}
      {profile ? (
        <div className="bg-gradient-to-r from-blue-900/50 to-purple-900/50 rounded-lg p-6 mb-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold">{profile.entity_type} Account</h2>
              <p className="text-gray-400 text-sm truncate max-w-md">{profile.address}</p>
            </div>
            <div className="text-right">
              <p className="text-sm text-gray-400">KYC Level</p>
              <p className="text-lg font-bold text-blue-400">{profile.kyc_level}</p>
            </div>
          </div>
          
          <div className="grid grid-cols-4 gap-4 mt-4">
            <div className="bg-gray-800/50 rounded p-3">
              <p className="text-xs text-gray-500">Single TX Limit</p>
              <p className="text-lg font-bold">{profile.single_tx_limit_eth} ETH</p>
            </div>
            <div className="bg-gray-800/50 rounded p-3">
              <p className="text-xs text-gray-500">Daily Limit</p>
              <p className="text-lg font-bold">{profile.daily_limit_eth} ETH</p>
            </div>
            <div className="bg-gray-800/50 rounded p-3">
              <p className="text-xs text-gray-500">Daily Used</p>
              <p className="text-lg font-bold text-yellow-400">{profile.daily_volume_eth.toFixed(2)} ETH</p>
            </div>
            <div className="bg-gray-800/50 rounded p-3">
              <p className="text-xs text-gray-500">Total Transactions</p>
              <p className="text-lg font-bold">{profile.total_transactions}</p>
            </div>
          </div>
        </div>
      ) : (
        <div className="bg-gray-800 rounded-lg p-6 mb-6 text-center">
          <p className="text-gray-400">Connect a wallet address in the sidebar to view your profile</p>
        </div>
      )}

      {/* Service Status */}
      <div className="grid grid-cols-2 gap-6 mb-6">
        <div className="bg-gray-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4">🔧 System Status</h3>
          {loading ? (
            <p className="text-gray-500">Loading...</p>
          ) : serviceStatus ? (
            <div>
              <div className="flex items-center gap-2 mb-4">
                <span className={`w-3 h-3 rounded-full ${serviceStatus.status === 'healthy' ? 'bg-green-500' : 'bg-red-500'}`}></span>
                <span className="font-medium">Orchestrator: {serviceStatus.status}</span>
              </div>
              <div className="space-y-2">
                {serviceStatus.connected_services && Object.entries(serviceStatus.connected_services).map(([service, status]) => (
                  <div key={service} className="flex items-center justify-between text-sm">
                    <span className="text-gray-400 capitalize">{service.replace('_', ' ')}</span>
                    <span className={status === 'healthy' ? 'text-green-400' : 'text-red-400'}>{status}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-red-400">Failed to connect to orchestrator</p>
          )}
        </div>

        <div className="bg-gray-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4">📈 Quick Stats</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-3xl font-bold text-blue-400">{serviceStatus?.profiles_loaded || 0}</p>
              <p className="text-sm text-gray-500">Active Profiles</p>
            </div>
            <div>
              <p className="text-3xl font-bold text-green-400">{recentDecisions.length}</p>
              <p className="text-sm text-gray-500">Recent Decisions</p>
            </div>
            <div>
              <p className="text-3xl font-bold text-yellow-400">
                {recentDecisions.filter(d => d.action === 'APPROVE').length}
              </p>
              <p className="text-sm text-gray-500">Approved</p>
            </div>
            <div>
              <p className="text-3xl font-bold text-red-400">
                {recentDecisions.filter(d => d.action === 'BLOCK').length}
              </p>
              <p className="text-sm text-gray-500">Blocked</p>
            </div>
          </div>
        </div>
      </div>

      {/* Recent Decisions */}
      <div className="bg-gray-800 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">📋 Recent Compliance Decisions</h3>
        {recentDecisions.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-500 border-b border-gray-700">
                  <th className="text-left py-2">Decision ID</th>
                  <th className="text-left py-2">From</th>
                  <th className="text-left py-2">To</th>
                  <th className="text-right py-2">Value</th>
                  <th className="text-center py-2">Action</th>
                  <th className="text-right py-2">Risk</th>
                </tr>
              </thead>
              <tbody>
                {recentDecisions.map((d) => (
                  <tr key={d.decision_id} className="border-b border-gray-700/50">
                    <td className="py-2 font-mono text-xs">{d.decision_id}</td>
                    <td className="py-2 font-mono text-xs truncate max-w-[100px]">{d.from_address}</td>
                    <td className="py-2 font-mono text-xs truncate max-w-[100px]">{d.to_address}</td>
                    <td className="py-2 text-right">{d.value_eth} ETH</td>
                    <td className="py-2 text-center">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${getActionColor(d.action)}`}>
                        {d.action}
                      </span>
                    </td>
                    <td className="py-2 text-right">
                      <span className={d.risk_score > 50 ? 'text-red-400' : 'text-green-400'}>
                        {d.risk_score.toFixed(1)}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-gray-500 text-center py-4">No recent decisions</p>
        )}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <AppLayout>
      <DashboardContent />
    </AppLayout>
  );
}
