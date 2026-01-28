'use client';

/**
 * Graph Explorer Component
 * Reagraph (WebGL) based network visualization for wallet relationships
 * Used in War Room - Detection Studio
 */

import React, { useState, useCallback, useMemo, Component, ReactNode, useEffect } from 'react';
import dynamic from 'next/dynamic';
import type { GraphCanvasRef, InternalGraphNode, Theme } from 'reagraph';

// Error Boundary for WebGL errors
interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

class GraphErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="flex items-center justify-center h-full bg-slate-900 rounded-lg border border-slate-700">
          <div className="text-center p-8">
            <div className="text-red-400 text-lg mb-2">Graph Visualization Error</div>
            <div className="text-slate-400 text-sm">
              {this.state.error?.message || 'WebGL rendering failed'}
            </div>
            <button
              onClick={() => this.setState({ hasError: false, error: null })}
              className="mt-4 px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700"
            >
              Retry
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

// Dynamic import with SSR disabled for WebGL
const GraphCanvas = dynamic(
  () => import('reagraph').then((mod) => mod.GraphCanvas),
  { ssr: false, loading: () => <GraphLoadingPlaceholder /> }
);

function GraphLoadingPlaceholder() {
  return (
    <div className="flex items-center justify-center h-full bg-slate-900 rounded-lg">
      <div className="text-slate-400">Loading graph visualization...</div>
    </div>
  );
}

// Wrapper component for safe graph rendering with ref forwarding
interface SafeGraphProps {
  nodes: Array<{ id: string; label: string; fill: string; data?: unknown }>;
  edges: Array<{ id: string; source: string; target: string; label?: string; data?: unknown }>;
  onNodeClick?: (node: InternalGraphNode) => void;
  onReady?: (ref: GraphCanvasRef) => void;
}

function SafeGraphCanvas({ nodes, edges, onNodeClick, onReady }: SafeGraphProps) {
  const internalRef = React.useRef<GraphCanvasRef>(null);
  const [hasError, setHasError] = useState(false);
  const [isReady, setIsReady] = useState(false);

  // Wait for next tick to ensure stable render
  useEffect(() => {
    const timer = setTimeout(() => setIsReady(true), 50);
    return () => clearTimeout(timer);
  }, []);

  // Notify parent when ref is available
  useEffect(() => {
    if (isReady && internalRef.current && onReady) {
      onReady(internalRef.current);
    }
  }, [isReady, onReady]);

  // Reset error state if data changes
  useEffect(() => {
    setHasError(false);
  }, [nodes.length, edges.length]);

  if (hasError) {
    return (
      <div className="flex items-center justify-center h-full bg-slate-900 rounded-lg">
        <div className="text-center p-4">
          <div className="text-amber-400 mb-2">Graph rendering issue</div>
          <button 
            onClick={() => setHasError(false)}
            className="px-3 py-1 bg-indigo-600 text-white rounded text-sm"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!isReady || nodes.length === 0) {
    return <GraphLoadingPlaceholder />;
  }

  // Final validation - ensure no null/undefined in critical fields
  const safeNodes = nodes.filter(n => n.id && n.label && n.fill);
  const safeEdges = edges.filter(e => e.id && e.source && e.target);

  if (safeNodes.length === 0) {
    return <GraphLoadingPlaceholder />;
  }

  try {
    return (
      <GraphCanvas
        ref={internalRef}
        nodes={safeNodes}
        edges={safeEdges}
        theme={GRAPH_THEME as Theme}
        layoutType="forceDirected2d"
        // Disable labels to avoid Three.js texture creation issues
        labelType="none"
        draggable
        animated={false}
        onNodeClick={onNodeClick}
      />
    );
  } catch {
    setHasError(true);
    return <GraphLoadingPlaceholder />;
  }
}

// Theme configuration for reagraph - partial theme (only custom overrides)
const GRAPH_THEME: Partial<Theme> = {
  canvas: { background: '#0f172a' },
  node: {
    fill: '#6366f1',
    activeFill: '#818cf8',
    opacity: 1,
    selectedOpacity: 1,
    inactiveOpacity: 0.3,
    label: {
      color: '#f1f5f9',
      stroke: '#0f172a',
      activeColor: '#ffffff',
    },
  },
  edge: {
    fill: '#475569',
    activeFill: '#6366f1',
    opacity: 1,
    selectedOpacity: 1,
    inactiveOpacity: 0.2,
    label: {
      color: '#94a3b8',
      stroke: '#0f172a',
      activeColor: '#ffffff',
    },
  },
  ring: { fill: '#22c55e', activeFill: '#4ade80' },
  arrow: { fill: '#475569', activeFill: '#6366f1' },
  lasso: { border: '#6366f1', background: 'rgba(99, 102, 241, 0.1)' },
  cluster: { stroke: '#475569', fill: 'rgba(71, 85, 105, 0.2)', label: { color: '#f1f5f9' } },
};

// Types - exported for use in pages
export interface WalletNode {
  id: string;
  label: string;
  data?: {
    type: 'wallet' | 'contract' | 'exchange' | 'flagged';
    riskScore?: number;
    balance?: number;
    transactionCount?: number;
  };
}

export interface TransactionEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  data?: {
    amount?: number;
    timestamp?: number;
    txHash?: string;
  };
}

