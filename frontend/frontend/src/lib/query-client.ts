// React Query client configuration
import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Stale time: 30 seconds before refetch
      staleTime: 30 * 1000,
      // Cache time: 5 minutes
      gcTime: 5 * 60 * 1000,
      // Retry failed requests up to 3 times with exponential backoff
      retry: 3,
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
      // Refetch on window focus for real-time data
      refetchOnWindowFocus: true,
      // Don't refetch on mount if data is fresh
      refetchOnMount: true,
    },
    mutations: {
      // Retry mutations once
      retry: 1,
    },
  },
});

// Query keys factory for type-safe cache management
export const queryKeys = {
  // Dashboard
  dashboard: {
    all: ['dashboard'] as const,
    stats: () => [...queryKeys.dashboard.all, 'stats'] as const,
    timeline: (range: string) => [...queryKeys.dashboard.all, 'timeline', range] as const,
  },
  // Alerts
  alerts: {
    all: ['alerts'] as const,
    list: (filters?: { riskLevel?: string[]; status?: string[]; limit?: number }) =>
      [...queryKeys.alerts.all, 'list', filters] as const,
    detail: (id: string) => [...queryKeys.alerts.all, 'detail', id] as const,
  },
  // Entities
  entities: {
    all: ['entities'] as const,
    profile: (address: string) => [...queryKeys.entities.all, 'profile', address] as const,
  },
  // Policies
  policies: {
    all: ['policies'] as const,
    list: () => [...queryKeys.policies.all, 'list'] as const,
    detail: (id: string) => [...queryKeys.policies.all, 'detail', id] as const,
  },
  // Risk Engine
  risk: {
    all: ['risk'] as const,
    health: () => [...queryKeys.risk.all, 'health'] as const,
    modelInfo: () => [...queryKeys.risk.all, 'model-info'] as const,
    score: (address: string) => [...queryKeys.risk.all, 'score', address] as const,
  },
} as const;
