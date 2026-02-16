'use client';

/**
 * Detection Studio Page
 * 
 * War Room visualization dashboard
 * RBAC: R3+ required
 * 
 * Visualization Stack (Ground Truth):
 * - ECharts: VelocityHeatmap, TimeSeriesChart, RiskDistributionChart
 * - Reagraph: GraphExplorer (WebGL network)
 * - Unovis: SankeyAuditor (value conservation)
 */

import React, { useState, useCallback, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { useSearchParams } from 'next/navigation';
import { 
  MagnifyingGlassIcon,
  ChartBarIcon,
  ShareIcon,
  CurrencyDollarIcon,
  ClockIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';

// Dynamically import components to avoid SSR issues with canvas/WebGL
const VelocityHeatmap = dynamic(
  () => import('@/components/detection/VelocityHeatmap'),
  { ssr: false, loading: () => <ChartPlaceholder /> }
);

const TimeSeriesChart = dynamic(
  () => import('@/components/detection/TimeSeriesChart'),
  { ssr: false, loading: () => <ChartPlaceholder /> }
);

const RiskDistributionChart = dynamic(
  () => import('@/components/detection/RiskDistributionChart'),
  { ssr: false, loading: () => <ChartPlaceholder /> }
);

const GraphExplorer = dynamic(
  () => import('@/components/detection/GraphExplorer'),
  { ssr: false, loading: () => <ChartPlaceholder height={500} /> }
);

const SankeyAuditor = dynamic(
  () => import('@/components/detection/SankeyAuditor'),
  { ssr: false, loading: () => <ChartPlaceholder height={400} /> }
);

// Import unified data service hooks
import { 
  useSankeyData,
  useGraphData,
  useVelocityData,
  useTimeSeriesData,
  useDistributionData,
} from '@/lib/data-service';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

type ViewMode = 'overview' | 'velocity' | 'network' | 'flow' | 'distribution';

interface ViewTab {
  id: ViewMode;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════════════════════

const VIEW_TABS: ViewTab[] = [
  { 
    id: 'overview', 
    label: 'Overview', 
    icon: ChartBarIcon,
    description: 'All visualizations at a glance'
  },
  { 
    id: 'velocity', 
    label: 'Velocity', 
    icon: ClockIcon,
    description: 'Temporal patterns & bot detection'
  },
  { 
    id: 'network', 
    label: 'Network', 
    icon: ShareIcon,
    description: 'Wallet relationships & layering'
  },
  { 
    id: 'flow', 
    label: 'Flow', 
    icon: CurrencyDollarIcon,
    description: 'Value conservation & smurfing'
  },
  { 
    id: 'distribution', 
    label: 'Distribution', 
    icon: ChartBarIcon,
    description: 'Risk score statistics'
  },
];

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENTS
// ═══════════════════════════════════════════════════════════════════════════════

function ChartPlaceholder({ height = 350 }: { height?: number }) {
  return (
    <div 
      className="bg-surface/50 rounded-lg animate-pulse flex items-center justify-center"
      style={{ height }}
    >
      <div className="text-mutedText">Loading visualization...</div>
    </div>
  );
}

function AlertBanner() {
  return (
    <div className="bg-amber-900/30 border border-amber-600/30 rounded-lg p-4 mb-6">
      <div className="flex items-center gap-3">
        <ExclamationTriangleIcon className="w-6 h-6 text-amber-500" />
        <div>
          <h4 className="font-semibold text-amber-200">3 High-Priority Alerts</h4>
          <p className="text-sm text-amber-300/70">
            Unusual velocity detected in cluster 0x7f2e...3d4c • Possible layering pattern • Review required
          </p>
        </div>
        <button className="ml-auto bg-amber-600 hover:bg-amber-700 text-text px-4 py-2 rounded-lg text-sm">
          Review Alerts
        </button>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function DetectionStudioPage() {
  const searchParams = useSearchParams();
  const viewParam = searchParams.get('view') as ViewMode | null;
  const embedParam = searchParams.get('embed') === 'true';
  const [activeView, setActiveView] = useState<ViewMode>(viewParam || 'overview');
  const [selectedAddress, setSelectedAddress] = useState<string>('');
  
  // Update activeView when URL parameter changes
  useEffect(() => {
    if (viewParam && ['overview', 'velocity', 'network', 'flow', 'distribution'].includes(viewParam)) {
      setActiveView(viewParam);
    }
  }, [viewParam]);
  
  // Use unified data service for all visualization data
  const { data: sankeyData, loading: isLoadingSankey, error: sankeyError } = useSankeyData();
  const { data: graphData, loading: isLoadingGraph } = useGraphData();
  const { data: heatmapData, loading: isLoadingHeatmap } = useVelocityData();
  const { data: timeSeriesData, loading: isLoadingTimeSeries } = useTimeSeriesData();
  const { data: distributionData, loading: isLoadingDistribution } = useDistributionData();
  
  // Ensure graph data is valid before passing to component
  const validGraphData = React.useMemo(() => ({
    nodes: graphData?.nodes?.filter(n => n && n.id) ?? [],
    edges: graphData?.edges?.filter(e => e && e.id && e.source && e.target) ?? [],
  }), [graphData]);
  
  // Handle node selection from graph
  const handleNodeSelect = useCallback((nodeId: string) => {
    setSelectedAddress(nodeId);
    console.log('Selected node:', nodeId);
  }, []);
  
  // Handle heatmap cell click - matches VelocityHeatmap onCellClick signature
  const handleHeatmapClick = useCallback((hour: number, day: number, velocity: number) => {
    console.log('Heatmap cell clicked:', { hour, day, velocity });
  }, []);
  
  // ═══════════════════════════════════════════════════════════════════════════════
  // EMBED MODE: Minimal view for iframe embedding (Flutter app)
  // ═══════════════════════════════════════════════════════════════════════════════
  if (embedParam) {
    return (
      <div className="p-4">
        {/* Flow View (Sankey) */}
        {activeView === 'flow' && (
          <div className="h-full">
            {sankeyError ? (
              <div className="h-[500px] flex items-center justify-center">
                <div className="text-center text-red-400">
                  <p className="font-semibold">Failed to load value flow data</p>
                  <p className="text-sm text-red-300 mt-2">{sankeyError}</p>
                </div>
              </div>
            ) : isLoadingSankey ? (
              <div className="h-[500px] flex items-center justify-center">
                <div className="text-center">
                  <div className="animate-spin h-8 w-8 border-2 border-cyan-500 border-t-transparent rounded-full mx-auto mb-4"></div>
                  <p className="text-mutedText">Loading value flow data...</p>
                </div>
              </div>
            ) : sankeyData.nodes.length === 0 || sankeyData.links.length === 0 ? (
              <div className="h-[500px] flex items-center justify-center text-mutedText">
                No value flow data available
              </div>
            ) : (
              <SankeyAuditor
                nodes={sankeyData.nodes}
                links={sankeyData.links}
                height={Math.max(500, (typeof window !== 'undefined' ? window.innerHeight : 600) - 100)}
              />
            )}
          </div>
        )}
        
        {/* Velocity View (Heatmap) */}
        {activeView === 'velocity' && (
          <div className="h-full">
            {isLoadingHeatmap ? (
              <div className="h-[500px] flex items-center justify-center">
                <div className="animate-spin h-8 w-8 border-2 border-cyan-500 border-t-transparent rounded-full"></div>
              </div>
            ) : (
              <VelocityHeatmap
                data={heatmapData}
                onCellClick={handleHeatmapClick}
              />
            )}
          </div>
        )}
        
        {/* Network View (Graph) */}
        {activeView === 'network' && (
          <div className="h-full">
            {isLoadingGraph ? (
              <div className="h-[600px] flex items-center justify-center">
                <div className="animate-spin h-8 w-8 border-2 border-cyan-500 border-t-transparent rounded-full"></div>
              </div>
            ) : validGraphData.nodes.length > 0 ? (
              <GraphExplorer
                nodes={validGraphData.nodes}
                edges={validGraphData.edges}
                height={Math.max(600, (typeof window !== 'undefined' ? window.innerHeight : 700) - 100)}
                onNodeClick={(node) => handleNodeSelect(node.id)}
              />
            ) : (
              <div className="h-[600px] flex items-center justify-center text-mutedText">No graph data</div>
            )}
          </div>
        )}
        
        {/* Distribution View */}
        {activeView === 'distribution' && (
          <div className="h-full">
            {isLoadingDistribution ? (
              <div className="h-[400px] flex items-center justify-center">
                <div className="animate-spin h-8 w-8 border-2 border-cyan-500 border-t-transparent rounded-full"></div>
              </div>
            ) : distributionData.length > 0 ? (
              <RiskDistributionChart
                data={distributionData}
                title="Risk Score Distribution"
                height={400}
              />
            ) : (
              <div className="h-[400px] flex items-center justify-center text-mutedText">No distribution data</div>
            )}
          </div>
        )}
        
        {/* Overview: show the Sankey Flow as default for embed */}
        {activeView === 'overview' && (
          <div className="h-full">
            {sankeyError ? (
              <div className="h-[500px] flex items-center justify-center">
                <div className="text-center text-red-400">
                  <p className="font-semibold">Failed to load value flow data</p>
                  <p className="text-sm text-red-300 mt-2">{sankeyError}</p>
                </div>
              </div>
            ) : isLoadingSankey ? (
              <div className="h-[500px] flex items-center justify-center">
                <div className="text-center">
                  <div className="animate-spin h-8 w-8 border-2 border-cyan-500 border-t-transparent rounded-full mx-auto mb-4"></div>
                  <p className="text-mutedText">Loading Detection Studio...</p>
                </div>
              </div>
            ) : sankeyData.nodes.length === 0 || sankeyData.links.length === 0 ? (
              <div className="h-[500px] flex items-center justify-center text-mutedText">
                <div className="text-center">
                  <p className="text-lg font-medium mb-2">Detection Studio Ready</p>
                  <p className="text-sm">No active transactions to display</p>
                </div>
              </div>
            ) : (
              <SankeyAuditor
                nodes={sankeyData.nodes}
                links={sankeyData.links}
                height={Math.max(500, (typeof window !== 'undefined' ? window.innerHeight : 600) - 100)}
              />
            )}
          </div>
        )}
      </div>
    );
  }
  
  // ═══════════════════════════════════════════════════════════════════════════════
  // FULL PAGE MODE: Complete dashboard with all chrome
  // ═══════════════════════════════════════════════════════════════════════════════
  return (
    <div className="space-y-6">
      <div>
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-text">Detection Studio</h1>
          <p className="text-mutedText mt-1">
            Advanced visualization workspace for pattern analysis
          </p>
        </div>
        
        {/* Alert Banner */}
        <AlertBanner />
        
        {/* Search Bar */}
        <div className="mb-6">
          <div className="relative max-w-lg">
            <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-mutedText" />
            <input
              type="text"
              placeholder="Search address, transaction, or cluster..."
              value={selectedAddress}
              onChange={(e) => setSelectedAddress(e.target.value)}
              className="w-full bg-surface border border-borderSubtle rounded-lg py-2.5 pl-10 pr-4 
                       text-text placeholder-slate-500 focus:ring-2 focus:ring-cyan-500 focus:border-transparent"
            />
          </div>
        </div>
        
        {/* View Tabs */}
        <div className="flex gap-2 mb-6 border-b border-borderSubtle pb-4">
          {VIEW_TABS.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeView === tab.id;
            
            return (
              <button
                key={tab.id}
                onClick={() => setActiveView(tab.id)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
                  isActive
                    ? 'bg-cyan-600 text-text'
                    : 'bg-surface text-mutedText hover:bg-slate-700 hover:text-text'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span className="text-sm font-medium">{tab.label}</span>
              </button>
            );
          })}
        </div>
        
        {/* Content Area */}
        <div className="space-y-6">
          {/* Overview Mode: All visualizations */}
          {activeView === 'overview' && (
            <div className="space-y-6">
              {/* Row 1: Time Series + Distribution */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="bg-surface/50 rounded-xl p-4 border border-borderSubtle">
                  {isLoadingTimeSeries ? (
                    <div className="h-[360px] flex items-center justify-center">
                      <div className="animate-spin h-8 w-8 border-2 border-cyan-500 border-t-transparent rounded-full"></div>
                    </div>
                  ) : timeSeriesData.length > 0 ? (
                    <TimeSeriesChart
                      data={timeSeriesData}
                      title="Transaction Volume (30 Days)"
                      height={360}
                    />
                  ) : (
                    <div className="h-[360px] flex items-center justify-center text-mutedText">No time series data</div>
                  )}
                </div>
                <div className="bg-surface/50 rounded-xl p-4 border border-borderSubtle">
                  {isLoadingDistribution ? (
                    <div className="h-[360px] flex items-center justify-center">
                      <div className="animate-spin h-8 w-8 border-2 border-cyan-500 border-t-transparent rounded-full"></div>
                    </div>
                  ) : distributionData.length > 0 ? (
                    <RiskDistributionChart
                      data={distributionData}
                      title="Risk Score Distribution"
                      height={360}
                    />
                  ) : (
                    <div className="h-[360px] flex items-center justify-center text-mutedText">No distribution data</div>
                  )}
                </div>
              </div>
              
              {/* Row 2: Velocity Heatmap */}
              <div className="bg-surface/50 rounded-xl p-4 border border-borderSubtle">
                {isLoadingHeatmap ? (
                  <div className="h-[350px] flex items-center justify-center">
                    <div className="animate-spin h-8 w-8 border-2 border-cyan-500 border-t-transparent rounded-full"></div>
                  </div>
                ) : heatmapData.length > 0 ? (
                  <VelocityHeatmap
                    data={heatmapData}
                    title="Velocity Heatmap (Hour × Day)"
                    height={350}
                    onCellClick={handleHeatmapClick}
                  />
                ) : (
                  <div className="h-[350px] flex items-center justify-center text-mutedText">No velocity data</div>
                )}
              </div>
              
              {/* Row 3: Network Graph */}
              <div className="bg-surface/50 rounded-xl p-4 border border-borderSubtle">
                <h3 className="text-lg font-semibold text-text mb-4">Network Explorer</h3>
                {isLoadingGraph ? (
                  <div className="h-[500px] flex items-center justify-center">
                    <div className="animate-spin h-8 w-8 border-2 border-cyan-500 border-t-transparent rounded-full"></div>
                  </div>
                ) : validGraphData.nodes.length > 0 ? (
                  <GraphExplorer
                    nodes={validGraphData.nodes}
                    edges={validGraphData.edges}
                    height={500}
                    onNodeClick={(node) => handleNodeSelect(node.id)}
                  />
                ) : (
                  <div className="h-[500px] flex items-center justify-center text-mutedText">No graph data</div>
                )}
              </div>
            </div>
          )}
          
          {/* Velocity Mode: Heatmap focus */}
          {activeView === 'velocity' && (
            <div className="space-y-6">
              <div className="bg-surface/50 rounded-xl p-6 border border-borderSubtle">
                <div className="mb-4">
                  <h3 className="text-lg font-semibold text-text">Temporal Velocity Analysis</h3>
                  <p className="text-sm text-mutedText mt-1">
                    Hour × Day matrix showing transaction frequency. Red cells indicate anomalous activity.
                    Bot patterns often show consistent activity in unusual hours.
                  </p>
                </div>
                {isLoadingHeatmap ? (
                  <div className="h-[500px] flex items-center justify-center">
                    <div className="animate-spin h-8 w-8 border-2 border-cyan-500 border-t-transparent rounded-full"></div>
                  </div>
                ) : heatmapData.length > 0 ? (
                  <VelocityHeatmap
                    data={heatmapData}
                    height={500}
                    onCellClick={handleHeatmapClick}
                  />
                ) : (
                  <div className="h-[500px] flex items-center justify-center text-mutedText">No velocity data</div>
                )}
              </div>
              
              <div className="bg-surface/50 rounded-xl p-6 border border-borderSubtle">
                {isLoadingTimeSeries ? (
                  <div className="h-[350px] flex items-center justify-center">
                    <div className="animate-spin h-8 w-8 border-2 border-cyan-500 border-t-transparent rounded-full"></div>
                  </div>
                ) : timeSeriesData.length > 0 ? (
                  <TimeSeriesChart
                    data={timeSeriesData}
                    title="Transaction Volume Over Time"
                    height={350}
                  />
                ) : (
                  <div className="h-[350px] flex items-center justify-center text-mutedText">No time series data</div>
                )}
              </div>
            </div>
          )}
          
          {/* Network Mode: Graph focus */}
          {activeView === 'network' && (
            <div className="bg-surface/50 rounded-xl p-6 border border-borderSubtle">
              <div className="mb-4">
                <h3 className="text-lg font-semibold text-text">Network Graph Explorer</h3>
                <p className="text-sm text-mutedText mt-1">
                  WebGL-accelerated graph for exploring wallet relationships.
                  Click nodes to expand. Red edges indicate high-risk transfers.
                </p>
              </div>
              {isLoadingGraph ? (
                <div className="h-[600px] flex items-center justify-center">
                  <div className="animate-spin h-8 w-8 border-2 border-cyan-500 border-t-transparent rounded-full"></div>
                </div>
              ) : validGraphData.nodes.length > 0 ? (
                <GraphExplorer
                  nodes={validGraphData.nodes}
                  edges={validGraphData.edges}
                  height={600}
                  onNodeClick={(node) => handleNodeSelect(node.id)}
                />
              ) : (
                <div className="h-[600px] flex items-center justify-center text-mutedText">No graph data</div>
              )}
              {selectedAddress && (
                <div className="mt-4 p-4 bg-background/50 rounded-lg">
                  <h4 className="text-sm font-medium text-mutedText">Selected Node</h4>
                  <code className="text-cyan-400 text-sm">{selectedAddress}</code>
                </div>
              )}
            </div>
          )}
          
          {/* Flow Mode: Sankey focus */}
          {activeView === 'flow' && (
            <div className="space-y-6">
              <div className="bg-surface/50 rounded-xl p-6 border border-borderSubtle">
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <h3 className="text-lg font-semibold text-text">Value Flow Auditor</h3>
                    <p className="text-sm text-mutedText mt-1">
                      Sankey diagram for value conservation analysis.
                      Money never lies - splits, merges, and smurfing patterns are visible here.
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {isLoadingSankey && (
                      <span className="text-sm text-cyan-400 animate-pulse">Loading from Memgraph...</span>
                    )}
                    <span className="px-2 py-1 bg-emerald-500/20 text-emerald-400 text-xs rounded">
                      Real Data
                    </span>
                  </div>
                </div>
                {sankeyError ? (
                  <div className="h-[500px] flex items-center justify-center">
                    <div className="text-center text-red-400">
                      <p className="font-semibold">Failed to load value flow data</p>
                      <p className="text-sm text-red-300 mt-2">{sankeyError}</p>
                    </div>
                  </div>
                ) : isLoadingSankey ? (
                  <div className="h-[500px] flex items-center justify-center">
                    <div className="text-center">
                      <div className="animate-spin h-8 w-8 border-2 border-cyan-500 border-t-transparent rounded-full mx-auto mb-4"></div>
                      <p className="text-mutedText">Loading value flow data...</p>
                    </div>
                  </div>
                ) : sankeyData.nodes.length === 0 || sankeyData.links.length === 0 ? (
                  <div className="h-[500px] flex items-center justify-center text-mutedText">
                    No value flow data available
                  </div>
                ) : (
                  <SankeyAuditor
                    nodes={sankeyData.nodes}
                    links={sankeyData.links}
                    height={500}
                  />
                )}
              </div>
              
              <div className="bg-surface/50 rounded-xl p-6 border border-borderSubtle">
                <h4 className="text-lg font-semibold text-text mb-4">Flow Statistics</h4>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-background/50 rounded-lg p-4">
                    <div className="text-2xl font-bold text-text">{sankeyData.nodes.length}</div>
                    <div className="text-sm text-mutedText">Unique Addresses</div>
                  </div>
                  <div className="bg-background/50 rounded-lg p-4">
                    <div className="text-2xl font-bold text-text">{sankeyData.links.length}</div>
                    <div className="text-sm text-mutedText">Transfer Links</div>
                  </div>
                  <div className="bg-background/50 rounded-lg p-4">
                    <div className="text-2xl font-bold text-emerald-400">
                      {sankeyData.links.reduce((sum, l) => sum + l.value, 0).toFixed(1)} ETH
                    </div>
                    <div className="text-sm text-mutedText">Total Volume</div>
                  </div>
                  <div className="bg-background/50 rounded-lg p-4">
                    <div className="text-2xl font-bold text-amber-400">
                      {sankeyData.links.filter(l => l.isAnomaly).length}
                    </div>
                    <div className="text-sm text-mutedText">Anomalous Flows</div>
                  </div>
                </div>
              </div>
            </div>
          )}
          
          {/* Distribution Mode */}
          {activeView === 'distribution' && (
            <div className="space-y-6">
              <div className="bg-surface/50 rounded-xl p-6 border border-borderSubtle">
                <div className="mb-4">
                  <h3 className="text-lg font-semibold text-text">Risk Score Distribution</h3>
                  <p className="text-sm text-mutedText mt-1">
                    Statistical view of risk scores across all analyzed addresses.
                    Click bars to drill down into specific risk ranges.
                  </p>
                </div>
                {isLoadingDistribution ? (
                  <div className="h-[400px] flex items-center justify-center">
                    <div className="animate-spin h-8 w-8 border-2 border-cyan-500 border-t-transparent rounded-full"></div>
                  </div>
                ) : distributionData.length > 0 ? (
                  <RiskDistributionChart
                    data={distributionData}
                    height={400}
                    onBarClick={(bucket) => console.log('Clicked bucket:', bucket)}
                  />
                ) : (
                  <div className="h-[400px] flex items-center justify-center text-mutedText">No distribution data</div>
                )}
              </div>
              
              {distributionData.length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="bg-surface/50 rounded-xl p-6 border border-borderSubtle">
                    <h4 className="text-lg font-semibold text-text mb-4">Distribution Summary</h4>
                    <div className="space-y-3">
                      <div className="flex justify-between">
                        <span className="text-mutedText">Low Risk (0-30%)</span>
                        <span className="text-emerald-400 font-medium">
                          {distributionData.slice(0, 3).reduce((s, d) => s + d.count, 0).toLocaleString()}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-mutedText">Medium Risk (30-70%)</span>
                        <span className="text-amber-400 font-medium">
                          {distributionData.slice(3, 7).reduce((s, d) => s + d.count, 0).toLocaleString()}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-mutedText">High Risk (70-100%)</span>
                        <span className="text-red-400 font-medium">
                          {distributionData.slice(7).reduce((s, d) => s + d.count, 0).toLocaleString()}
                        </span>
                      </div>
                    </div>
                  </div>
                  
                  <div className="bg-surface/50 rounded-xl p-6 border border-borderSubtle">
                    <h4 className="text-lg font-semibold text-text mb-4">Key Metrics</h4>
                    <div className="space-y-3">
                      <div className="flex justify-between">
                        <span className="text-mutedText">Total Addresses Analyzed</span>
                        <span className="text-text font-medium">
                          {distributionData.reduce((s, d) => s + d.count, 0).toLocaleString()}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-mutedText">Flagged for Review</span>
                        <span className="text-amber-400 font-medium">142</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-mutedText">Blocked</span>
                        <span className="text-red-400 font-medium">23</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
