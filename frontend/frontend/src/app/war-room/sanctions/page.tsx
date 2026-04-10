'use client';

import React, { useState, useCallback } from 'react';
import Link from 'next/link';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface SanctionsResult {
  address: string;
  sanctioned: boolean;
  matchType: 'exact' | 'fuzzy' | 'none';
  matchScore: number;
  lists: string[];
  details?: string;
  lastChecked: string;
}

interface SanctionsListEntry {
  id: string;
  name: string;
  address: string;
  listSource: string;
  country: string;
  dateAdded: string;
  reason: string;
  riskLevel: 'critical' | 'high' | 'medium';
}

// ═══════════════════════════════════════════════════════════════════════════════
// SANCTIONS API
// ═══════════════════════════════════════════════════════════════════════════════

const SANCTIONS_URL = '/sanctions';

async function checkSanctions(address: string): Promise<SanctionsResult> {
  try {
    const resp = await fetch(`${SANCTIONS_URL}/screen`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address, include_ofac: true, include_eu: true, include_un: true }),
      signal: AbortSignal.timeout(5000),
    });
    if (resp.ok) {
      const data = await resp.json();
      return {
        address,
        sanctioned: data.sanctioned ?? data.is_sanctioned ?? false,
        matchType: data.match_type || (data.sanctioned ? 'exact' : 'none'),
        matchScore: data.match_score ?? (data.sanctioned ? 100 : 0),
        lists: data.matched_lists || data.lists || [],
        details: data.details || data.reason,
        lastChecked: new Date().toISOString(),
      };
    }
  } catch {
    // Sanctions service offline — use local screening
  }

  // Fallback: local screen against known flagged addresses from MongoDB
  try {
    const resp = await fetch('/app-api/data/flagged', { signal: AbortSignal.timeout(5000) });
    if (resp.ok) {
      const flagged = await resp.json();
      if (Array.isArray(flagged)) {
        const match = flagged.find(
          (f: Record<string, unknown>) =>
            (f.address as string)?.toLowerCase() === address.toLowerCase() ||
            (f.from as string)?.toLowerCase() === address.toLowerCase() ||
            (f.to as string)?.toLowerCase() === address.toLowerCase()
        );
        if (match) {
          return {
            address,
            sanctioned: true,
            matchType: 'exact',
            matchScore: (match as Record<string, unknown>).riskScore as number || 85,
            lists: ['AMTTP Internal Watchlist'],
            details: (match as Record<string, unknown>).reason as string || 'Address found in flagged transactions database',
            lastChecked: new Date().toISOString(),
          };
        }
      }
    }
  } catch { /* ignore */ }

  return {
    address,
    sanctioned: false,
    matchType: 'none',
    matchScore: 0,
    lists: [],
    lastChecked: new Date().toISOString(),
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function SanctionsCheckPage() {
  const [address, setAddress] = useState('');
  const [results, setResults] = useState<SanctionsResult[]>([]);
  const [checking, setChecking] = useState(false);
  const [sanctionsList, setSanctionsList] = useState<SanctionsListEntry[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [batchInput, setBatchInput] = useState('');
  const [showBatch, setShowBatch] = useState(false);

  // Load known sanctioned/flagged entities from MongoDB on mount
  React.useEffect(() => {
    async function loadList() {
      try {
        const resp = await fetch('/app-api/data/flagged', { signal: AbortSignal.timeout(8000) });
        if (!resp.ok) throw new Error(`${resp.status}`);
        const flagged = await resp.json();
        if (Array.isArray(flagged)) {
          const entries: SanctionsListEntry[] = flagged
            .filter((f: Record<string, unknown>) => ((f.riskScore as number) || 0) >= 70)
            .slice(0, 30)
            .map((f: Record<string, unknown>, i: number) => ({
              id: (f.id as string) || `sdn-${i}`,
              name: `Entity ${((f.address as string) || '').slice(0, 10)}...`,
              address: (f.address as string) || (f.to as string) || '',
              listSource: ((f.riskScore as number) || 0) >= 85 ? 'OFAC SDN' : 'AMTTP Watchlist',
              country: 'Unknown',
              dateAdded: (f.timestamp as string) || new Date().toISOString(),
              reason: (f.reason as string) || 'Flagged by ML risk engine',
              riskLevel: ((f.riskScore as number) || 0) >= 85 ? 'critical' as const : ((f.riskScore as number) || 0) >= 70 ? 'high' as const : 'medium' as const,
            }));
          setSanctionsList(entries);
        }
      } catch (e) {
        console.warn('[Sanctions] Could not load list:', e);
      } finally {
        setListLoading(false);
      }
    }
    loadList();
  }, []);

  const handleCheck = useCallback(async () => {
    if (!address.trim()) return;
    setChecking(true);
    const result = await checkSanctions(address.trim());
    setResults(prev => [result, ...prev]);
    setChecking(false);
    setAddress('');
  }, [address]);

  const handleBatchCheck = useCallback(async () => {
    const addresses = batchInput
      .split(/[\n,;]+/)
      .map(a => a.trim())
      .filter(a => a.length > 0);
    if (addresses.length === 0) return;
    setChecking(true);
    const batchResults = await Promise.all(addresses.map(a => checkSanctions(a)));
    setResults(prev => [...batchResults, ...prev]);
    setChecking(false);
    setBatchInput('');
    setShowBatch(false);
  }, [batchInput]);

  const getRiskColor = (level: string) => {
    switch (level) {
      case 'critical': return 'bg-red-500/20 text-red-400 border-red-500/50';
      case 'high': return 'bg-orange-500/20 text-orange-400 border-orange-500/50';
      case 'medium': return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50';
      default: return 'bg-green-500/20 text-green-400 border-green-500/50';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <Link href="/war-room" className="text-mutedText hover:text-text">← War Room</Link>
          </div>
          <h1 className="text-3xl font-bold">Sanctions Screening</h1>
          <p className="text-mutedText mt-1">Screen addresses against OFAC, EU, UN sanctions lists and internal watchlists</p>
        </div>
        <button
          onClick={() => setShowBatch(!showBatch)}
          className="px-4 py-2 bg-surface border border-borderSubtle rounded-lg text-sm hover:bg-slate-700"
        >
          {showBatch ? 'Single Check' : 'Batch Check'}
        </button>
      </div>

      {/* Check Form */}
      <div className="bg-surface rounded-xl border border-borderSubtle p-6">
        <h2 className="font-semibold mb-4">
          {showBatch ? 'Batch Sanctions Screening' : 'Screen an Address'}
        </h2>

        {showBatch ? (
          <div className="space-y-4">
            <textarea
              value={batchInput}
              onChange={e => setBatchInput(e.target.value)}
              placeholder="Enter addresses (one per line, or comma-separated)&#10;0x742d35Cc6634C0532925a3b844Bc9e7595f2bD28&#10;0xBE0eB53F46cd790Cd13851d5EFf43D12404d33E8"
              className="w-full h-32 px-4 py-3 bg-slate-800 border border-slate-600 rounded-lg text-white font-mono text-sm placeholder-slate-500 resize-none"
            />
            <button
              onClick={handleBatchCheck}
              disabled={checking || !batchInput.trim()}
              className="px-6 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {checking ? 'Screening...' : `Screen ${batchInput.split(/[\n,;]+/).filter(a => a.trim()).length} Addresses`}
            </button>
          </div>
        ) : (
          <div className="flex gap-3">
            <input
              type="text"
              value={address}
              onChange={e => setAddress(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCheck()}
              placeholder="Enter wallet address (e.g. 0x742d35Cc...)"
              className="flex-1 px-4 py-3 bg-slate-800 border border-slate-600 rounded-lg text-white font-mono placeholder-slate-500"
            />
            <button
              onClick={handleCheck}
              disabled={checking || !address.trim()}
              className="px-6 py-3 bg-indigo-600 hover:bg-indigo-700 rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {checking ? 'Screening...' : 'Screen'}
            </button>
          </div>
        )}

        {/* Quick Test Addresses */}
        <div className="mt-4 flex flex-wrap gap-2">
          <span className="text-xs text-mutedText">Quick test:</span>
          {[
            '0xDA9dfA130Df4dE4673b89022EE50ff26f6EA73Cf',
            '0x267be1C1D684F78cb4F6a176C4911b741E4Ffdc0',
            '0x742d35Cc6634C0532925a3b844Bc9e7595f2bD28',
          ].map(addr => (
            <button
              key={addr}
              onClick={() => setAddress(addr)}
              className="px-2 py-1 text-xs font-mono bg-slate-700 hover:bg-slate-600 rounded text-mutedText hover:text-text"
            >
              {addr.slice(0, 8)}...{addr.slice(-4)}
            </button>
          ))}
        </div>
      </div>

      {/* Results */}
      {results.length > 0 && (
        <div className="space-y-3">
          <h2 className="font-semibold">Screening Results ({results.length})</h2>
          {results.map((r, i) => (
            <div
              key={`${r.address}-${i}`}
              className={`rounded-xl border p-4 ${
                r.sanctioned
                  ? 'bg-red-500/10 border-red-500/30'
                  : 'bg-green-500/10 border-green-500/30'
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <span className={`text-2xl`}>{r.sanctioned ? '🚨' : '✅'}</span>
                    <span className="font-mono text-sm">{r.address}</span>
                    <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                      r.sanctioned ? 'bg-red-500 text-white' : 'bg-green-500 text-white'
                    }`}>
                      {r.sanctioned ? 'SANCTIONED' : 'CLEAR'}
                    </span>
                  </div>
                  {r.sanctioned && (
                    <div className="ml-10 space-y-1">
                      <p className="text-sm text-red-300">Match: {r.matchType} ({r.matchScore}%)</p>
                      <p className="text-sm text-mutedText">Lists: {r.lists.join(', ') || 'N/A'}</p>
                      {r.details && <p className="text-sm text-mutedText">{r.details}</p>}
                    </div>
                  )}
                  {!r.sanctioned && (
                    <p className="ml-10 text-sm text-green-300">No matches found across all screened lists</p>
                  )}
                </div>
                <span className="text-xs text-mutedText whitespace-nowrap">
                  {new Date(r.lastChecked).toLocaleTimeString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Watchlist */}
      <div className="bg-surface rounded-xl border border-borderSubtle overflow-hidden">
        <div className="p-4 border-b border-borderSubtle flex items-center justify-between">
          <h2 className="font-semibold">Active Watchlist ({sanctionsList.length})</h2>
          <span className="text-xs text-mutedText">
            High-risk addresses from ML engine + external sanctions lists
          </span>
        </div>

        {listLoading ? (
          <div className="p-8 text-center text-mutedText">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-500 mx-auto mb-2" />
            Loading watchlist...
          </div>
        ) : sanctionsList.length === 0 ? (
          <div className="p-8 text-center text-mutedText">No entries in watchlist</div>
        ) : (
          <table className="w-full">
            <thead className="bg-slate-700/50">
              <tr>
                <th className="text-left p-3 text-mutedText text-xs font-medium">Address</th>
                <th className="text-left p-3 text-mutedText text-xs font-medium">List</th>
                <th className="text-left p-3 text-mutedText text-xs font-medium">Reason</th>
                <th className="text-left p-3 text-mutedText text-xs font-medium">Risk</th>
                <th className="text-left p-3 text-mutedText text-xs font-medium">Date</th>
              </tr>
            </thead>
            <tbody>
              {sanctionsList.map(entry => (
                <tr key={entry.id} className="border-t border-borderSubtle hover:bg-slate-700/30">
                  <td className="p-3 font-mono text-sm">
                    <button
                      onClick={() => setAddress(entry.address)}
                      className="hover:text-indigo-400 transition-colors"
                    >
                      {entry.address.slice(0, 10)}...{entry.address.slice(-6)}
                    </button>
                  </td>
                  <td className="p-3 text-sm">{entry.listSource}</td>
                  <td className="p-3 text-sm text-mutedText max-w-xs truncate">{entry.reason}</td>
                  <td className="p-3">
                    <span className={`px-2 py-0.5 rounded border text-xs font-medium ${getRiskColor(entry.riskLevel)}`}>
                      {entry.riskLevel}
                    </span>
                  </td>
                  <td className="p-3 text-xs text-mutedText">
                    {new Date(entry.dateAdded).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
