'use client';

/**
 * Sankey Flow Auditor Component
 * 
 * Unovis-based Sankey diagram for value flow visualization
 * 
 * Used in War Room - Detection Studio (R4 Compliance ONLY)
 * Cognitive Job: "Money never lies" - value conservation analysis
 * 
 * Features:
 * - Source → split → merge visualization
 * - Smurfing detection
 * - Entry/exit analysis
 * - Value conservation verification
 */

import React, { useMemo } from 'react';
import { VisSingleContainer, VisSankey } from '@unovis/react';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface FlowNode {
  id: string;
  label: string;
  type: 'source' | 'intermediate' | 'sink' | 'mixer' | 'exchange';
  riskLevel?: 'low' | 'medium' | 'high' | 'critical';
  address?: string;
}

export interface FlowLink {
  source: string;
  target: string;
  value: number;
  count?: number;
  currency?: string;
  isAnomaly?: boolean;
  timestamp?: number;
}

export interface SankeyAuditorProps {
  nodes: FlowNode[];
  links: FlowLink[];
  title?: string;
  height?: number;
  darkMode?: boolean;
  showValues?: boolean;
}

// ═══════════════════════════════════════════════════════════════════════════════
// STYLING
// ═══════════════════════════════════════════════════════════════════════════════

const TYPE_COLORS = {
  source: '#10b981',       // Green - Entry point
  intermediate: '#3b82f6', // Blue - Pass-through
  sink: '#8b5cf6',         // Purple - Exit point
  mixer: '#ef4444',        // Red - Mixer/Tumbler
  exchange: '#f59e0b',     // Amber - Exchange
};

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function SankeyAuditor({
  nodes,
  links,
  title = 'Value Flow Analysis',
  height = 500,
  darkMode = true,
  showValues = true,
}: SankeyAuditorProps) {
  // Ensure graph is acyclic: Unovis Sankey requires a DAG. Remove self-loops and links that introduce cycles.
  const { safeLinks } = useMemo(() => {
    const nodeIds = new Set(nodes.map((n) => n.id));
    const adjacency = new Map<string, Set<string>>();

    const ensureAdj = (id: string) => {
      if (!adjacency.has(id)) adjacency.set(id, new Set());
      return adjacency.get(id)!;
    };

    const hasPath = (from: string, to: string): boolean => {
      // BFS to see if there is an existing path from `from` to `to`
      const queue: string[] = [from];
      const visited = new Set<string>();
      while (queue.length) {
        const current = queue.shift()!;
        if (current === to) return true;
        if (visited.has(current)) continue;
        visited.add(current);
        const neighbors = adjacency.get(current);
        if (neighbors) {
          neighbors.forEach((n) => {
            if (!visited.has(n)) queue.push(n);
          });
        }
      }
      return false;
    };

    const safe: FlowLink[] = [];
    const dropped: FlowLink[] = [];

    for (const link of links) {
      // Skip links with missing endpoints
      if (!link?.source || !link?.target) {
        dropped.push(link);
        continue;
      }

      // Skip links pointing to unknown nodes
      if (!nodeIds.has(link.source) || !nodeIds.has(link.target)) {
        dropped.push(link);
        continue;
      }

      // Remove self-loops which break Sankey layout
      if (link.source === link.target) {
        dropped.push(link);
        continue;
      }

      // If adding this edge would create a cycle, drop it
      if (hasPath(link.target, link.source)) {
        dropped.push(link);
        continue;
      }

      // Accept link and update adjacency
      safe.push(link);
      ensureAdj(link.source).add(link.target);
    }

    if (dropped.length > 0) {
      console.warn('[SankeyAuditor] Dropped cyclic/self links to keep DAG:', dropped.map(l => `${l.source}->${l.target}`).join(', '));
    }

    return { safeLinks: safe };
  }, [links, nodes]);
  
  // Create node map for quick lookup
  const nodeMap = useMemo(() => {
    const map = new Map<string, FlowNode>();
    nodes.forEach(n => map.set(n.id, n));
    return map;
  }, [nodes]);
  
  // Transform data for Unovis
  const sankeyData = useMemo(() => {
    return {
      nodes: nodes.map((n) => ({
        ...n,
        // Ensure id and label are present (already in spread)
      })),
      links: safeLinks.map(l => ({
        ...l,
        // Ensure source, target, value are present (already in spread)
      })),
    };
  }, [nodes, safeLinks]);
  
  // Calculate total flow for conservation check
  const flowStats = useMemo(() => {
    // Calculate total value flowing through the system
    const totalFlow = safeLinks.reduce((sum, l) => sum + (l.value || 0), 0);
    
    // Find flows that originate from "source" type nodes
    const sourceFlow = safeLinks
      .filter(l => {
        const sourceNode = nodeMap.get(l.source);
        return sourceNode?.type === 'source';
      })
      .reduce((sum, l) => sum + (l.value || 0), 0);
    
    // Find flows that end at "sink" type nodes
    const sinkFlow = safeLinks
      .filter(l => {
        const targetNode = nodeMap.get(l.target);
        return targetNode?.type === 'sink';
      })
      .reduce((sum, l) => sum + (l.value || 0), 0);
    
    // If no source/sink types, use total flow as both
    const effectiveSourceFlow = sourceFlow > 0 ? sourceFlow : totalFlow;
    const effectiveSinkFlow = sinkFlow > 0 ? sinkFlow : totalFlow;
    
    const difference = Math.abs(effectiveSourceFlow - effectiveSinkFlow);
    const conservationRate = effectiveSourceFlow > 0 
      ? ((effectiveSourceFlow - difference) / effectiveSourceFlow) * 100 
      : 100;
    
    return {
      sourceFlow: effectiveSourceFlow,
      sinkFlow: effectiveSinkFlow,
      totalFlow,
      difference,
      conservationRate,
      isConserved: conservationRate > 95, // Relaxed to 95% for real data
    };
  }, [safeLinks, nodeMap]);
  
  // Node color accessor
  const nodeColor = (d: FlowNode) => {
    const node = nodeMap.get(d.id);
    return node ? TYPE_COLORS[node.type] || '#64748b' : '#64748b';
  };
  
  // Link color accessor
  const linkColor = (d: FlowLink) => {
    if (d.isAnomaly) return '#ef4444';
    return darkMode ? 'rgba(148, 163, 184, 0.3)' : 'rgba(100, 116, 139, 0.3)';
  };
  
  // Node label accessor
  const nodeLabel = (d: FlowNode) => {
    const node = nodeMap.get(d.id);
    return node?.label || d.id;
  };
  
  return (
    <div className={`w-full ${darkMode ? 'text-slate-200' : 'text-gray-800'}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">{title}</h3>
        
        {/* Conservation Status */}
        <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm ${
          flowStats.isConserved 
            ? 'bg-green-500/20 text-green-400' 
            : 'bg-red-500/20 text-red-400'
        }`}>
          {flowStats.isConserved ? (
            <>
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
              Value Conserved ({flowStats.conservationRate.toFixed(1)}%)
            </>
          ) : (
            <>
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              Value Discrepancy: {flowStats.difference.toFixed(4)} ETH
            </>
          )}
        </div>
      </div>
      
      {/* Sankey Diagram */}
      <div 
        className={`rounded-xl p-4 ${darkMode ? 'bg-slate-800/50' : 'bg-gray-50'}`}
        style={{ height }}
      >
        <VisSingleContainer 
          data={sankeyData}
          height={height - 32}
        >
          <VisSankey
            // Unovis Sankey accessor signatures are untyped; allow any with narrow usage.
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            id={(d: any) => d.id}
            nodeColor={nodeColor}
            linkColor={linkColor}
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            linkValue={(d: any) => d.value}
            label={nodeLabel}
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            subLabel={(d: any) => nodeMap.get(d.id)?.type || ''}
            labelBackground={true}
          />
        </VisSingleContainer>
      </div>
      
      {/* Legend */}
      <div className={`mt-4 p-3 rounded-lg ${darkMode ? 'bg-slate-800/30' : 'bg-gray-100'}`}>
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <span className="font-semibold">Node Types:</span>
          {Object.entries(TYPE_COLORS).map(([type, color]) => (
            <div key={type} className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded" style={{ backgroundColor: color }} />
              <span className="capitalize">{type}</span>
            </div>
          ))}
        </div>
      </div>
      
      {/* Flow Summary */}
      {showValues && (
        <div className={`mt-4 grid grid-cols-3 gap-4`}>
          <div className={`p-4 rounded-lg ${darkMode ? 'bg-slate-800/30' : 'bg-gray-100'}`}>
            <div className="text-sm opacity-60">Total Flow</div>
            <div className="text-xl font-semibold text-cyan-400">
              {flowStats.totalFlow.toFixed(2)} ETH
            </div>
          </div>
          <div className={`p-4 rounded-lg ${darkMode ? 'bg-slate-800/30' : 'bg-gray-100'}`}>
            <div className="text-sm opacity-60">Transactions</div>
            <div className="text-xl font-semibold text-blue-400">
              {links.reduce((sum, l) => sum + (l.count || 1), 0).toLocaleString()}
            </div>
          </div>
          <div className={`p-4 rounded-lg ${darkMode ? 'bg-slate-800/30' : 'bg-gray-100'}`}>
            <div className="text-sm opacity-60">High Risk Flows</div>
            <div className="text-xl font-semibold text-red-400">
              {links.filter(l => l.isAnomaly).length}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER: Generate mock data for testing
// ═══════════════════════════════════════════════════════════════════════════════

export function generateMockSankeyData(): { nodes: FlowNode[], links: FlowLink[] } {
  const nodes: FlowNode[] = [
    // Sources
    { id: 'src-1', label: 'Exchange A', type: 'source', address: '0xabc...' },
    { id: 'src-2', label: 'Wallet B', type: 'source', address: '0xdef...' },
    
    // Intermediates
    { id: 'int-1', label: 'Hop 1', type: 'intermediate', address: '0x111...' },
    { id: 'int-2', label: 'Hop 2', type: 'intermediate', address: '0x222...' },
    { id: 'int-3', label: 'Hop 3', type: 'intermediate', address: '0x333...' },
    { id: 'mixer-1', label: 'Suspected Mixer', type: 'mixer', riskLevel: 'high', address: '0xbad...' },
    
    // Sinks
    { id: 'sink-1', label: 'Exchange C', type: 'exchange', address: '0x444...' },
    { id: 'sink-2', label: 'Final Wallet', type: 'sink', address: '0x555...' },
  ];
  
  const links: FlowLink[] = [
    // From sources
    { source: 'src-1', target: 'int-1', value: 10.5, currency: 'ETH' },
    { source: 'src-2', target: 'int-1', value: 5.2, currency: 'ETH' },
    
    // Through intermediates
    { source: 'int-1', target: 'int-2', value: 8.0, currency: 'ETH' },
    { source: 'int-1', target: 'mixer-1', value: 7.5, currency: 'ETH', isAnomaly: true },
    { source: 'int-2', target: 'int-3', value: 7.8, currency: 'ETH' },
    { source: 'mixer-1', target: 'int-3', value: 7.3, currency: 'ETH', isAnomaly: true },
    
    // To sinks
    { source: 'int-3', target: 'sink-1', value: 9.0, currency: 'ETH' },
    { source: 'int-3', target: 'sink-2', value: 5.9, currency: 'ETH' },
  ];
  
  return { nodes, links };
}
