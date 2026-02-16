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
  reasons: string[];
  requires_travel_rule: boolean;
  requires_sar: boolean;
  requires_escrow: boolean;
  escrow_duration_hours: number;
}

function HistoryContent() {
  const { profile, address } = useProfile();
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [loading, setLoading] = useState(true);
  const [backendOffline, setBackendOffline] = useState(false);
  const [filter, setFilter] = useState<string>('all');
  const [selectedDecision, setSelectedDecision] = useState<Decision | null>(null);

  useEffect(() => {
    loadHistory();
  }, []);

  async function loadHistory() {
    setLoading(true);
    try {
      const res = await fetch(`${ORCHESTRATOR_API}/decisions?limit=100`);
      if (res.ok) {
        const data = await res.json();
        setDecisions(data.decisions || []);
      }
    } catch (e) {
      console.warn('[History] Backend unavailable, showing offline state.');
      setBackendOffline(true);
    }
    setLoading(false);
  }

  const getActionColor = (action: string) => {
    switch (action) {
      case 'APPROVE': return 'bg-green-600';
      case 'ESCROW': return 'bg-yellow-600 text-black';
      case 'REVIEW': return 'bg-orange-500';
      case 'BLOCK': return 'bg-red-600';
      case 'REQUIRE_INFO': return 'bg-purple-600';
      default: return 'bg-gray-600';
    }
  };

  const filteredDecisions = decisions.filter(d => {
    if (filter === 'all') return true;
    if (filter === 'mine' && address) {
      return d.from_address.toLowerCase() === address.toLowerCase() ||
             d.to_address.toLowerCase() === address.toLowerCase();
    }
    return d.action === filter;
  });

  const formatDate = (iso: string) => {
    return new Date(iso).toLocaleString();
  };

  return (
    <div>
      <h1 className="text-3xl font-bold mb-2">📜 Transaction History</h1>
      <p className="text-gray-400 mb-6">View compliance decisions and transaction history</p>

      {backendOffline && (
        <div className="bg-yellow-900/30 border border-yellow-700/50 rounded-lg p-3 mb-4 flex items-center gap-2 text-yellow-300 text-sm">
          <span>⚠️</span>
          <span>Backend services are offline. No transaction history available.</span>
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-2 mb-6">
        {[
          { value: 'all', label: 'All' },
          { value: 'mine', label: 'My Transactions' },
          { value: 'APPROVE', label: '✓ Approved' },
          { value: 'BLOCK', label: '✗ Blocked' },
          { value: 'ESCROW', label: '⏳ Escrow' },
          { value: 'REVIEW', label: '👁️ Review' },
        ].map(f => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={`px-4 py-2 rounded text-sm ${
              filter === f.value ? 'bg-blue-600' : 'bg-gray-700 hover:bg-gray-600'
            }`}
          >
            {f.label}
          </button>
        ))}
        <button
          onClick={loadHistory}
          className="ml-auto bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded text-sm"
        >
          🔄 Refresh
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-5 gap-4 mb-6">
        <div className="bg-gray-800 rounded-lg p-4 text-center">
          <p className="text-2xl font-bold">{decisions.length}</p>
          <p className="text-xs text-gray-500">Total</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 text-center">
          <p className="text-2xl font-bold text-green-400">
            {decisions.filter(d => d.action === 'APPROVE').length}
          </p>
          <p className="text-xs text-gray-500">Approved</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 text-center">
          <p className="text-2xl font-bold text-red-400">
            {decisions.filter(d => d.action === 'BLOCK').length}
          </p>
          <p className="text-xs text-gray-500">Blocked</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 text-center">
          <p className="text-2xl font-bold text-yellow-400">
            {decisions.filter(d => d.action === 'ESCROW').length}
          </p>
          <p className="text-xs text-gray-500">Escrow</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 text-center">
          <p className="text-2xl font-bold text-purple-400">
            {decisions.filter(d => d.requires_sar).length}
          </p>
          <p className="text-xs text-gray-500">SAR Required</p>
        </div>
      </div>

      {/* Table */}
      <div className="bg-gray-800 rounded-lg overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-500">Loading...</div>
        ) : filteredDecisions.length === 0 ? (
          <div className="p-8 text-center text-gray-500">No transactions found</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 border-b border-gray-700 bg-gray-900">
                <th className="text-left p-3">Time</th>
                <th className="text-left p-3">Decision ID</th>
                <th className="text-left p-3">From</th>
                <th className="text-left p-3">To</th>
                <th className="text-right p-3">Value</th>
                <th className="text-center p-3">Action</th>
                <th className="text-right p-3">Risk</th>
                <th className="text-center p-3">Flags</th>
              </tr>
            </thead>
            <tbody>
              {filteredDecisions.map((d) => (
                <tr
                  key={d.decision_id}
                  onClick={() => setSelectedDecision(d)}
                  className="border-b border-gray-700/50 hover:bg-gray-700/50 cursor-pointer"
                >
                  <td className="p-3 text-gray-400 text-xs">{formatDate(d.timestamp)}</td>
                  <td className="p-3 font-mono text-xs">{d.decision_id}</td>
                  <td className="p-3 font-mono text-xs truncate max-w-[100px]" title={d.from_address}>
                    {d.from_address.slice(0, 8)}...
                  </td>
                  <td className="p-3 font-mono text-xs truncate max-w-[100px]" title={d.to_address}>
                    {d.to_address.slice(0, 8)}...
                  </td>
                  <td className="p-3 text-right">{d.value_eth} ETH</td>
                  <td className="p-3 text-center">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${getActionColor(d.action)}`}>
                      {d.action}
                    </span>
                  </td>
                  <td className="p-3 text-right">
                    <span className={d.risk_score > 50 ? 'text-red-400' : 'text-green-400'}>
                      {d.risk_score.toFixed(1)}%
                    </span>
                  </td>
                  <td className="p-3 text-center">
                    <div className="flex justify-center gap-1">
                      {d.requires_travel_rule && <span title="Travel Rule" className="text-purple-400">🛂</span>}
                      {d.requires_sar && <span title="SAR Required" className="text-red-400">🚨</span>}
                      {d.requires_escrow && <span title="Escrow" className="text-yellow-400">⏳</span>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Detail Modal */}
      {selectedDecision && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50" onClick={() => setSelectedDecision(null)}>
          <div className="bg-gray-800 rounded-lg p-6 max-w-2xl w-full m-4" onClick={e => e.stopPropagation()}>
            <div className="flex justify-between items-start mb-4">
              <div>
                <h2 className="text-xl font-bold">Decision Details</h2>
                <p className="text-sm text-gray-400 font-mono">{selectedDecision.decision_id}</p>
              </div>
              <button onClick={() => setSelectedDecision(null)} className="text-gray-400 hover:text-white text-xl">×</button>
            </div>

            <div className="grid grid-cols-2 gap-4 mb-4">
              <div className="bg-gray-700 rounded p-3">
                <p className="text-xs text-gray-500">Action</p>
                <span className={`inline-block px-3 py-1 rounded mt-1 ${getActionColor(selectedDecision.action)}`}>
                  {selectedDecision.action}
                </span>
              </div>
              <div className="bg-gray-700 rounded p-3">
                <p className="text-xs text-gray-500">Risk Score</p>
                <p className={`text-2xl font-bold ${selectedDecision.risk_score > 50 ? 'text-red-400' : 'text-green-400'}`}>
                  {selectedDecision.risk_score.toFixed(1)}%
                </p>
              </div>
              <div className="bg-gray-700 rounded p-3">
                <p className="text-xs text-gray-500">From</p>
                <p className="font-mono text-sm break-all">{selectedDecision.from_address}</p>
              </div>
              <div className="bg-gray-700 rounded p-3">
                <p className="text-xs text-gray-500">To</p>
                <p className="font-mono text-sm break-all">{selectedDecision.to_address}</p>
              </div>
              <div className="bg-gray-700 rounded p-3">
                <p className="text-xs text-gray-500">Value</p>
                <p className="text-lg font-bold">{selectedDecision.value_eth} ETH</p>
              </div>
              <div className="bg-gray-700 rounded p-3">
                <p className="text-xs text-gray-500">Timestamp</p>
                <p className="text-sm">{formatDate(selectedDecision.timestamp)}</p>
              </div>
            </div>

            {selectedDecision.reasons.length > 0 && (
              <div className="bg-gray-700 rounded p-3 mb-4">
                <p className="text-xs text-gray-500 mb-2">Compliance Notes</p>
                <ul className="text-sm space-y-1">
                  {selectedDecision.reasons.map((r, i) => (
                    <li key={i} className="text-yellow-400">• {r}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="flex gap-2">
              {selectedDecision.requires_travel_rule && (
                <span className="bg-purple-700 px-3 py-1 rounded text-sm">🛂 Travel Rule</span>
              )}
              {selectedDecision.requires_sar && (
                <span className="bg-red-700 px-3 py-1 rounded text-sm">🚨 SAR Required</span>
              )}
              {selectedDecision.requires_escrow && (
                <span className="bg-yellow-700 px-3 py-1 rounded text-sm text-black">
                  ⏳ Escrow {selectedDecision.escrow_duration_hours}h
                </span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function HistoryPage() {
  return (
    <AppLayout>
      <HistoryContent />
    </AppLayout>
  );
}
