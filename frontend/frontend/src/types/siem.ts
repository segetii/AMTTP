// Types for SIEM Dashboard
export interface Alert {
  id: string;
  timestamp: string;
  address: string;
  riskLevel: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  riskScore: number;
  signals: string[];
  signalCount: number;
  patterns: string[];
  action: 'BLOCK' | 'ESCROW' | 'FLAG' | 'MONITOR' | 'APPROVE';
  status: 'NEW' | 'INVESTIGATING' | 'RESOLVED' | 'FALSE_POSITIVE';
  transactionHash?: string;
  valueEth?: number;
  fromAddress?: string;
  toAddress?: string;
}

export interface EntityProfile {
  address: string;
  firstSeen: string;
  lastSeen: string;
  totalTransactions: number;
  totalValueEth: number;
  riskScore: number;
  riskLevel: string;
  patterns: string[];
  graphConnections: number;
  mlScore: number;
  graphScore: number;
  alerts: Alert[];
  transactions: Transaction[];
  connectedAddresses: ConnectedAddress[];
}

export interface Transaction {
  hash: string;
  timestamp: string;
  from: string;
  to: string;
  valueEth: number;
  gasUsed: number;
  riskScore: number;
  flagged: boolean;
}

export interface ConnectedAddress {
  address: string;
  relationship: 'SENT_TO' | 'RECEIVED_FROM' | 'BOTH';
  transactionCount: number;
  totalValue: number;
  riskLevel: string;
}

export interface DashboardStats {
  totalAlerts: number;
  criticalAlerts: number;
  highAlerts: number;
  mediumAlerts: number;
  lowAlerts: number;
  alertsTrend: number; // percentage change
  resolvedToday: number;
  pendingInvestigation: number;
  blockedAddresses: number;
  flaggedTransactions: number;
}

export interface TimelineDataPoint {
  timestamp: string;
  critical: number;
  high: number;
  medium: number;
  low: number;
}

export interface RiskDistribution {
  level: string;
  count: number;
  percentage: number;
}

export type FilterState = {
  riskLevel: string[];
  status: string[];
  timeRange: '1h' | '24h' | '7d' | '30d' | 'custom';
  patterns: string[];
  searchQuery: string;
};