interface GraphExplorerProps {
  initialAddress?: string;
  nodes?: WalletNode[];
  edges?: TransactionEdge[];
  onNodeSelect?: (node: WalletNode | null) => void;
  onNodeClick?: (node: WalletNode) => void;
  height?: number;
  className?: string;
}

// Stable mock data - generated once with deterministic values
const MOCK_NODES: WalletNode[] = [
  { id: 'wallet-1', label: '0x1a2b3c4d...', data: { type: 'wallet', riskScore: 25, balance: 150.5, transactionCount: 42 } },
  { id: 'wallet-2', label: '0x2b3c4d5e...', data: { type: 'wallet', riskScore: 15, balance: 320.8, transactionCount: 128 } },
  { id: 'exchange-1', label: '0x3c4d5e6f...', data: { type: 'exchange', riskScore: 5, balance: 5000.0, transactionCount: 1500 } },
  { id: 'contract-1', label: '0x4d5e6f7a...', data: { type: 'contract', riskScore: 45, balance: 890.2, transactionCount: 350 } },
  { id: 'wallet-3', label: '0x5e6f7a8b...', data: { type: 'wallet', riskScore: 72, balance: 45.3, transactionCount: 89 } },
  { id: 'flagged-1', label: '0x6f7a8b9c...', data: { type: 'flagged', riskScore: 95, balance: 1200.0, transactionCount: 230 } },
  { id: 'wallet-4', label: '0x7a8b9c0d...', data: { type: 'wallet', riskScore: 30, balance: 780.5, transactionCount: 156 } },
  { id: 'contract-2', label: '0x8b9c0d1e...', data: { type: 'contract', riskScore: 55, balance: 2100.0, transactionCount: 890 } },
  { id: 'exchange-2', label: '0x9c0d1e2f...', data: { type: 'exchange', riskScore: 8, balance: 8500.0, transactionCount: 2500 } },
  { id: 'wallet-5', label: '0x0d1e2f3a...', data: { type: 'wallet', riskScore: 85, balance: 95.2, transactionCount: 67 } },
  { id: 'flagged-2', label: '0x1e2f3a4b...', data: { type: 'flagged', riskScore: 92, balance: 560.8, transactionCount: 145 } },
  { id: 'wallet-6', label: '0x2f3a4b5c...', data: { type: 'wallet', riskScore: 18, balance: 420.0, transactionCount: 203 } },
];

const MOCK_EDGES: TransactionEdge[] = [
  { id: 'edge-1', source: 'wallet-1', target: 'exchange-1', label: '2.5 ETH', data: { amount: 2.5, timestamp: Date.now() - 86400000 } },
  { id: 'edge-2', source: 'exchange-1', target: 'wallet-2', label: '5.0 ETH', data: { amount: 5.0, timestamp: Date.now() - 172800000 } },
  { id: 'edge-3', source: 'wallet-2', target: 'contract-1', label: '1.2 ETH', data: { amount: 1.2, timestamp: Date.now() - 259200000 } },
  { id: 'edge-4', source: 'contract-1', target: 'wallet-3', label: '0.8 ETH', data: { amount: 0.8, timestamp: Date.now() - 345600000 } },
  { id: 'edge-5', source: 'wallet-3', target: 'flagged-1', label: '3.5 ETH', data: { amount: 3.5, timestamp: Date.now() - 432000000 } },
  { id: 'edge-6', source: 'flagged-1', target: 'wallet-4', label: '1.8 ETH', data: { amount: 1.8, timestamp: Date.now() - 518400000 } },
  { id: 'edge-7', source: 'wallet-4', target: 'contract-2', label: '4.2 ETH', data: { amount: 4.2, timestamp: Date.now() - 604800000 } },
  { id: 'edge-8', source: 'contract-2', target: 'exchange-2', label: '10.0 ETH', data: { amount: 10.0, timestamp: Date.now() - 691200000 } },
  { id: 'edge-9', source: 'exchange-2', target: 'wallet-5', label: '0.5 ETH', data: { amount: 0.5, timestamp: Date.now() - 777600000 } },
  { id: 'edge-10', source: 'wallet-5', target: 'flagged-2', label: '2.0 ETH', data: { amount: 2.0, timestamp: Date.now() - 864000000 } },
  { id: 'edge-11', source: 'flagged-2', target: 'wallet-6', label: '1.5 ETH', data: { amount: 1.5, timestamp: Date.now() - 950400000 } },
  { id: 'edge-12', source: 'wallet-6', target: 'wallet-1', label: '0.9 ETH', data: { amount: 0.9, timestamp: Date.now() - 1036800000 } },
  { id: 'edge-13', source: 'wallet-1', target: 'contract-1', label: '6.0 ETH', data: { amount: 6.0, timestamp: Date.now() - 1123200000 } },
  { id: 'edge-14', source: 'exchange-1', target: 'flagged-1', label: '8.5 ETH', data: { amount: 8.5, timestamp: Date.now() - 1209600000 } },
  { id: 'edge-15', source: 'contract-2', target: 'wallet-3', label: '3.0 ETH', data: { amount: 3.0, timestamp: Date.now() - 1296000000 } },
];

