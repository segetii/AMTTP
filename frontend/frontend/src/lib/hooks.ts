// React Query hooks for data fetching with proper error handling
'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from './query-client';
import { useToast } from './toast';
import type { Alert, DashboardStats, TimelineDataPoint, EntityProfile } from '@/types/siem';
import type { Policy, PolicyFormData } from '@/types/policy';

// Environment check for mock data
const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === 'true';

// API Base URLs
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8007';
const RISK_ENGINE_URL = process.env.NEXT_PUBLIC_RISK_ENGINE_URL || 'http://127.0.0.1:8002';
const POLICY_API = process.env.NEXT_PUBLIC_POLICY_API_URL || 'http://127.0.0.1:8003';

// =============================================================================
// Error Types
// =============================================================================

export class APIError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string
  ) {
    super(message);
    this.name = 'APIError';
  }
}

// Generic fetch wrapper with error handling
async function fetchAPI<T>(
  url: string,
  options?: RequestInit
): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 30000);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const errorBody = await response.text();
      throw new APIError(
        errorBody || `Request failed with status ${response.status}`,
        response.status
      );
    }

    return response.json();
  } catch (error) {
    clearTimeout(timeoutId);
    
    if (error instanceof APIError) {
      throw error;
    }
    
    if (error instanceof Error) {
      if (error.name === 'AbortError') {
        throw new APIError('Request timed out', 408, 'TIMEOUT');
      }
      throw new APIError(error.message, 0, 'NETWORK_ERROR');
    }
    
    throw new APIError('Unknown error occurred', 0, 'UNKNOWN');
  }
}

// =============================================================================
// Dashboard Hooks
// =============================================================================

export function useDashboardStats() {
  return useQuery({
    queryKey: queryKeys.dashboard.stats(),
    queryFn: async (): Promise<DashboardStats> => {
      if (USE_MOCKS) {
        return generateMockStats();
      }
      return fetchAPI<DashboardStats>(`${API_BASE}/dashboard/stats`);
    },
    refetchInterval: 30000, // Refetch every 30 seconds
  });
}

export function useTimelineData(timeRange: '1h' | '24h' | '7d' | '30d') {
  return useQuery({
    queryKey: queryKeys.dashboard.timeline(timeRange),
    queryFn: async (): Promise<TimelineDataPoint[]> => {
      if (USE_MOCKS) {
        return generateMockTimeline(timeRange);
      }
      return fetchAPI<TimelineDataPoint[]>(
        `${API_BASE}/dashboard/timeline?time_range=${timeRange}`
      );
    },
    refetchInterval: 30000,
  });
}

// =============================================================================
// Alerts Hooks
// =============================================================================

interface AlertFilters {
  riskLevel?: string[];
  status?: string[];
  limit?: number;
  offset?: number;
}

export function useAlerts(filters?: AlertFilters) {
  return useQuery({
    queryKey: queryKeys.alerts.list(filters),
    queryFn: async (): Promise<Alert[]> => {
      if (USE_MOCKS) {
        return generateMockAlerts(filters?.limit || 50);
      }
      
      const params = new URLSearchParams();
      if (filters?.riskLevel?.length) params.set('risk_level', filters.riskLevel.join(','));
      if (filters?.status?.length) params.set('status', filters.status.join(','));
      if (filters?.limit) params.set('limit', filters.limit.toString());
      if (filters?.offset) params.set('offset', filters.offset.toString());
      
      const query = params.toString();
      const url = query
        ? `${API_BASE}/dashboard/alerts?${query}`
        : `${API_BASE}/dashboard/alerts`;
      const data = await fetchAPI<any>(url);
      if (Array.isArray(data)) return data;
      if (Array.isArray(data?.alerts)) return data.alerts as Alert[];
      return [];
    },
    refetchInterval: 30000,
  });
}

type AlertAction = 'FLAG' | 'BLOCK' | 'ESCALATE' | 'RESOLVE' | 'FALSE_POSITIVE' | 'WATCHLIST';

