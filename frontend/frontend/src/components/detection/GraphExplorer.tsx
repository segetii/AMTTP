'use client';

/**
 * Graph Explorer Component
 * Canvas 2D force-directed network visualization for wallet relationships
 * Used in War Room - Detection Studio
 *
 * Replaced reagraph (WebGL / Three.js) with a pure Canvas 2D renderer
 * to eliminate chunk-load timeouts and WeakMap errors.
 */

import React, { useState, useCallback, useMemo, Component, ReactNode, useRef } from 'react';
import ForceGraph2D from './ForceGraph2D';
import type { ForceGraph2DRef, ForceNode, ForceEdge } from './ForceGraph2D';

// ─── Error Boundary ──────────────────────────────────────────────────────────

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
              {this.state.error?.message || 'Rendering failed'}
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

// ─── Types (exported for use in pages) ───────────────────────────────────────

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

// ─── Mock data ───────────────────────────────────────────────────────────────

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

export function generateMockGraphData(): { nodes: WalletNode[]; edges: TransactionEdge[] } {
  return { nodes: MOCK_NODES, edges: MOCK_EDGES };
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getNodeColorByRisk(riskScore?: number, type?: string): string {
  if (type === 'flagged') return '#ef4444';
  const score = riskScore ?? 0;
  if (score >= 70) return '#ef4444';
  if (score >= 50) return '#f97316';
  if (score >= 30) return '#f59e0b';
  return '#22c55e';
}

function validateGraphData(
  nodes: WalletNode[],
  edges: TransactionEdge[],
): { validNodes: WalletNode[]; validEdges: TransactionEdge[] } {
  const validNodes = nodes.filter(
    (n) => n && typeof n.id === 'string' && n.id.trim() !== '',
  );
  const ids = new Set(validNodes.map((n) => n.id));
  const validEdges = edges.filter(
    (e) =>
      e &&
      typeof e.id === 'string' &&
      e.id.trim() !== '' &&
      e.source &&
      e.target &&
      ids.has(e.source) &&
      ids.has(e.target),
  );
  return { validNodes, validEdges };
}

// ─── Main Component ──────────────────────────────────────────────────────────

export default function GraphExplorer({
  initialAddress,
  nodes: externalNodes,
  edges: externalEdges,
  onNodeSelect,
  onNodeClick: externalOnNodeClick,
  height,
  className = '',
}: GraphExplorerProps) {
  const graphRef = useRef<ForceGraph2DRef>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [searchAddress, setSearchAddress] = useState(initialAddress || '');

  // Use external data or fall back to mock
  const { validNodes: nodes, validEdges: edges } = useMemo(() => {
    const raw =
      externalNodes && externalEdges && externalNodes.length > 0
        ? { nodes: externalNodes, edges: externalEdges }
        : generateMockGraphData();
    return validateGraphData(raw.nodes, raw.edges);
  }, [externalNodes, externalEdges]);

  // Transform WalletNodes → ForceNodes with risk-based coloring
  const graphNodes: ForceNode[] = useMemo(
    () =>
      nodes.map((n) => ({
        id: n.id,
        label: n.label || n.id.slice(0, 12) + '…',
        fill: getNodeColorByRisk(n.data?.riskScore, n.data?.type),
        data: n.data,
      })),
    [nodes],
  );

  // Transform TransactionEdges → ForceEdges
  const graphEdges: ForceEdge[] = useMemo(() => {
    const ids = new Set(graphNodes.map((n) => n.id));
    return edges
      .filter((e) => ids.has(e.source) && ids.has(e.target))
      .map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        ...(e.label ? { label: e.label } : {}),
        ...(e.data ? { data: e.data } : {}),
      }));
  }, [edges, graphNodes]);

  // ── Callbacks ────────────────────────────────────────────────────────

  const handleNodeClick = useCallback(
    (node: ForceNode) => {
      setSelectedNode(node.id);
      const walletNode = nodes.find((n) => n.id === node.id) || null;
      onNodeSelect?.(walletNode);
      if (walletNode) externalOnNodeClick?.(walletNode);
    },
    [nodes, onNodeSelect, externalOnNodeClick],
  );

  const handleCenterGraph = useCallback(() => graphRef.current?.centerGraph(), []);
  const handleZoomIn = useCallback(() => graphRef.current?.zoomIn(), []);
  const handleZoomOut = useCallback(() => graphRef.current?.zoomOut(), []);
  const handleFitView = useCallback(() => graphRef.current?.fitNodesInView(), []);

  const selectedNodeData = useMemo(
    () => nodes.find((n) => n.id === selectedNode),
    [nodes, selectedNode],
  );

  // ── Render ───────────────────────────────────────────────────────────

  return (
    <div
      className={`flex flex-col ${className}`}
      style={height ? { height: `${height}px` } : { height: '100%' }}
    >
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
            ○
          </button>
          <button
            onClick={handleFitView}
            className="px-3 py-2 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded text-sm transition-colors"
            title="Fit All Nodes"
          >
            □
          </button>
        </div>
      </div>

      {/* Graph Container */}
      <div className="flex-1 relative">
        <GraphErrorBoundary>
          {graphNodes.length > 0 ? (
            <ForceGraph2D
              ref={graphRef}
              nodes={graphNodes}
              edges={graphEdges}
              onNodeClick={handleNodeClick}
            />
          ) : (
            <div className="flex items-center justify-center h-full bg-slate-900 rounded-lg">
              <div className="text-slate-400">No graph data available</div>
            </div>
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
                  <span
                    className={`ml-2 font-medium ${
                      selectedNodeData.data.riskScore > 70
                        ? 'text-red-400'
                        : selectedNodeData.data.riskScore > 40
                          ? 'text-amber-400'
                          : 'text-green-400'
                    }`}
                  >
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
        <div className="absolute bottom-4 left-4 p-3 bg-slate-800/95 backdrop-blur border border-slate-600 rounded-lg max-w-[200px]">
          <div className="text-xs font-medium text-slate-300 mb-2">Risk Level</div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-emerald-500"></div>
              <span className="text-slate-400">Low (0-30)</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-amber-500"></div>
              <span className="text-slate-400">Med (30-50)</span>
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
        </div>
      </div>
    </div>
  );
}
