'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';

// ═══════════════════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════════════════

interface Report {
  id: string;
  name: string;
  type: 'compliance' | 'transaction' | 'risk' | 'audit' | 'regulatory';
  description: string;
  frequency: 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'on-demand';
  lastGenerated: string;
  status: 'ready' | 'generating' | 'scheduled' | 'error';
  format: 'PDF' | 'CSV' | 'Excel';
  size?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════════════════════

const getTypeColor = (type: string) => {
  switch (type) {
    case 'compliance': return 'bg-purple-500/20 text-purple-400';
    case 'transaction': return 'bg-green-500/20 text-green-400';
    case 'risk': return 'bg-red-500/20 text-red-400';
    case 'audit': return 'bg-blue-500/20 text-blue-400';
    case 'regulatory': return 'bg-orange-500/20 text-orange-400';
    default: return 'bg-slate-500/20 text-mutedText';
  }
};

const getStatusColor = (status: string) => {
  switch (status) {
    case 'ready': return 'bg-green-500/20 text-green-400';
    case 'generating': return 'bg-yellow-500/20 text-yellow-400';
    case 'scheduled': return 'bg-blue-500/20 text-blue-400';
    case 'error': return 'bg-red-500/20 text-red-400';
    default: return 'bg-slate-500/20 text-mutedText';
  }
};

// ═══════════════════════════════════════════════════════════════════════════════
// Component
// ═══════════════════════════════════════════════════════════════════════════════

export default function ReportsPage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>('all');

  useEffect(() => {
    async function loadReports() {
      try {
        const res = await fetch('/app/api/risk/compliance/reports/periodic', {
          credentials: 'same-origin',
          signal: AbortSignal.timeout(8000),
        });
        if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
        const data = await res.json();
        setReports(Array.isArray(data) ? data : []);
      } catch (e) {
        console.warn('[Reports] Backend unavailable:', e);
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    }
    loadReports();
  }, []);

  const filteredReports = filter === 'all'
    ? reports
    : reports.filter(r => r.type === filter);

  const handleGenerate = (id: string) => {
    setReports(prev => prev.map(r =>
      r.id === id ? { ...r, status: 'generating' as const } : r
    ));
    setTimeout(() => {
      setReports(prev => prev.map(r =>
        r.id === id ? { ...r, status: 'ready' as const, lastGenerated: new Date().toISOString() } : r
      ));
    }, 3000);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <Link href="/war-room" className="text-mutedText hover:text-text">
              ← War Room
            </Link>
          </div>
          <h1 className="text-3xl font-bold">Reports</h1>
          <p className="text-mutedText mt-1">Generate and download compliance and analytics reports</p>
        </div>
        <button className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg flex items-center gap-2">
          <span>+ Custom Report</span>
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-2 mb-6">
        {(['all', 'compliance', 'transaction', 'risk', 'audit', 'regulatory'] as const).map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-4 py-2 rounded-lg capitalize transition-colors ${
              filter === f
                ? 'bg-indigo-600 text-text'
                : 'bg-surface text-mutedText hover:bg-slate-700'
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {/* Loading / Error / Empty states */}
      {loading && (
        <div className="flex items-center justify-center py-20">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500" />
          <span className="ml-3 text-mutedText">Loading reports…</span>
        </div>
      )}

      {!loading && error && (
        <div className="bg-surface rounded-xl border border-borderSubtle p-8 text-center">
          <p className="text-yellow-400 text-lg mb-2">Reports Unavailable</p>
          <p className="text-mutedText text-sm mb-4">
            The compliance reporting backend is not reachable right now.
          </p>
          <p className="text-mutedText text-xs font-mono">{error}</p>
          <Link
            href="/war-room/compliance"
            className="inline-block mt-4 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg text-sm"
          >
            Go to Compliance Dashboard →
          </Link>
        </div>
      )}

      {!loading && !error && filteredReports.length === 0 && (
        <div className="bg-surface rounded-xl border border-borderSubtle p-8 text-center">
          <p className="text-mutedText text-lg mb-2">No reports available</p>
          <p className="text-mutedText text-sm">
            Reports will appear here once the compliance engine generates them.
          </p>
          <Link
            href="/war-room/compliance"
            className="inline-block mt-4 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg text-sm"
          >
            Go to Compliance Dashboard →
          </Link>
        </div>
      )}

      {/* Reports Grid */}
      {!loading && filteredReports.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredReports.map(report => (
            <div key={report.id} className="bg-surface rounded-xl p-6 border border-borderSubtle hover:border-borderSubtle transition-colors">
              <div className="flex items-start justify-between mb-4">
                <div className="flex gap-2">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${getTypeColor(report.type)}`}>
                    {report.type}
                  </span>
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${getStatusColor(report.status)}`}>
                    {report.status}
                  </span>
                </div>
                <span className="text-xs text-mutedText">{report.format}</span>
              </div>

              <h3 className="font-semibold mb-2">{report.name}</h3>
              <p className="text-sm text-mutedText mb-4">{report.description}</p>

              <div className="flex justify-between items-center text-xs text-mutedText mb-4">
                <span className="capitalize">{report.frequency}</span>
                <span>Last: {report.lastGenerated}</span>
              </div>

              <div className="flex gap-2">
                {report.status === 'ready' && (
                  <>
                    <button className="flex-1 px-3 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg text-sm">
                      Download {report.size && `(${report.size})`}
                    </button>
                    <button
                      onClick={() => handleGenerate(report.id)}
                      className="px-3 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm"
                    >
                      Regenerate
                    </button>
                  </>
                )}
                {report.status === 'generating' && (
                  <button disabled className="flex-1 px-3 py-2 bg-yellow-600/50 rounded-lg text-sm cursor-wait">
                    Generating...
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Scheduled Reports Section */}
      <div className="mt-8">
        <h2 className="text-xl font-semibold mb-4">Scheduled Reports</h2>
        <div className="bg-surface rounded-xl border border-borderSubtle p-6">
          <div className="grid grid-cols-4 gap-4">
            <div className="text-center">
              <div className="text-3xl font-bold text-green-400">5</div>
              <div className="text-sm text-mutedText">Daily</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-blue-400">3</div>
              <div className="text-sm text-mutedText">Weekly</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-purple-400">2</div>
              <div className="text-sm text-mutedText">Monthly</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-orange-400">1</div>
              <div className="text-sm text-mutedText">Quarterly</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
