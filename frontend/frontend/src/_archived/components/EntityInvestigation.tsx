'use client';

import { useParams } from 'next/navigation';
import { useState, useEffect } from 'react';
import Link from 'next/link';

interface EntityData {
  address: string;
  risk_score: number;
  risk_level: string;
  entity_type: string;
  kyc_status: string;
  transaction_count: number;
  total_volume_eth: number;
  first_seen: string;
  last_active: string;
  flags: string[];
  connections: {
    address: string;
    relationship: string;
    risk_level: string;
  }[];
}

const RISK_COLORS: Record<string, string> = {
  critical: 'bg-red-600 text-white',
  high: 'bg-orange-500 text-white',
  medium: 'bg-yellow-500 text-black',
  low: 'bg-green-500 text-white',
};

export function EntityInvestigation() {
  const params = useParams();
  const address = params?.address as string;
  const [entity, setEntity] = useState<EntityData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (address) {
      loadEntityData();
    }
  }, [address]);

  async function loadEntityData() {
    setLoading(true);
    setError(null);
    try {
      // Resolve API origin for orchestrator
      const getApiOrigin = () => {
        if (typeof window === 'undefined') return '';
        const { protocol, hostname, port } = window.location;
        if (port === '3004' || port === '3006') {
          return `${protocol}//${hostname}:8007`;
        }
        return '';
      };
      const apiOrigin = getApiOrigin();
      
      // Fetch from orchestrator profiles endpoint
      const res = await fetch(`${apiOrigin}/profiles/${address}`);
      if (res.ok) {
        const data = await res.json();
        
        // Determine risk level from entity type and KYC
        let riskLevel = 'medium';
        const riskScore = data.risk_score_cache || 0.5;
        if (riskScore > 0.7) riskLevel = 'high';
        else if (riskScore > 0.85) riskLevel = 'critical';
        else if (riskScore < 0.3) riskLevel = 'low';
        
        setEntity({
          address: data.address || address,
          risk_score: riskScore,
          risk_level: riskLevel,
          entity_type: data.entity_type || 'UNVERIFIED',
          kyc_status: data.kyc_level || 'NONE',
          transaction_count: data.total_transactions || 0,
          total_volume_eth: data.monthly_volume_eth || data.daily_volume_eth || 0,
          first_seen: data.created_at || new Date().toISOString(),
          last_active: data.updated_at || data.last_activity || new Date().toISOString(),
          flags: data.sanctions_checked === false ? ['Sanctions not checked'] : [],
          connections: [],
        });
      } else {
        setError(`Entity not found: ${address}. Register entity in the orchestrator first.`);
        setEntity(null);
      }
    } catch (e) {
      console.error('Failed to load entity:', e);
      setError('Failed to load entity data. Ensure Orchestrator is running on port 8007.');
    }
    setLoading(false);
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="text-white">Loading entity data...</div>
      </div>
    );
  }

  if (error || !entity) {
    return (
      <div className="min-h-screen bg-gray-900 p-6">
        <div className="max-w-4xl mx-auto">
          <div className="bg-red-900/50 border border-red-500 rounded-lg p-6">
            <h2 className="text-xl font-bold text-red-400">Error</h2>
            <p className="text-red-300 mt-2">{error || 'Entity not found'}</p>
            <Link href="/war-room" className="inline-block mt-4 text-blue-400 hover:underline">
              ← Back to War Room
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 p-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <Link href="/war-room" className="text-blue-400 hover:underline text-sm mb-2 inline-block">
              ← Back to War Room
            </Link>
            <h1 className="text-3xl font-bold text-white">🔍 Entity Investigation</h1>
            <p className="text-gray-400 mt-1 font-mono">{address}</p>
          </div>
          <div className={`px-4 py-2 rounded-lg font-semibold ${RISK_COLORS[entity.risk_level]}`}>
            Risk: {entity.risk_level.toUpperCase()} ({(entity.risk_score * 100).toFixed(0)}%)
          </div>
        </div>

        {/* Entity Overview */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <h3 className="text-gray-400 text-sm mb-2">Entity Type</h3>
            <p className="text-white text-xl font-semibold">{entity.entity_type}</p>
          </div>
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <h3 className="text-gray-400 text-sm mb-2">KYC Status</h3>
            <p className="text-white text-xl font-semibold">{entity.kyc_status}</p>
          </div>
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <h3 className="text-gray-400 text-sm mb-2">Total Transactions</h3>
            <p className="text-white text-xl font-semibold">{entity.transaction_count}</p>
          </div>
        </div>

        {/* Activity Stats */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700 mb-8">
          <h2 className="text-xl font-semibold text-white mb-4">📊 Activity Summary</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-gray-400 text-sm">Total Volume</p>
              <p className="text-white text-lg font-semibold">{entity.total_volume_eth.toFixed(2)} ETH</p>
            </div>
            <div>
              <p className="text-gray-400 text-sm">First Seen</p>
              <p className="text-white text-lg">{new Date(entity.first_seen).toLocaleDateString()}</p>
            </div>
            <div>
              <p className="text-gray-400 text-sm">Last Active</p>
              <p className="text-white text-lg">{new Date(entity.last_active).toLocaleDateString()}</p>
            </div>
            <div>
              <p className="text-gray-400 text-sm">Flags</p>
              <p className="text-white text-lg">{entity.flags.length} active</p>
            </div>
          </div>
        </div>

        {/* Flags */}
        {entity.flags.length > 0 && (
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700 mb-8">
            <h2 className="text-xl font-semibold text-white mb-4">🚩 Active Flags</h2>
            <div className="space-y-2">
              {entity.flags.map((flag, idx) => (
                <div key={idx} className="flex items-center gap-2 px-4 py-2 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
                  <span className="text-yellow-400">⚠️</span>
                  <span className="text-yellow-300">{flag}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Connections */}
        {entity.connections.length > 0 && (
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <h2 className="text-xl font-semibold text-white mb-4">🔗 Known Connections</h2>
            <div className="space-y-3">
              {entity.connections.map((conn, idx) => (
                <div key={idx} className="flex items-center justify-between px-4 py-3 bg-gray-700 rounded-lg">
                  <div>
                    <p className="text-white font-mono">{conn.address}</p>
                    <p className="text-gray-400 text-sm">{conn.relationship}</p>
                  </div>
                  <span className={`px-3 py-1 rounded-full text-sm ${RISK_COLORS[conn.risk_level]}`}>
                    {conn.risk_level}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="mt-8 flex gap-4">
          <button className="px-6 py-3 bg-blue-600 hover:bg-blue-700 rounded-lg text-white font-semibold">
            📄 Generate Report
          </button>
          <button className="px-6 py-3 bg-purple-600 hover:bg-purple-700 rounded-lg text-white font-semibold">
            🔍 Deep Analysis
          </button>
          <button className="px-6 py-3 bg-orange-600 hover:bg-orange-700 rounded-lg text-white font-semibold">
            🚨 Flag for Review
          </button>
        </div>
      </div>
    </div>
  );
}
