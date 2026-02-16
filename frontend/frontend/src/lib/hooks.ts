// React Query hooks for data fetching with proper error handling
'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from './query-client';
import { useToast } from './toast';
import type { Alert, DashboardStats, TimelineDataPoint, EntityProfile } from '@/types/siem';
import type { Policy, PolicyFormData } from '@/types/policy';

// Mocks DISABLED — all hooks hit real backend APIs.
// Failures will propagate as errors so they are visible in the UI.
const USE_MOCKS = false;

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
  const timeoutId = setTimeout(() => controller.abort(), 5000);

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
      return fetchAPI<DashboardStats>(`${API_BASE}/dashboard/stats`);
    },
    refetchInterval: 30000, // Refetch every 30 seconds
  });
}

export function useTimelineData(timeRange: '1h' | '24h' | '7d' | '30d') {
  return useQuery({
    queryKey: queryKeys.dashboard.timeline(timeRange),
    queryFn: async (): Promise<TimelineDataPoint[]> => {
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
      return fetchAPI<Policy[]>(`${POLICY_API}/policies`);
    },
  });
}

export function usePolicy(id: string) {
  return useQuery({
    queryKey: queryKeys.policies.detail(id),
    queryFn: async (): Promise<Policy | null> => {
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
// Mock Data Generators — REMOVED (all data comes from real backends now)
// =============================================================================
