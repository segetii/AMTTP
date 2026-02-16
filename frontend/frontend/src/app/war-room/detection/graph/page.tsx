'use client';

/**
 * Graph Analysis Page
 * 
 * Network visualization and graph analytics
 * RBAC: R4+ required (Institution, Regulator, Admin)
 */

import React, { useState, useMemo } from 'react';
import dynamic from 'next/dynamic';
import { 
  MagnifyingGlassIcon,
  ArrowPathIcon,
  AdjustmentsHorizontalIcon,
  ShareIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';
import { useGraphData } from '@/lib/data-service';

// Dynamically import graph component to avoid SSR issues
const GraphExplorer = dynamic(
  () => import('@/components/detection/GraphExplorer'),
  { ssr: false, loading: () => <GraphPlaceholder /> }
);

import { generateMockGraphData } from '@/components/detection/GraphExplorer';

// ═══════════════════════════════════════════════════════════════════════════════
// PLACEHOLDER
// ═══════════════════════════════════════════════════════════════════════════════

function GraphPlaceholder() {
  return (
    <div className="h-[600px] bg-surface rounded-lg border border-borderSubtle flex items-center justify-center">
      <div className="text-center">
        <div className="w-12 h-12 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin mx-auto mb-4" />
        <p className="text-mutedText">Loading graph visualization...</p>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function GraphAnalysisPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [depthLevel, setDepthLevel] = useState(2);
  const [showHighRiskOnly, setShowHighRiskOnly] = useState(false);

  // Use real API data with fallback to mock
  const { data: apiGraphData, loading: isLoading, refetch } = useGraphData();
  
  // Fallback to mock data if API returns empty
  const mockData = useMemo(() => generateMockGraphData(), []);
  
  const graphData = useMemo(() => {
    if (apiGraphData?.nodes?.length > 0) {
      return {
        nodes: apiGraphData.nodes.filter((n: any) => n && n.id) ?? [],
        edges: apiGraphData.edges?.filter((e: any) => e && e.id && e.source && e.target) ?? [],
      };
    }
    return mockData;
  }, [apiGraphData, mockData]);

  const handleRefresh = () => {
    refetch();
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    // Handle search
    console.log('Searching for:', searchQuery);
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text">Graph Analysis</h1>
          <p className="text-mutedText mt-1">Explore wallet relationships and transaction networks</p>
        </div>
        <button 
          onClick={handleRefresh}
          disabled={isLoading}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg flex items-center gap-2 transition-colors disabled:opacity-50"
        >
          <ArrowPathIcon className={`w-5 h-5 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-surface rounded-lg p-4 border border-borderSubtle">
          <div className="flex items-center gap-2 text-mutedText text-sm">
            <ShareIcon className="w-4 h-4" />
            <span>Total Nodes</span>
          </div>
          <p className="text-2xl font-bold text-text mt-2">{graphData.nodes.length}</p>
        </div>
        <div className="bg-surface rounded-lg p-4 border border-borderSubtle">
          <div className="flex items-center gap-2 text-mutedText text-sm">
            <ShareIcon className="w-4 h-4" />
            <span>Total Edges</span>
          </div>
          <p className="text-2xl font-bold text-text mt-2">{graphData.edges.length}</p>
        </div>
        <div className="bg-surface rounded-lg p-4 border border-borderSubtle">
          <div className="flex items-center gap-2 text-mutedText text-sm">
            <ExclamationTriangleIcon className="w-4 h-4 text-red-400" />
            <span>High Risk Nodes</span>
          </div>
          <p className="text-2xl font-bold text-red-400 mt-2">
            {graphData.nodes.filter((n) => n.data?.riskScore && n.data.riskScore > 70).length}
          </p>
        </div>
        <div className="bg-surface rounded-lg p-4 border border-borderSubtle">
          <div className="flex items-center gap-2 text-mutedText text-sm">
            <ShareIcon className="w-4 h-4" />
            <span>Clusters Detected</span>
          </div>
          <p className="text-2xl font-bold text-yellow-400 mt-2">3</p>
        </div>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap gap-4 items-center bg-surface rounded-lg p-4 border border-borderSubtle">
        <form onSubmit={handleSearch} className="relative flex-1 max-w-md">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-mutedText" />
          <input
            type="text"
            placeholder="Search wallet address..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-background border border-borderSubtle rounded-lg text-text placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
        </form>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <AdjustmentsHorizontalIcon className="w-5 h-5 text-mutedText" />
            <label className="text-mutedText text-sm">Depth:</label>
            <select
              value={depthLevel}
              onChange={(e) => setDepthLevel(Number(e.target.value))}
              className="bg-background border border-borderSubtle rounded px-3 py-1 text-text text-sm"
            >
              <option value={1}>1 hop</option>
              <option value={2}>2 hops</option>
              <option value={3}>3 hops</option>
              <option value={4}>4 hops</option>
            </select>
          </div>

          <label className="flex items-center gap-2 text-mutedText text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={showHighRiskOnly}
              onChange={(e) => setShowHighRiskOnly(e.target.checked)}
              className="w-4 h-4 rounded bg-background border-borderSubtle text-red-500 focus:ring-red-500"
            />
            High Risk Only
          </label>
        </div>
      </div>

      {/* Graph Visualization */}
      <div className="bg-surface rounded-lg border border-borderSubtle overflow-hidden">
        <div className="p-4 border-b border-borderSubtle flex items-center justify-between">
          <h2 className="text-lg font-semibold text-text">Network Graph</h2>
        </div>
        <div className="h-[600px]">
          <GraphExplorer 
            nodes={graphData.nodes} 
            edges={graphData.edges}
          />
        </div>
      </div>

      {/* Legend */}
      <div className="bg-surface rounded-lg p-4 border border-borderSubtle">
        <h3 className="text-text font-medium mb-3">Graph Legend</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded-full bg-blue-500" />
            <span className="text-mutedText">Wallet</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded bg-purple-500" />
            <span className="text-mutedText">Contract</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded-full bg-orange-500" />
            <span className="text-mutedText">Exchange</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 border-2 border-dashed border-slate-400 rounded" />
            <span className="text-mutedText">Cluster</span>
          </div>
        </div>
      </div>
    </div>
  );
}