// Mock data generator - exported for use in pages (returns stable data)
export function generateMockGraphData(): { nodes: WalletNode[]; edges: TransactionEdge[] } {
  return { nodes: MOCK_NODES, edges: MOCK_EDGES };
}

// Node color by risk score (primary) with type overlay
function getNodeColorByRisk(riskScore?: number, type?: string): string {
  // Flagged nodes always red
  if (type === 'flagged') return '#ef4444';
  
  // Risk-based coloring
  const score = riskScore ?? 0;
  if (score >= 70) return '#ef4444';      // Critical - red
  if (score >= 50) return '#f97316';      // High - orange
  if (score >= 30) return '#f59e0b';      // Medium - amber
  return '#22c55e';                        // Low - green
}

// Node color by type (legacy, kept for fallback)
function getNodeColor(type?: string): string {
  switch (type) {
    case 'flagged': return '#ef4444';
    case 'exchange': return '#06b6d4';
    case 'contract': return '#8b5cf6';
    default: return '#6366f1';
  }
}

// Validate graph data to prevent WeakMap errors
function validateGraphData(
  nodes: WalletNode[], 
  edges: TransactionEdge[]
): { validNodes: WalletNode[]; validEdges: TransactionEdge[] } {
  // Filter out nodes with invalid/undefined IDs
  const validNodes = nodes.filter(node => {
    if (!node || typeof node.id !== 'string' || node.id.trim() === '') {
      console.warn('[GraphExplorer] Skipping invalid node:', node);
      return false;
    }
    return true;
  });
  
  const validNodeIds = new Set(validNodes.map(n => n.id));
  
  // Filter out edges with missing endpoints or invalid IDs
  const validEdges = edges.filter(edge => {
    if (!edge || typeof edge.id !== 'string' || edge.id.trim() === '') {
      console.warn('[GraphExplorer] Skipping edge with invalid id:', edge);
      return false;
    }
    if (!edge.source || !edge.target) {
      console.warn('[GraphExplorer] Skipping edge with missing source/target:', edge);
      return false;
    }
    if (!validNodeIds.has(edge.source) || !validNodeIds.has(edge.target)) {
      // Orphaned edge - skip silently (common with filtered datasets)
      return false;
    }
    return true;
  });
  
  return { validNodes, validEdges };
}