export function useAlertAction() {
  const queryClient = useQueryClient();
  const { success, error } = useToast();

  return useMutation({
    mutationFn: async ({ alertId, action }: { alertId: string; action: AlertAction }) => {
      if (USE_MOCKS) {
        // Simulate network delay
        await new Promise(resolve => setTimeout(resolve, 500));
        return { success: true, message: `Action ${action} performed (mock)` };
      }
      
      return fetchAPI<{ success: boolean; message: string }>(
        `${API_BASE}/alerts/${alertId}/action`,
        {
          method: 'POST',
          body: JSON.stringify({ action }),
        }
      );
    },
    onSuccess: (data, variables) => {
      success(`Alert ${variables.action.toLowerCase()}ed`, data.message);
      // Invalidate alerts cache to refresh data
      queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all });
    },
    onError: (err: Error) => {
      error('Action failed', err.message);
    },
  });
}

// =============================================================================
// Entity Profile Hooks
// =============================================================================

export function useEntityProfile(address: string) {
  return useQuery({
    queryKey: queryKeys.entities.profile(address),
    queryFn: async (): Promise<EntityProfile> => {
      if (USE_MOCKS) {
        return generateMockEntity(address);
      }
      return fetchAPI<EntityProfile>(`${API_BASE}/profiles/${address}`);
    },
    enabled: !!address && address.length === 42,
  });
}

// =============================================================================
// Risk Engine Hooks
// =============================================================================

export function useRiskEngineHealth() {
  return useQuery({
    queryKey: queryKeys.risk.health(),
    queryFn: async () => {
      return fetchAPI<{
        status: string;
        model_loaded: boolean;
        version: string;
        uptime_seconds: number;
      }>(`${RISK_ENGINE_URL}/health`);
    },
    retry: 1,
    refetchInterval: 60000, // Check health every minute
  });
}

export function useAddressScore(address: string) {
  return useQuery({
    queryKey: queryKeys.risk.score(address),
    queryFn: async () => {
      if (USE_MOCKS) {
        return {
          address,
          hybrid_score: Math.random() * 100,
          risk_level: ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'][Math.floor(Math.random() * 4)],
          action: ['APPROVE', 'REVIEW', 'ESCROW', 'BLOCK'][Math.floor(Math.random() * 4)],
          ml_score: Math.random(),
          graph_score: Math.random() * 50,
          patterns: 'LAYERING,FAN_OUT',
          signal_count: Math.floor(Math.random() * 5) + 1,
        };
      }
      
      return fetchAPI<{
        address: string;
        hybrid_score: number;
        risk_level: string;
        action: string;
        ml_score: number;
        graph_score: number;
        patterns: string;
        signal_count: number;
      }>(`${API_BASE}/score/address`, {
        method: 'POST',
        body: JSON.stringify({ address }),
      });
    },
    enabled: !!address && address.length === 42,
  });
}

// =============================================================================
// Policy Hooks
// =============================================================================

export function usePolicies() {
  return useQuery({
    queryKey: queryKeys.policies.list(),
    queryFn: async (): Promise<Policy[]> => {
      if (USE_MOCKS) {
        return generateMockPolicies();
      }
      return fetchAPI<Policy[]>(`${POLICY_API}/policies`);
    },
  });
}

export function usePolicy(id: string) {
  return useQuery({
    queryKey: queryKeys.policies.detail(id),
    queryFn: async (): Promise<Policy | null> => {
      if (USE_MOCKS) {
        const policies = generateMockPolicies();
        return policies.find(p => p.id === id) || null;
      }
      return fetchAPI<Policy>(`${POLICY_API}/policies/${id}`);
    },
    enabled: !!id,
  });
}

