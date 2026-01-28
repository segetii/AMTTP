/**
 * Dashboard Service - Analytics and Metrics
 * 
 * Provides dashboard data for compliance monitoring,
 * including statistics, alerts, and visualizations.
 */

import { AxiosInstance } from 'axios';
import { BaseService } from './base';
import { EventEmitter } from '../events';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export type AlertSeverity = 'low' | 'medium' | 'high' | 'critical';
export type AlertType = 'transaction' | 'policy' | 'sanctions' | 'ml' | 'system';
export type TimeRange = '1h' | '24h' | '7d' | '30d' | '90d';

export interface DashboardStats {
  totalTransactions: number;
  flaggedTransactions: number;
  pendingReviews: number;
  approvedToday: number;
  blockedToday: number;
  complianceScore: number;
  riskScore: number;
  activeAlerts: number;
}

export interface Alert {
  id: string;
  type: AlertType;
  severity: AlertSeverity;
  title: string;
  message: string;
  source: string;
  timestamp: string;
  isRead: boolean;
  details?: Record<string, unknown>;
  relatedEntityId?: string;
}

export interface RiskDistribution {
  low: number;
  medium: number;
  high: number;
  critical: number;
}

export interface ActivityMetric {
  timestamp: string;
  transactions: number;
  flagged: number;
  blocked: number;
}

export interface SankeyNode {
  id: string;
  name: string;
  value?: number;
}

export interface SankeyLink {
  source: string;
  target: string;
  value: number;
}

export interface SankeyData {
  nodes: SankeyNode[];
  links: SankeyLink[];
}

export interface TopRiskEntity {
  address: string;
  riskScore: number;
  riskLevel: string;
  flagCount: number;
  lastActivity: string;
}

export interface GeographicRiskMap {
  countries: Array<{
    code: string;
    name: string;
    riskLevel: string;
    transactionCount: number;
    flaggedCount: number;
  }>;
}

export interface DashboardFilters {
  timeRange?: TimeRange;
  riskLevel?: string;
  transactionType?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SERVICE
// ═══════════════════════════════════════════════════════════════════════════════

export class DashboardService extends BaseService {
  constructor(http: AxiosInstance, events: EventEmitter) {
    super(http, events);
  }

  /**
   * Get dashboard overview statistics
   */
  async getStats(filters?: DashboardFilters): Promise<DashboardStats> {
    const response = await this.http.get<DashboardStats>(
      '/monitoring/dashboard/stats',
      { params: filters }
    );
    return response.data;
  }

  /**
   * Get active alerts
   */
  async getAlerts(options?: {
    severity?: AlertSeverity;
    type?: AlertType;
    limit?: number;
    unreadOnly?: boolean;
  }): Promise<Alert[]> {
    const response = await this.http.get<{ alerts: Alert[] }>(
      '/monitoring/alerts',
      { params: options }
    );
    return response.data.alerts;
  }

  /**
   * Mark an alert as read
   */
  async markAlertRead(alertId: string): Promise<void> {
    await this.http.patch(`/monitoring/alerts/${alertId}`, { isRead: true });
    this.events.emit('dashboard:alert_read', { alertId });
  }

  /**
   * Dismiss an alert
   */
  async dismissAlert(alertId: string): Promise<void> {
    await this.http.delete(`/monitoring/alerts/${alertId}`);
    this.events.emit('dashboard:alert_dismissed', { alertId });
  }

  /**
   * Get risk distribution
   */
  async getRiskDistribution(filters?: DashboardFilters): Promise<RiskDistribution> {
    const response = await this.http.get<RiskDistribution>(
      '/monitoring/dashboard/risk-distribution',
      { params: filters }
    );
    return response.data;
  }

  /**
   * Get activity metrics over time
   */
  async getActivityMetrics(timeRange: TimeRange = '24h'): Promise<ActivityMetric[]> {
    const response = await this.http.get<{ metrics: ActivityMetric[] }>(
      '/monitoring/dashboard/activity',
      { params: { timeRange } }
    );
    return response.data.metrics;
  }

  /**
   * Get Sankey flow visualization data
   */
  async getSankeyFlow(options?: {
    limit?: number;
    minValue?: number;
    riskLevel?: string;
  }): Promise<SankeyData> {
    const response = await this.http.get<SankeyData>(
      '/monitoring/dashboard/sankey',
      { params: options }
    );
    return response.data;
  }

  /**
   * Get top risk entities
   */
  async getTopRiskEntities(limit: number = 10): Promise<TopRiskEntity[]> {
    const response = await this.http.get<{ entities: TopRiskEntity[] }>(
      '/monitoring/dashboard/top-risk',
      { params: { limit } }
    );
    return response.data.entities;
  }

  /**
   * Get geographic risk map data
   */
  async getGeographicRiskMap(): Promise<GeographicRiskMap> {
    const response = await this.http.get<GeographicRiskMap>(
      '/monitoring/dashboard/geographic'
    );
    return response.data;
  }

  /**
   * Get real-time metrics
   */
  async getRealTimeMetrics(): Promise<{
    transactionsPerSecond: number;
    avgResponseTime: number;
    queueDepth: number;
    activeConnections: number;
  }> {
    const response = await this.http.get('/monitoring/dashboard/realtime');
    return response.data;
  }

  /**
   * Export dashboard data
   */
  async exportData(format: 'csv' | 'json' | 'pdf', filters?: DashboardFilters): Promise<Blob> {
    const response = await this.http.get('/monitoring/dashboard/export', {
      params: { format, ...filters },
      responseType: 'blob',
    });
    return response.data;
  }

  /**
   * Subscribe to real-time updates (returns cleanup function)
   */
  subscribeToUpdates(callback: (update: {
    type: string;
    data: unknown;
  }) => void): () => void {
    // In a real implementation, this would use WebSocket
    // For now, we'll use polling
    const interval = setInterval(async () => {
      try {
        const metrics = await this.getRealTimeMetrics();
        callback({ type: 'metrics', data: metrics });
      } catch {
        // Ignore polling errors
      }
    }, 5000);

    return () => clearInterval(interval);
  }

  /**
   * Format alert for display
   */
  static formatAlert(alert: Alert): {
    title: string;
    description: string;
    time: string;
    color: string;
    icon: string;
  } {
    const colors: Record<AlertSeverity, string> = {
      low: 'blue',
      medium: 'yellow',
      high: 'orange',
      critical: 'red',
    };

    const icons: Record<AlertType, string> = {
      transaction: '💸',
      policy: '📜',
      sanctions: '🚫',
      ml: '🤖',
      system: '⚙️',
    };

    return {
      title: alert.title,
      description: alert.message,
      time: new Date(alert.timestamp).toLocaleString(),
      color: colors[alert.severity] || 'gray',
      icon: icons[alert.type] || '📌',
    };
  }
}