export default function GraphExplorer({
  initialAddress,
  nodes: externalNodes,
  edges: externalEdges,
  onNodeSelect,
  onNodeClick: externalOnNodeClick,
  height,
  className = '',
}: GraphExplorerProps) {
  const isMountedRef = React.useRef(true);
  const graphRefCallback = React.useRef<GraphCanvasRef | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [searchAddress, setSearchAddress] = useState(initialAddress || '');
  const [isMounted, setIsMounted] = useState(false);
  const [isDataReady, setIsDataReady] = useState(false);

  // Track component mount state
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  // Delay mounting to avoid React 18 strict mode double-render WebGL issues
  // Increased delay to 300ms for better hydration stability
  useEffect(() => {
    const timer = setTimeout(() => {
      if (isMountedRef.current) {
        setIsMounted(true);
      }
    }, 300);
    return () => {
      clearTimeout(timer);
      setIsMounted(false);
    };
  }, []);

  // Use external data or generate mock data, with validation
  const { nodes, edges } = useMemo(() => {
    let rawNodes: WalletNode[];
    let rawEdges: TransactionEdge[];
    
    if (externalNodes && externalEdges && externalNodes.length > 0) {
      rawNodes = externalNodes;
      rawEdges = externalEdges;
    } else {
      const mockData = generateMockGraphData();
      rawNodes = mockData.nodes;
      rawEdges = mockData.edges;
    }
    
    // Validate to prevent WeakMap errors
    const { validNodes, validEdges } = validateGraphData(rawNodes, rawEdges);
    return { nodes: validNodes, edges: validEdges };
  }, [externalNodes, externalEdges]);

  // Transform nodes for reagraph with risk-based coloring
  // CRITICAL: All properties must be non-null to prevent Three.js WeakMap errors
  const graphNodes = useMemo(() => {
    if (!nodes || nodes.length === 0) return [];
    return nodes
      .filter(node => node && node.id && typeof node.id === 'string' && node.id.trim() !== '')
      .map((node) => {
        const id = String(node.id).trim();
        const label = String(node.label || id.slice(0, 10) + '...').trim();
        const fill = getNodeColorByRisk(node.data?.riskScore, node.data?.type) || '#6366f1';
        
        // Ensure no undefined/null values that could cause texture issues
        return {
          id,
          label: label || id,
          fill,
          // Only include data if it's a valid object
          ...(node.data && typeof node.data === 'object' ? { data: node.data } : {}),
        };
      });
  }, [nodes]);

  // Transform edges for reagraph
  // CRITICAL: Edge labels that are undefined cause Three.js texture errors
  const graphEdges = useMemo(() => {
    if (!edges || edges.length === 0) return [];
    const validNodeIds = new Set(graphNodes.map(n => n.id));
    return edges
      .filter(edge => edge && edge.id && edge.source && edge.target && 
              validNodeIds.has(edge.source) && validNodeIds.has(edge.target))
      .map((edge) => {
        const id = String(edge.id).trim();
        const source = String(edge.source).trim();
        const target = String(edge.target).trim();
        
        // Build edge object without undefined properties
        const edgeObj: { id: string; source: string; target: string; label?: string; data?: unknown } = {
          id,
          source,
          target,
        };
        
        // Only add label if it's a non-empty string
        if (edge.label && typeof edge.label === 'string' && edge.label.trim() !== '') {
          edgeObj.label = edge.label.trim();
        }
        
        // Only add data if it's a valid object
        if (edge.data && typeof edge.data === 'object') {
          edgeObj.data = edge.data;
        }
        
        return edgeObj;
      });
  }, [edges, graphNodes]);

  // Mark data as ready after a brief stabilization period
  useEffect(() => {
    if (graphNodes.length > 0) {
      const timer = setTimeout(() => {
        if (isMountedRef.current) {
          setIsDataReady(true);
        }
      }, 100);
      return () => clearTimeout(timer);
    } else {
      setIsDataReady(false);
    }
  }, [graphNodes.length]);

  // Only render graph when both mounted and data is ready
  const canRenderGraph = isMounted && isDataReady && graphNodes.length > 0;

  // Callback to receive ref from SafeGraphCanvas
  const handleGraphReady = useCallback((ref: GraphCanvasRef) => {
    graphRefCallback.current = ref;
  }, []);

  const handleNodeClick = useCallback((node: InternalGraphNode) => {
    setSelectedNode(node.id);
    const walletNode = nodes.find((n) => n.id === node.id) || null;
    onNodeSelect?.(walletNode);
    if (walletNode) {
      externalOnNodeClick?.(walletNode);
    }
  }, [nodes, onNodeSelect, externalOnNodeClick]);

  // Graph control handlers
  const handleCenterGraph = useCallback(() => {
    graphRefCallback.current?.centerGraph();
  }, []);

  const handleZoomIn = useCallback(() => {
    graphRefCallback.current?.zoomIn?.();
  }, []);

  const handleZoomOut = useCallback(() => {
    graphRefCallback.current?.zoomOut?.();
  }, []);

  const handleFitView = useCallback(() => {
    graphRefCallback.current?.fitNodesInView?.();
  }, []);

  const selectedNodeData = useMemo(() => 
    nodes.find((n) => n.id === selectedNode),
    [nodes, selectedNode]
  );

  return (
    <div className={`flex flex-col ${className}`} style={height ? { height: `${height}px` } : { height: '100%' }}>
      {/* Toolbar */}
      <div className="flex items-center gap-4 p-4 bg-slate-800 border-b border-slate-700">
        <input
          type="text"
          value={searchAddress}
          onChange={(e) => setSearchAddress(e.target.value)}
          placeholder="Search wallet address..."
          className="flex-1 px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
        <div className="flex gap-1">
          <button
            onClick={handleZoomIn}
            className="px-3 py-2 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded text-sm transition-colors"
            title="Zoom In"
          >
            +
          </button>
          <button
            onClick={handleZoomOut}
            className="px-3 py-2 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded text-sm transition-colors"
            title="Zoom Out"
          >
            −
          </button>
          <button
            onClick={handleCenterGraph}
            className="px-3 py-2 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded text-sm transition-colors"
            title="Center Graph"
          >
            ⌖
          </button>
          <button
            onClick={handleFitView}
            className="px-3 py-2 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded text-sm transition-colors"
            title="Fit All Nodes"
          >
            ⊡
          </button>
        </div>
      </div>

      {/* Graph Container */}
      <div className="flex-1 relative">
        <GraphErrorBoundary key={`boundary-${graphNodes.length}-${graphEdges.length}`}>
          {canRenderGraph ? (
            <SafeGraphCanvas
              key={`graph-${graphNodes.length}-${graphEdges.length}`}
              nodes={graphNodes}
              edges={graphEdges}
              onNodeClick={handleNodeClick}
              onReady={handleGraphReady}
            />
          ) : (
            <GraphLoadingPlaceholder />
          )}
        </GraphErrorBoundary>

        {/* Selected Node Panel */}
        {selectedNodeData && (
          <div className="absolute top-4 right-4 w-64 p-4 bg-slate-800/95 backdrop-blur border border-slate-600 rounded-lg shadow-xl">
            <div className="flex justify-between items-start mb-3">
              <h3 className="text-sm font-semibold text-slate-200">Node Details</h3>
              <button
                onClick={() => setSelectedNode(null)}
                className="text-slate-400 hover:text-slate-200"
              >
                ✕
              </button>
            </div>
            <div className="space-y-2 text-sm">
              <div>
                <span className="text-slate-400">Address:</span>
                <div className="text-slate-200 font-mono text-xs break-all">
                  {selectedNodeData.label}
                </div>
              </div>
              <div>
                <span className="text-slate-400">Type:</span>
                <span className="ml-2 text-slate-200 capitalize">
                  {selectedNodeData.data?.type || 'wallet'}
                </span>
              </div>
              {selectedNodeData.data?.riskScore !== undefined && (
                <div>
                  <span className="text-slate-400">Risk Score:</span>
                  <span className={`ml-2 font-medium ${
                    selectedNodeData.data.riskScore > 70 ? 'text-red-400' :
                    selectedNodeData.data.riskScore > 40 ? 'text-amber-400' : 'text-green-400'
                  }`}>
                    {selectedNodeData.data.riskScore.toFixed(1)}
                  </span>
                </div>
              )}
              {selectedNodeData.data?.balance !== undefined && (
                <div>
                  <span className="text-slate-400">Balance:</span>
                  <span className="ml-2 text-slate-200">
                    {selectedNodeData.data.balance.toFixed(4)} ETH
                  </span>
                </div>
              )}
              {selectedNodeData.data?.transactionCount !== undefined && (
                <div>
                  <span className="text-slate-400">Transactions:</span>
                  <span className="ml-2 text-slate-200">
                    {selectedNodeData.data.transactionCount}
                  </span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Legend */}
        <div className="absolute bottom-4 left-4 p-3 bg-slate-800/95 backdrop-blur border border-slate-600 rounded-lg">
          <div className="text-xs font-medium text-slate-300 mb-2">Risk Level Legend</div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-emerald-500"></div>
              <span className="text-slate-400">Low (0-30)</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-amber-500"></div>
              <span className="text-slate-400">Medium (30-50)</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-orange-500"></div>
              <span className="text-slate-400">High (50-70)</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-red-500"></div>
              <span className="text-slate-400">Critical (70+)</span>
            </div>
          </div>
          <div className="mt-2 pt-2 border-t border-slate-600">
            <div className="text-xs font-medium text-slate-300 mb-1">Entity Type</div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full border-2 border-slate-400"></div>
                <span className="text-slate-400">Wallet</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-sm border-2 border-purple-500"></div>
                <span className="text-slate-400">Contract</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-sm border-2 border-cyan-500"></div>
                <span className="text-slate-400">Exchange</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full border-2 border-red-500 bg-red-500/30"></div>
                <span className="text-slate-400">Flagged</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
