/**
 * SIEM (Security Information and Event Management) Types
 * 
 * Types for alerts, entity profiles, and dashboard statistics
 */

export interface Alert {
  id: string;
  timestamp: string;
  address?: string;
  // Risk info
  riskLevel: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  riskScore: number;
  // Signals and patterns
  signals?: string[];
  signalCount?: number;
  patterns?: string[];
  // Actions
  action: 'BLOCK' | 'ESCROW' | 'FLAG' | 'MONITOR' | 'APPROVE';
  status: 'open' | 'investigating' | 'resolved' | 'dismissed' | 'NEW' | 'INVESTIGATING' | 'RESOLVED' | 'FALSE_POSITIVE';
  // Transaction info
  valueEth?: number;
  transactionHash?: string;
  transaction_hash?: string;
  // Legacy fields (optional)
  title?: string;
  description?: string;
  severity?: 'critical' | 'high' | 'medium' | 'low';
  source?: string;
  category?: string;
  tags?: string[];
  metadata?: Record<string, unknown>;
  amount?: number;
  confidence?: number;
}

export interface EntityProfile {
  address: string;
  entity_type: 'INDIVIDUAL' | 'INSTITUTION' | 'EXCHANGE' | 'DEFI_PROTOCOL' | 'UNKNOWN';
  kyc_level: 'NONE' | 'BASIC' | 'ENHANCED' | 'VERIFIED';
  risk_tolerance: 'LOW' | 'MEDIUM' | 'HIGH';
  jurisdiction: string;
  daily_limit_eth: number;
  monthly_limit_eth: number;
  single_tx_limit_eth: number;
  total_transactions: number;
  daily_volume_eth: number;
  risk_score?: number;
  created_at?: string;
  updated_at?: string;
  flags?: string[];
}

export interface DashboardStats {
  // Alert counts
  totalAlerts: number;
  criticalAlerts: number;
  highAlerts: number;
  mediumAlerts: number;
  lowAlerts: number;
  alertsTrend: number;
  resolvedToday: number;
  pendingInvestigation: number;
  blockedAddresses: number;
  flaggedTransactions: number;
  // Transaction metrics (optional, for extended stats)
  totalTransactions?: number;
  totalVolume?: number;
  activeAlerts?: number;
  riskScore?: number;
  complianceRate?: number;
  blockedTransactions?: number;
  pendingReviews?: number;
  averageProcessingTime?: number;
  // Time-based metrics
  transactionsToday?: number;
  volumeToday?: number;
  alertsToday?: number;
  // Risk distribution
  riskDistribution?: {
    low: number;
    medium: number;
    high: number;
    critical: number;
  };
}

export interface TimelineDataPoint {
  timestamp: string;
  value: number;
  label?: string;
  category?: string;
  metadata?: Record<string, unknown>;
}

export interface TimelineData {
  series: string;
  dataPoints: TimelineDataPoint[];
  aggregation?: 'sum' | 'avg' | 'count' | 'max' | 'min';
}

export interface AlertFilter {
  severity?: Alert['severity'][];
  status?: Alert['status'][];
  source?: string[];
  dateRange?: {
    start: string;
    end: string;
  };
  searchQuery?: string;
}

export interface AlertStats {
  total: number;
  bySeverity: Record<string, number>;
  byStatus: Record<string, number>;
  bySource: Record<string, number>;
}
