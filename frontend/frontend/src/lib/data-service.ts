/**
 * Unified Data Service
 * 
 * Provides consistent data access across all platform components.
 * All visualization data comes from the same source (generated from Memgraph).
 * 
 * Data Transformation: Maps raw JSON data to component-expected formats.
 */

import { useState, useEffect, useCallback } from 'react';
import sankeyFallback from '@/data/sankeyFlowData.json';
import flaggedFallback from '@/data/flaggedQueueData.json';

// ============================================================================
// Types - Matching Component Interfaces
// ============================================================================

// Sankey Types
export interface SankeyNode {
  id: string;
  label: string;
  type: 'source' | 'intermediate' | 'sink';
  riskLevel: 'low' | 'medium' | 'high' | 'critical';
}

export interface SankeyLink {
  source: string;
  target: string;
  value: number;
  count: number;
  isAnomaly: boolean;
}

export interface SankeyData {
  nodes: SankeyNode[];
  links: SankeyLink[];
}

// Graph Types - Matches GraphExplorer.tsx
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

export interface GraphData {
  nodes: WalletNode[];
  edges: TransactionEdge[];
}

// Velocity Types - Matches VelocityHeatmap.tsx
export interface VelocityDataPoint {
  hour: number;      // 0-23
  day: number;       // 0-6 (Sunday-Saturday)
  velocity: number;  // Transactions per hour
  anomalyScore?: number;
}

// TimeSeries Types - Matches TimeSeriesChart.tsx
export interface TimeSeriesDataPoint {
  timestamp: number;
  value: number;
  baseline?: number;
  upperBound?: number;
  lowerBound?: number;
  isAnomaly?: boolean;
}

// Distribution Types - Matches RiskDistributionChart.tsx
export interface DistributionBucket {
  range: string;
  rangeStart: number;
  rangeEnd: number;
  count: number;
  percentage?: number;
}

// Flagged Queue Types
export interface FlaggedTransaction {
  id: string;
  address: string;
  hash?: string;
  from?: string;
  to?: string;
  value?: number;
  riskScore: number;
  riskLevel?: string;
  reason?: string;
  flags: string[];
  timestamp: string;
  status: 'pending' | 'reviewing' | 'escalated' | 'resolved' | 'under_review';
  patternCount?: number;
  totalTransactions?: number;
  uniqueCounterparties?: number;
}

// Dashboard Stats Types
export interface DashboardStats {
  totalTransactions: number;
  totalVolume: number;
  flaggedCount: number;
  averageRiskScore: number;
  highRiskWallets: number;
  complianceRate: number;
}

// ============================================================================
// Data Transformation Functions
// ============================================================================

const DAY_MAP: Record<string, number> = {
  'Sun': 0, 'Mon': 1, 'Tue': 2, 'Wed': 3, 'Thu': 4, 'Fri': 5, 'Sat': 6
};

function transformVelocityData(raw: unknown): VelocityDataPoint[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((item) => {
    const rec = item as Record<string, unknown>;
    const transactionCount = typeof rec.transactionCount === 'number' ? rec.transactionCount : undefined;
    const velocityNormalized = typeof rec.velocity === 'number' ? rec.velocity : undefined;
    return {
      hour: typeof rec.hour === 'number' ? rec.hour : 0,
      day: typeof rec.dayIndex === 'number' ? rec.dayIndex : DAY_MAP[rec.day as string] || 0,
      // Prefer raw transaction count for clearer heatmap contrast
      velocity: transactionCount ?? (velocityNormalized ?? 0),
      // Keep anomaly score if present, otherwise fall back to normalized velocity
      anomalyScore: (rec.anomalyScore as number | undefined) ?? velocityNormalized,
    };
  });
}

function transformTimeSeriesData(raw: unknown): TimeSeriesDataPoint[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((item) => {
    const rec = item as Record<string, unknown>;
    return {
      timestamp: rec.timestamp ? new Date(rec.timestamp as string).getTime() : Date.now(),
      value: (rec.transactionCount as number) || (rec.totalVolume as number) || 0,
      baseline: rec.avgRiskScore as number | undefined,
      isAnomaly: (rec.flaggedCount as number || 0) > 5,
    };
  });
}

function transformDistributionData(raw: unknown): DistributionBucket[] {
  // Handle both array and object with histogram property
  const histogram = Array.isArray(raw) ? raw : (raw as Record<string, unknown>)?.histogram;
  if (!Array.isArray(histogram)) return [];
  
  const total = histogram.reduce((sum: number, item) => {
    const rec = item as Record<string, unknown>;
    return sum + (rec.count as number || 0);
  }, 0);
  
  return histogram.map((item) => {
    const rec = item as Record<string, unknown>;
    return {
      range: (rec.bin as string) || `${rec.binStart}-${rec.binEnd}`,
      rangeStart: (rec.binStart as number) || 0,
      rangeEnd: (rec.binEnd as number) || 0,
      count: (rec.count as number) || 0,
      percentage: total > 0 ? ((rec.count as number || 0) / total) * 100 : 0,
    };
  });
}