export function useCreatePolicy() {
  const queryClient = useQueryClient();
  const { success, error } = useToast();

  return useMutation({
    mutationFn: async (data: PolicyFormData) => {
      if (USE_MOCKS) {
        await new Promise(resolve => setTimeout(resolve, 500));
        return {
          id: `policy-${Date.now()}`,
          ...data,
          isDefault: false,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          createdBy: '0x0000000000000000000000000000000000000000',
          stats: {
            totalTransactions: 0,
            approvedCount: 0,
            reviewedCount: 0,
            escrowedCount: 0,
            blockedCount: 0,
          },
        } as Policy;
      }
      
      return fetchAPI<Policy>(`${POLICY_API}/policies`, {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },
    onSuccess: () => {
      success('Policy created', 'The new policy has been saved.');
      queryClient.invalidateQueries({ queryKey: queryKeys.policies.all });
    },
    onError: (err: Error) => {
      error('Failed to create policy', err.message);
    },
  });
}

export function useUpdatePolicy() {
  const queryClient = useQueryClient();
  const { success, error } = useToast();

  return useMutation({
    mutationFn: async ({ id, data }: { id: string; data: Partial<PolicyFormData> }) => {
      return fetchAPI<Policy>(`${POLICY_API}/policies/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      });
    },
    onSuccess: (_, variables) => {
      success('Policy updated', 'Changes have been saved.');
      queryClient.invalidateQueries({ queryKey: queryKeys.policies.detail(variables.id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.policies.list() });
    },
    onError: (err: Error) => {
      error('Failed to update policy', err.message);
    },
  });
}

export function useDeletePolicy() {
  const queryClient = useQueryClient();
  const { success, error } = useToast();

  return useMutation({
    mutationFn: async (id: string) => {
      await fetchAPI(`${POLICY_API}/policies/${id}`, { method: 'DELETE' });
    },
    onSuccess: () => {
      success('Policy deleted', 'The policy has been removed.');
      queryClient.invalidateQueries({ queryKey: queryKeys.policies.all });
    },
    onError: (err: Error) => {
      error('Failed to delete policy', err.message);
    },
  });
}

// =============================================================================
// Mock Data Generators (only used when USE_MOCKS is true)
// =============================================================================

function generateMockStats(): DashboardStats {
  return {
    totalAlerts: 166,
    criticalAlerts: 8,
    highAlerts: 24,
    mediumAlerts: 89,
    lowAlerts: 45,
    alertsTrend: 12.5,
    resolvedToday: 15,
    pendingInvestigation: 23,
    blockedAddresses: 8,
    flaggedTransactions: 1152,
  };
}

function generateMockTimeline(timeRange: string): TimelineDataPoint[] {
  const points = timeRange === '1h' ? 12 : timeRange === '24h' ? 24 : timeRange === '7d' ? 7 : 30;
  const interval = timeRange === '1h' ? 5 * 60 * 1000 :
                   timeRange === '24h' ? 60 * 60 * 1000 :
                   24 * 60 * 60 * 1000;

  return Array.from({ length: points }, (_, i) => ({
    timestamp: new Date(Date.now() - (points - i) * interval).toISOString(),
    critical: Math.floor(Math.random() * 3),
    high: Math.floor(Math.random() * 8),
    medium: Math.floor(Math.random() * 15),
    low: Math.floor(Math.random() * 10),
  }));
}

function generateMockAlerts(count: number): Alert[] {
  const riskLevels: Alert['riskLevel'][] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];
  const patterns = ['SMURFING', 'LAYERING', 'FAN_OUT', 'FAN_IN', 'ROUND_TRIP', 'RAPID_MOVEMENT'];
  const statuses: Alert['status'][] = ['NEW', 'INVESTIGATING', 'RESOLVED', 'FALSE_POSITIVE'];
  const actions: Alert['action'][] = ['BLOCK', 'ESCROW', 'FLAG', 'MONITOR', 'APPROVE'];

  const knownAddresses = [
    '0xeae7380dd4cef6fbd1144f49e4d1e6964258a4f4',
    '0xa1abfa21f80ecf401b5fab3f4cf88223dc7ed5a6',
    '0x28c6c06298d514db089934071355e5743bf21d60',
    '0x21a31ee1afc51d94c2efccaa2092ad1028285549',
  ];

  return Array.from({ length: count }, (_, i) => {
    const riskLevel = riskLevels[Math.floor(Math.random() * riskLevels.length)];
    const numPatterns = Math.floor(Math.random() * 3) + 1;
    const selectedPatterns = patterns.sort(() => 0.5 - Math.random()).slice(0, numPatterns);

    return {
      id: `alert-${Date.now()}-${i}`,
      timestamp: new Date(Date.now() - Math.random() * 7 * 24 * 60 * 60 * 1000).toISOString(),
      address: i < knownAddresses.length ? knownAddresses[i] : `0x${Math.random().toString(16).slice(2, 42)}`,
      riskLevel,
      riskScore: riskLevel === 'CRITICAL' ? 85 + Math.random() * 15 :
                 riskLevel === 'HIGH' ? 65 + Math.random() * 20 :
                 riskLevel === 'MEDIUM' ? 40 + Math.random() * 25 :
                 Math.random() * 40,
      signals: selectedPatterns,
      signalCount: numPatterns,
      patterns: selectedPatterns,
      action: actions[riskLevels.indexOf(riskLevel)] || 'MONITOR',
      status: statuses[Math.floor(Math.random() * statuses.length)],
      valueEth: Math.random() * 100,
      transactionHash: `0x${Math.random().toString(16).slice(2, 66)}`,
    };
  }).sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
}

function generateMockEntity(address: string): EntityProfile {
  return {
    address,
    firstSeen: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(),
    lastSeen: new Date().toISOString(),
    totalTransactions: Math.floor(Math.random() * 500) + 50,
    totalValueEth: Math.random() * 1000,
    riskScore: Math.random() * 100,
    riskLevel: 'HIGH',
    patterns: ['LAYERING', 'FAN_OUT'],
    graphConnections: Math.floor(Math.random() * 50) + 5,
    mlScore: Math.random(),
    graphScore: Math.random() * 50,
    alerts: generateMockAlerts(5),
    transactions: Array.from({ length: 10 }, (_, i) => ({
      hash: `0x${Math.random().toString(16).slice(2, 66)}`,
      timestamp: new Date(Date.now() - i * 3600000).toISOString(),
      from: i % 2 === 0 ? address : `0x${Math.random().toString(16).slice(2, 42)}`,
      to: i % 2 === 1 ? address : `0x${Math.random().toString(16).slice(2, 42)}`,
      valueEth: Math.random() * 10,
      gasUsed: Math.floor(Math.random() * 100000) + 21000,
      riskScore: Math.random() * 100,
      flagged: Math.random() > 0.7,
    })),
    connectedAddresses: Array.from({ length: 8 }, () => ({
      address: `0x${Math.random().toString(16).slice(2, 42)}`,
      relationship: ['SENT_TO', 'RECEIVED_FROM', 'BOTH'][Math.floor(Math.random() * 3)] as 'SENT_TO' | 'RECEIVED_FROM' | 'BOTH',
      transactionCount: Math.floor(Math.random() * 20) + 1,
      totalValue: Math.random() * 50,
      riskLevel: ['LOW', 'MEDIUM', 'HIGH'][Math.floor(Math.random() * 3)],
    })),
  };
}

function generateMockPolicies(): Policy[] {
  return [
    {
      id: 'policy-default',
      name: 'Default Policy',
      description: 'Standard compliance policy for all transactions',
      isActive: true,
      isDefault: true,
      createdAt: '2025-01-01T00:00:00Z',
      updatedAt: '2025-01-05T00:00:00Z',
      createdBy: '0xBc270F0ce5bbE8Ed8489f11262eF1a1527CaF23F',
      thresholds: { lowRiskMax: 25, mediumRiskMax: 50, highRiskMax: 75 },
      limits: {
        maxTransactionAmount: '1000000000000000000000',
        dailyLimit: '10000000000000000000000',
        monthlyLimit: '100000000000000000000000',
        maxCounterparties: 100,
      },
      rules: {
        blockSanctionedAddresses: true,
        requireKYCAboveThreshold: true,
        kycThresholdAmount: '10000000000000000000',
        autoEscrowHighRisk: true,
        escrowDurationHours: 24,
        allowedChainIds: [1, 137, 42161],
        blockedCountries: ['KP', 'IR', 'SY'],
      },
      actions: {
        onLowRisk: 'APPROVE',
        onMediumRisk: 'REVIEW',
        onHighRisk: 'ESCROW',
        onCriticalRisk: 'BLOCK',
        onSanctionedAddress: 'BLOCK',
        onUnknownAddress: 'REVIEW',
      },
      whitelist: [],
      blacklist: [],
      stats: {
        totalTransactions: 15420,
        approvedCount: 12500,
        reviewedCount: 2100,
        escrowedCount: 720,
        blockedCount: 100,
        lastTriggered: '2025-01-05T10:30:00Z',
      },
    },
  ];
}
