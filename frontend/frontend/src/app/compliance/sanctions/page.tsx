'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import AppLayout from '@/components/AppLayout';

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

interface SanctionedEntity {
  name: string;
  type: string;
  source_list: string;
  country?: string;
  added_date?: string;
  aliases?: string[];
}

interface SanctionsListStats {
  total_entities: number;
  by_source: Record<string, number>;
  last_updated: string;
}

const resolveGatewayOrigin = () => {
  const envOrigin = process.env.NEXT_PUBLIC_GATEWAY_ORIGIN;
  if (envOrigin && envOrigin.length > 0) {
    return envOrigin.replace(/\/$/, '');
  }
  if (typeof window === 'undefined') return '';
  const { protocol, hostname, port } = window.location;
  if (port === '3004' || port === '3006') {
    return `${protocol}//${hostname}`;
  }
  return '';
};

const GATEWAY_ORIGIN = resolveGatewayOrigin();
const SANCTIONS_API = `${GATEWAY_ORIGIN}/sanctions`;

export default function SanctionsPage() {
  const [searchType, setSearchType] = useState<'address' | 'name'>('address');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResult, setSearchResult] = useState<SanctionsCheckResult | null>(null);
  const [searchHistory, setSearchHistory] = useState<SanctionsCheckResult[]>([]);
  const [stats, setStats] = useState<SanctionsListStats | null>(null);
  const [recentEntities, setRecentEntities] = useState<SanctionedEntity[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [healthStatus, setHealthStatus] = useState<'checking' | 'healthy' | 'unhealthy'>('checking');

  useEffect(() => {
    checkHealth();
    fetchStats();
  }, []);

  const checkHealth = async () => {
    try {
      const response = await fetch(`${SANCTIONS_API}/health`);
      setHealthStatus(response.ok ? 'healthy' : 'unhealthy');
    } catch {
      setHealthStatus('unhealthy');
    }
  };

  const fetchStats = async () => {
    try {
      const response = await fetch(`${SANCTIONS_API}/stats`);
      if (response.ok) {
        const data = await response.json();
        setStats(data);
      }
    } catch (err) {
      console.error('Failed to fetch sanctions stats:', err);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    setIsLoading(true);
    setError(null);
    setSearchResult(null);

    try {
      const endpoint = searchType === 'address' 
        ? `${SANCTIONS_API}/check/address/${searchQuery.trim()}`
        : `${SANCTIONS_API}/check/name/${encodeURIComponent(searchQuery.trim())}`;

      const response = await fetch(endpoint);
      if (!response.ok) {
        throw new Error(`Sanctions check failed: ${response.status}`);
      }

      const data = await response.json();
      setSearchResult(data);
      setSearchHistory(prev => [data, ...prev.slice(0, 9)]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to perform sanctions check');
    } finally {
      setIsLoading(false);
    }
  };

  const handleBatchCheck = async (addresses: string[]) => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(`${SANCTIONS_API}/check/batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ addresses }),
      });

      if (!response.ok) {
        throw new Error(`Batch check failed: ${response.status}`);
      }

      const data = await response.json();
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to perform batch check');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AppLayout>
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white">🚫 Sanctions Screening</h1>
          <p className="text-gray-400 mt-1">
            Screen addresses and entities against global sanctions lists
          </p>
        </div>
        <div className="flex items-center gap-4">
          <span className={`px-3 py-1 rounded-full text-sm font-medium ${
            healthStatus === 'healthy' ? 'bg-green-500/20 text-green-400' :
            healthStatus === 'unhealthy' ? 'bg-red-500/20 text-red-400' :
            'bg-yellow-500/20 text-yellow-400'
          }`}>
            {healthStatus === 'healthy' ? '● Service Online' :
             healthStatus === 'unhealthy' ? '● Service Offline' :
             '● Checking...'}
          </span>
          <Link
            href="/compliance"
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-white"
          >
            ← Back to Compliance
          </Link>
        </div>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div className="text-2xl font-bold text-white">{stats.total_entities?.toLocaleString() || '—'}</div>
            <div className="text-gray-400 text-sm">Total Sanctioned Entities</div>
          </div>
          <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div className="text-2xl font-bold text-blue-400">{Object.keys(stats.by_source || {}).length || '—'}</div>
            <div className="text-gray-400 text-sm">Source Lists</div>
          </div>
          <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div className="text-2xl font-bold text-green-400">{searchHistory.length}</div>
            <div className="text-gray-400 text-sm">Searches This Session</div>
          </div>
          <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div className="text-2xl font-bold text-purple-400">
              {stats.last_updated ? new Date(stats.last_updated).toLocaleDateString() : '—'}
            </div>
            <div className="text-gray-400 text-sm">Last List Update</div>
          </div>
        </div>
      )}

      {/* Search Form */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700 mb-8">
        <h2 className="text-xl font-semibold text-white mb-4">🔍 Sanctions Check</h2>
        <form onSubmit={handleSearch} className="space-y-4">
          <div className="flex gap-4">
            <div className="flex bg-gray-700 rounded-lg p-1">
              <button
                type="button"
                onClick={() => setSearchType('address')}
                className={`px-4 py-2 rounded-lg transition-colors ${
                  searchType === 'address' 
                    ? 'bg-blue-600 text-white' 
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                Wallet Address
              </button>
              <button
                type="button"
                onClick={() => setSearchType('name')}
                className={`px-4 py-2 rounded-lg transition-colors ${
                  searchType === 'name' 
                    ? 'bg-blue-600 text-white' 
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                Entity Name
              </button>
            </div>
          </div>

          <div className="flex gap-4">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={searchType === 'address' ? '0x...' : 'Enter entity name...'}
              className="flex-1 bg-gray-700 border border-gray-600 rounded-lg px-4 py-3 text-white placeholder-gray-400 focus:outline-none focus:border-blue-500"
            />
            <button
              type="submit"
              disabled={isLoading || !searchQuery.trim()}
              className="px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded-lg text-white font-medium transition-colors"
            >
              {isLoading ? 'Checking...' : 'Screen'}
            </button>
          </div>
        </form>

        {error && (
          <div className="mt-4 p-4 bg-red-500/20 border border-red-500/50 rounded-lg text-red-400">
            ❌ {error}
          </div>
        )}

        {/* Search Result */}
        {searchResult && (
          <div className={`mt-6 p-6 rounded-lg border ${
            searchResult.is_sanctioned 
              ? 'bg-red-500/10 border-red-500/50' 
              : 'bg-green-500/10 border-green-500/50'
          }`}>
            <div className="flex items-center gap-4 mb-4">
              <span className="text-4xl">{searchResult.is_sanctioned ? '🚨' : '✅'}</span>
              <div>
                <h3 className={`text-xl font-bold ${
                  searchResult.is_sanctioned ? 'text-red-400' : 'text-green-400'
                }`}>
                  {searchResult.is_sanctioned ? 'SANCTIONED - DO NOT PROCESS' : 'CLEAR - No Sanctions Match'}
                </h3>
                <p className="text-gray-400">
                  Checked: {new Date(searchResult.check_timestamp).toLocaleString()}
                </p>
              </div>
            </div>

            {searchResult.matches && searchResult.matches.length > 0 && (
              <div className="mt-4">
                <h4 className="text-white font-medium mb-2">Matches Found:</h4>
                <div className="space-y-2">
                  {searchResult.matches.map((match, idx) => (
                    <div key={idx} className="bg-gray-800 rounded p-3">
                      <div className="flex justify-between items-center">
                        <span className="text-white">{match.entity?.name || 'Unknown Entity'}</span>
                        <span className={`px-2 py-1 rounded text-sm ${
                          match.confidence > 0.9 ? 'bg-red-500/30 text-red-400' :
                          match.confidence > 0.7 ? 'bg-yellow-500/30 text-yellow-400' :
                          'bg-gray-600 text-gray-300'
                        }`}>
                          {(match.confidence * 100).toFixed(1)}% match
                        </span>
                      </div>
                      <div className="text-gray-400 text-sm mt-1">
                        Source: {match.entity?.source_list || match.match_type}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Search History */}
      {searchHistory.length > 0 && (
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h2 className="text-xl font-semibold text-white mb-4">📋 Recent Searches</h2>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-gray-400 border-b border-gray-700">
                  <th className="pb-3">Query</th>
                  <th className="pb-3">Type</th>
                  <th className="pb-3">Result</th>
                  <th className="pb-3">Time</th>
                </tr>
              </thead>
              <tbody>
                {searchHistory.map((result, idx) => (
                  <tr key={idx} className="border-b border-gray-700/50">
                    <td className="py-3 text-white font-mono text-sm">
                      {result.query.address || result.query.name}
                    </td>
                    <td className="py-3 text-gray-400">
                      {result.query.address ? 'Address' : 'Name'}
                    </td>
                    <td className="py-3">
                      <span className={`px-2 py-1 rounded text-sm ${
                        result.is_sanctioned 
                          ? 'bg-red-500/30 text-red-400' 
                          : 'bg-green-500/30 text-green-400'
                      }`}>
                        {result.is_sanctioned ? '🚨 Sanctioned' : '✅ Clear'}
                      </span>
                    </td>
                    <td className="py-3 text-gray-400 text-sm">
                      {new Date(result.check_timestamp).toLocaleTimeString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Source Lists */}
      {stats?.by_source && Object.keys(stats.by_source).length > 0 && (
        <div className="mt-8 bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h2 className="text-xl font-semibold text-white mb-4">📚 Active Sanctions Lists</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {Object.entries(stats.by_source).map(([source, count]) => (
              <div key={source} className="bg-gray-700 rounded-lg p-4">
                <div className="text-white font-medium">{source}</div>
                <div className="text-gray-400 text-sm">{count.toLocaleString()} entities</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
    </AppLayout>
  );
}