function transformGraphData(raw: unknown): GraphData {
  const data = raw as Record<string, unknown>;
  const rawNodes = (data?.nodes as unknown[]) || [];
  const rawEdges = (data?.edges as unknown[]) || [];
  
  const nodes = rawNodes
    .map<WalletNode | null>((item) => {
      const node = item as Record<string, unknown>;
      const id = node.id as string | undefined;
      if (!id) return null;

      const riskScore = (node.riskScore as number) || 0;
      const riskLevel = (node.riskLevel as string | undefined)?.toUpperCase();
      const transactionCount = node.transactionCount as number | undefined;
      const uniqueCounterparties = node.uniqueCounterparties as number | undefined;
      
      // Use explicit nodeType from data if available, otherwise infer
      let nodeType: 'wallet' | 'contract' | 'exchange' | 'flagged' = 'wallet';
      const explicitType = (node.nodeType as string | undefined)?.toLowerCase();
      
      if (explicitType && ['wallet', 'contract', 'exchange', 'flagged'].includes(explicitType)) {
        nodeType = explicitType as 'wallet' | 'contract' | 'exchange' | 'flagged';
      } else {
        // Fallback to inference
        if (node.isFlagged || riskLevel === 'HIGH' || riskLevel === 'CRITICAL' || riskScore > 70) {
          nodeType = 'flagged';
        } else if ((transactionCount ?? 0) >= 5000 && (uniqueCounterparties ?? 0) >= 1000) {
          nodeType = 'exchange';
        } else if ((transactionCount ?? 0) >= 500 && (uniqueCounterparties ?? 0) <= 20) {
          nodeType = 'contract';
        }
      }
      
      const walletNode: WalletNode = {
        id,
        label: (node.label as string) || (node.address as string)?.slice(0, 10) + '...',
        data: {
          type: nodeType,
          riskScore: riskScore,
          balance: node.balance as number | undefined,
          transactionCount: transactionCount,
        },
      };

      return walletNode;
  })
  .filter((node): node is WalletNode => node !== null);

  const validNodeIds = new Set(nodes.map((node) => node.id));
  const edges = rawEdges
    .map<TransactionEdge | null>((item, idx) => {
      const edge = item as Record<string, unknown>;
      const source = edge.source as string | undefined;
      const target = edge.target as string | undefined;
      if (!source || !target) return null;
      if (!validNodeIds.has(source) || !validNodeIds.has(target)) return null;

      const edgeData: TransactionEdge = {
        id: (edge.id as string) || `edge-${idx}`,
        source,
        target,
        label: edge.value ? `${(edge.value as number).toFixed(2)} ETH` : undefined,
        data: {
          amount: edge.value as number | undefined,
          timestamp: edge.timestamp ? new Date(edge.timestamp as string).getTime() : undefined,
          txHash: edge.txHash as string | undefined,
        },
      };

      return edgeData;
  })
  .filter((edge): edge is TransactionEdge => edge !== null);
  
  return { nodes, edges };
}

// ============================================================================
// Data Fetching Functions
// ============================================================================

// Use a dedicated internal API namespace to avoid collisions with backend rewrites
const API_BASE = '/app-api/data';

async function fetchData<T>(endpoint: string, transform?: (raw: unknown) => T): Promise<T> {
  const response = await fetch(`${API_BASE}/${endpoint}`, {
    // Ensure cookies (session) are sent for role-gated endpoints
    credentials: 'same-origin',
  });
  if (!response.ok) {
    let responseText = '';
    try {
      responseText = await response.text();
    } catch {
      // ignore
    }

    throw new Error(
      `Failed to fetch ${endpoint}. Status: ${response.status} ${response.statusText}. Response: ${responseText || '<empty>'}`
    );
  }

  const raw = await response.json();
  return transform ? transform(raw) : raw;
}

// ============================================================================
// Public API
// ============================================================================

export async function getSankeyData(): Promise<SankeyData> {
  try {
    return await fetchData<SankeyData>('sankey');
  } catch (e) {
    console.error('Falling back to bundled Sankey data:', e);
    return sankeyFallback as SankeyData;
  }
}

export async function getGraphData(): Promise<GraphData> {
  return fetchData<GraphData>('graph', transformGraphData);
}

export async function getVelocityData(): Promise<VelocityDataPoint[]> {
  return fetchData<VelocityDataPoint[]>('velocity', transformVelocityData);
}

export async function getTimeSeriesData(): Promise<TimeSeriesDataPoint[]> {
  return fetchData<TimeSeriesDataPoint[]>('timeseries', transformTimeSeriesData);
}

export async function getDistributionData(): Promise<DistributionBucket[]> {
  return fetchData<DistributionBucket[]>('distribution', transformDistributionData);
}

