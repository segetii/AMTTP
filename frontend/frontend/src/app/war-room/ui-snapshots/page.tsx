'use client';

import { useState } from 'react';
import Link from 'next/link';

interface UISnapshot {
  id: string;
  name: string;
  description: string;
  page: string;
  capturedBy: string;
  timestamp: string;
  type: 'manual' | 'automated' | 'audit';
  tags: string[];
  thumbnailUrl?: string;
}

export default function UISnapshotsPage() {
  const [snapshots, setSnapshots] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>('No snapshots API endpoint configured');
  const [filter, setFilter] = useState<'all' | 'manual' | 'automated' | 'audit'>('all');
  const [selectedSnapshot, setSelectedSnapshot] = useState<UISnapshot | null>(null);

  const filteredSnapshots = filter === 'all' 
    ? snapshots 
    : snapshots.filter(s => s.type === filter);

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'audit': return 'bg-purple-500/20 text-purple-400';
      case 'automated': return 'bg-blue-500/20 text-blue-400';
      case 'manual': return 'bg-green-500/20 text-green-400';
      default: return 'bg-slate-500/20 text-mutedText';
    }
  };

  const captureSnapshot = () => {
    const newSnapshot: UISnapshot = {
      id: Date.now().toString(),
      name: 'Manual Snapshot',
      description: 'Captured from current page',
      page: window.location.pathname,
      capturedBy: 'you@exchange.com',
      timestamp: new Date().toISOString(),
      type: 'manual',
      tags: ['manual'],
    };
    setSnapshots(prev => [newSnapshot, ...prev]);
  };

  return (
    <div className="space-y-6">
      {error && <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 mb-4 text-red-400 text-sm">⚠ Backend unavailable: {error}</div>}
      {loading && <div className="text-zinc-500 text-sm mb-4">Loading from backend...</div>}
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <Link href="/war-room" className="text-mutedText hover:text-text">
              ← War Room
            </Link>
          </div>
          <h1 className="text-3xl font-bold">UI Snapshots</h1>
          <p className="text-mutedText mt-1">Audit trail of UI states and actions for compliance</p>
        </div>
        <button 
          onClick={captureSnapshot}
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg flex items-center gap-2"
        >
          <span>📸 Capture Snapshot</span>
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <div className="bg-surface rounded-xl p-4 border border-borderSubtle">
          <div className="text-2xl font-bold">{snapshots.length}</div>
          <div className="text-mutedText text-sm">Total Snapshots</div>
        </div>
        <div className="bg-surface rounded-xl p-4 border border-borderSubtle">
          <div className="text-2xl font-bold text-purple-400">{snapshots.filter(s => s.type === 'audit').length}</div>
          <div className="text-mutedText text-sm">Audit Captures</div>
        </div>
        <div className="bg-surface rounded-xl p-4 border border-borderSubtle">
          <div className="text-2xl font-bold text-blue-400">{snapshots.filter(s => s.type === 'automated').length}</div>
          <div className="text-mutedText text-sm">Automated</div>
        </div>
        <div className="bg-surface rounded-xl p-4 border border-borderSubtle">
          <div className="text-2xl font-bold text-green-400">{snapshots.filter(s => s.type === 'manual').length}</div>
          <div className="text-mutedText text-sm">Manual</div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-2 mb-6">
        {(['all', 'audit', 'automated', 'manual'] as const).map(f => (
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

      {/* Snapshots Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredSnapshots.map(snapshot => (
          <div 
            key={snapshot.id} 
            className="bg-surface rounded-xl border border-borderSubtle overflow-hidden hover:border-borderSubtle cursor-pointer transition-colors"
            onClick={() => setSelectedSnapshot(snapshot)}
          >
            {/* Thumbnail placeholder */}
            <div className="h-40 bg-slate-700 flex items-center justify-center">
              <div className="text-4xl opacity-50">🖼️</div>
            </div>
            
            <div className="p-4">
              <div className="flex items-center gap-2 mb-2">
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${getTypeColor(snapshot.type)}`}>
                  {snapshot.type}
                </span>
              </div>
              <h3 className="font-semibold mb-1">{snapshot.name}</h3>
              <p className="text-sm text-mutedText mb-3 line-clamp-2">{snapshot.description}</p>
              
              <div className="flex flex-wrap gap-1 mb-3">
                {snapshot.tags.map(tag => (
                  <span key={tag} className="px-2 py-0.5 bg-slate-700 rounded text-xs text-mutedText">
                    {tag}
                  </span>
                ))}
              </div>
              
              <div className="flex justify-between text-xs text-mutedText">
                <span>{snapshot.capturedBy}</span>
                <span>{snapshot.timestamp}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Detail Modal */}
      {selectedSnapshot && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setSelectedSnapshot(null)}>
          <div className="bg-surface rounded-xl max-w-4xl w-full mx-4 border border-borderSubtle overflow-hidden" onClick={e => e.stopPropagation()}>
            {/* Large preview */}
            <div className="h-96 bg-slate-700 flex items-center justify-center">
              <div className="text-6xl opacity-50">🖼️</div>
            </div>
            
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <h2 className="text-xl font-bold">{selectedSnapshot.name}</h2>
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${getTypeColor(selectedSnapshot.type)}`}>
                      {selectedSnapshot.type}
                    </span>
                  </div>
                  <p className="text-mutedText">{selectedSnapshot.description}</p>
                </div>
              </div>
              
              <div className="grid grid-cols-3 gap-4 mb-4 text-sm">
                <div>
                  <div className="text-mutedText">Page</div>
                  <div className="font-mono">{selectedSnapshot.page}</div>
                </div>
                <div>
                  <div className="text-mutedText">Captured By</div>
                  <div>{selectedSnapshot.capturedBy}</div>
                </div>
                <div>
                  <div className="text-mutedText">Timestamp</div>
                  <div>{selectedSnapshot.timestamp}</div>
                </div>
              </div>
              
              <div className="flex flex-wrap gap-2 mb-6">
                {selectedSnapshot.tags.map(tag => (
                  <span key={tag} className="px-3 py-1 bg-slate-700 rounded-full text-sm text-slate-300">
                    {tag}
                  </span>
                ))}
              </div>
              
              <div className="flex gap-3 justify-end">
                <button onClick={() => setSelectedSnapshot(null)} className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg">
                  Close
                </button>
                <button className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg">
                  Download
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