export async function getFlaggedQueue(): Promise<FlaggedTransaction[]> {
  try {
    return await fetchData<FlaggedTransaction[]>('flagged', transformFlaggedQueue);
  } catch (e) {
    console.error('Falling back to bundled flagged queue data:', e);
    return transformFlaggedQueue(flaggedFallback as unknown);
  }
}

function transformFlaggedQueue(raw: unknown): FlaggedTransaction[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((item, idx) => {
    const rec = item as Record<string, unknown>;
    return {
      id: (rec.id as string) || `flagged-${idx}`,
      address: (rec.address as string) || (rec.from as string) || '',
      hash: (rec.hash as string) || (rec.tx_hash as string) || undefined,
      from: (rec.from as string) || (rec.sender as string) || undefined,
      to: (rec.to as string) || (rec.receiver as string) || undefined,
      value: (rec.value as number) || (rec.amount as number) || undefined,
      riskScore: (rec.riskScore as number) || (rec.risk_score as number) || 0,
      riskLevel: (rec.riskLevel as string) || undefined,
      reason: (rec.reason as string) || undefined,
      flags: (rec.flags as string[]) || [(rec.reason as string) || 'Flagged'],
      timestamp: (rec.timestamp as string) || new Date().toISOString(),
      status: (rec.status as 'pending' | 'reviewing' | 'escalated' | 'resolved' | 'under_review') || 'pending',
      patternCount: (rec.patternCount as number) || undefined,
      totalTransactions: (rec.totalTransactions as number) || undefined,
      uniqueCounterparties: (rec.uniqueCounterparties as number) || undefined,
    };
  });
}

function transformDashboardStats(raw: unknown): DashboardStats {
  const rec = raw as Record<string, unknown>;
  const totalTx = (rec.totalTransactions as number) || 0;
  const flagged = (rec.flaggedWallets as number) || (rec.flaggedCount as number) || 0;
  
  return {
    totalTransactions: totalTx,
    totalVolume: (rec.totalVolume as number) || 0,
    flaggedCount: flagged,
    averageRiskScore: (rec.avgRiskScore as number) || (rec.averageRiskScore as number) || 0,
    highRiskWallets: (rec.highRiskWallets as number) || 0,
    complianceRate: totalTx > 0 ? ((totalTx - flagged) / totalTx) * 100 : 100,
  };
}

export async function getDashboardStats(): Promise<DashboardStats> {
  return fetchData<DashboardStats>('stats', transformDashboardStats);
}

// ============================================================================
// React Hooks for Data Fetching
// ============================================================================

export function useSankeyData() {
  const [data, setData] = useState<SankeyData>({ nodes: [], links: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSankeyData()
      .then(setData)
      .catch(e => {
        console.error(e);
        setError(e.message);
        // keep fallback or previous data if available
      })
      .finally(() => setLoading(false));
  }, []);

  return { data, loading, error };
}

export function useGraphData() {
  const [data, setData] = useState<GraphData>({ nodes: [], edges: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(() => {
    setLoading(true);
    getGraphData()
      .then(setData)
      .catch(e => {
        console.error(e);
        setError(e.message);
        setData({ nodes: [], edges: [] });
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, refetch: fetchData };
}

export function useVelocityData() {
  const [data, setData] = useState<VelocityDataPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getVelocityData()
      .then(setData)
      .catch(e => {
        console.error(e);
        setError(e.message);
        setData([]);
      })
      .finally(() => setLoading(false));
  }, []);

  return { data, loading, error };
}

export function useTimeSeriesData() {
  const [data, setData] = useState<TimeSeriesDataPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getTimeSeriesData()
      .then(setData)
      .catch(e => {
        console.error(e);
        setError(e.message);
        setData([]);
      })
      .finally(() => setLoading(false));
  }, []);

  return { data, loading, error };
}

export function useDistributionData() {
  const [data, setData] = useState<DistributionBucket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDistributionData()
      .then(setData)
      .catch(e => {
        console.error(e);
        setError(e.message);
        setData([]);
      })
      .finally(() => setLoading(false));
  }, []);

  return { data, loading, error };
}

export function useFlaggedQueue() {
  const [data, setData] = useState<FlaggedTransaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getFlaggedQueue()
      .then(setData)
      .catch(e => {
        console.error(e);
        setError(e.message);
        // keep fallback or previous data if available
      })
      .finally(() => setLoading(false));
  }, []);

  return { data, loading, error };
}

export function useDashboardStats() {
  const [data, setData] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDashboardStats()
      .then(setData)
      .catch(e => {
        console.error(e);
        setError(e.message);
        setData({
          totalTransactions: 0,
          totalVolume: 0,
          flaggedCount: 0,
          averageRiskScore: 0,
          highRiskWallets: 0,
          complianceRate: 0,
        });
      })
      .finally(() => setLoading(false));
  }, []);

  return { data, loading, error };
}
