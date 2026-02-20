/**
 * Ongoing Monitoring Service
 * Wraps /monitoring endpoints for continuous compliance monitoring
 */

import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
import { BaseService } from './base';

export type AlertSeverity = 'info' | 'low' | 'medium' | 'high' | 'critical';
export type AlertStatus = 'open' | 'acknowledged' | 'investigating' | 'resolved' | 'dismissed';
export type AlertType = 
  | 'risk_increase'
  | 'new_sanction_match'
  | 'suspicious_pattern'
  | 'velocity_breach'
  | 'pep_status_change'
  | 'kyc_expiry'
  | 'threshold_breach'
  | 'unusual_activity';

export interface MonitoringAlert {
  id: string;
  type: AlertType;
  severity: AlertSeverity;
  status: AlertStatus;
  address: string;
  title: string;
  description: string;
  details: Record<string, any>;
  createdAt: string;
  updatedAt: string;
  acknowledgedAt?: string;
  acknowledgedBy?: string;
  resolvedAt?: string;
  resolvedBy?: string;
  resolution?: string;
}

export interface MonitoringRule {
  id: string;
  name: string;
  description: string;
  type: AlertType;
  conditions: RuleCondition[];
  severity: AlertSeverity;
  enabled: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface RuleCondition {
  field: string;
  operator: 'eq' | 'ne' | 'gt' | 'gte' | 'lt' | 'lte' | 'in' | 'change';
  value: any;
  timeWindow?: string;
}

export interface MonitoredAddress {
  address: string;
  enabled: boolean;
  monitoringSince: string;
  lastCheckedAt: string;
  alertCount: number;
  currentRiskScore: number;
  riskTrend: 'stable' | 'increasing' | 'decreasing';
  tags?: string[];
}

export interface MonitoringConfig {
  checkInterval: number;
  riskThreshold: number;
  velocityLimits: {
    daily: string;
    weekly: string;
    monthly: string;
  };
  enabledAlertTypes: AlertType[];
  notificationChannels: string[];
}

export class MonitoringService extends BaseService {
  constructor(http: AxiosInstance, events: EventEmitter) {
    super(http, events);
  }

  /**
   * Add address to monitoring
   */
  async addAddress(address: string, options?: {
    tags?: string[];
    priority?: 'low' | 'medium' | 'high';
  }): Promise<MonitoredAddress> {
    const response = await this.http.post<MonitoredAddress>('/monitoring/addresses', {
      address,
      ...options
    });
    return response.data;
  }

  /**
   * Remove address from monitoring
   */
  async removeAddress(address: string): Promise<void> {
    await this.http.delete(`/monitoring/addresses/${address}`);
  }

  /**
   * Get monitored addresses
   */
  async getAddresses(options?: {
    enabled?: boolean;
    hasAlerts?: boolean;
    tags?: string[];
    limit?: number;
    offset?: number;
  }): Promise<{
    addresses: MonitoredAddress[];
    total: number;
  }> {
    const params = new URLSearchParams();
    if (options?.enabled !== undefined) params.append('enabled', options.enabled.toString());
    if (options?.hasAlerts !== undefined) params.append('hasAlerts', options.hasAlerts.toString());
    if (options?.tags) options.tags.forEach(t => params.append('tags', t));
    if (options?.limit) params.append('limit', options.limit.toString());
    if (options?.offset) params.append('offset', options.offset.toString());

    const response = await this.http.get<{
      addresses: MonitoredAddress[];
      total: number;
    }>(`/monitoring/addresses?${params.toString()}`);

    return response.data;
  }

  /**
   * Get address monitoring status
   */
  async getAddressStatus(address: string): Promise<MonitoredAddress> {
    const response = await this.http.get<MonitoredAddress>(`/monitoring/addresses/${address}`);
    return response.data;
  }

  /**
   * Get alerts
   */
  async getAlerts(options?: {
    address?: string;
    type?: AlertType;
    severity?: AlertSeverity;
    status?: AlertStatus;
    limit?: number;
    offset?: number;
    startDate?: Date;
    endDate?: Date;
  }): Promise<{
    alerts: MonitoringAlert[];
    total: number;
  }> {
    const params = new URLSearchParams();
    if (options?.address) params.append('address', options.address);
    if (options?.type) params.append('type', options.type);
    if (options?.severity) params.append('severity', options.severity);
    if (options?.status) params.append('status', options.status);
    if (options?.limit) params.append('limit', options.limit.toString());
    if (options?.offset) params.append('offset', options.offset.toString());
    if (options?.startDate) params.append('startDate', options.startDate.toISOString());
    if (options?.endDate) params.append('endDate', options.endDate.toISOString());

    const response = await this.http.get<{
      alerts: MonitoringAlert[];
      total: number;
    }>(`/monitoring/alerts?${params.toString()}`);

    return response.data;
  }

  /**
   * Get alert by ID
   */
  async getAlert(id: string): Promise<MonitoringAlert> {
    const response = await this.http.get<MonitoringAlert>(`/monitoring/alerts/${id}`);
    return response.data;
  }

  /**
   * Acknowledge an alert
   */
  async acknowledgeAlert(id: string, acknowledgedBy: string): Promise<MonitoringAlert> {
    const response = await this.http.post<MonitoringAlert>(`/monitoring/alerts/${id}/acknowledge`, {
      acknowledgedBy
    });
    return response.data;
  }

  /**
   * Resolve an alert
   */
  async resolveAlert(id: string, resolution: {
    resolvedBy: string;
    resolution: string;
    actionsTaken?: string[];
  }): Promise<MonitoringAlert> {
    const response = await this.http.post<MonitoringAlert>(`/monitoring/alerts/${id}/resolve`, resolution);
    return response.data;
  }

  /**
   * Dismiss an alert
   */
  async dismissAlert(id: string, reason: string, dismissedBy: string): Promise<MonitoringAlert> {
    const response = await this.http.post<MonitoringAlert>(`/monitoring/alerts/${id}/dismiss`, {
      reason,
      dismissedBy
    });
    return response.data;
  }

  /**
   * Get monitoring rules
   */
  async getRules(): Promise<MonitoringRule[]> {
    const response = await this.http.get<{ rules: MonitoringRule[] }>('/monitoring/rules');
    return response.data.rules;
  }

  /**
   * Create a monitoring rule
   */
  async createRule(rule: Omit<MonitoringRule, 'id' | 'createdAt' | 'updatedAt'>): Promise<MonitoringRule> {
    const response = await this.http.post<MonitoringRule>('/monitoring/rules', rule);
    return response.data;
  }

  /**
   * Update a monitoring rule
   */
  async updateRule(id: string, updates: Partial<MonitoringRule>): Promise<MonitoringRule> {
    const response = await this.http.put<MonitoringRule>(`/monitoring/rules/${id}`, updates);
    return response.data;
  }

  /**
   * Delete a monitoring rule
   */
  async deleteRule(id: string): Promise<void> {
    await this.http.delete(`/monitoring/rules/${id}`);
  }

  /**
   * Enable/disable a rule
   */
  async toggleRule(id: string, enabled: boolean): Promise<MonitoringRule> {
    const response = await this.http.post<MonitoringRule>(`/monitoring/rules/${id}/toggle`, { enabled });
    return response.data;
  }

  /**
   * Get monitoring configuration
   */
  async getConfig(): Promise<MonitoringConfig> {
    const response = await this.http.get<MonitoringConfig>('/monitoring/config');
    return response.data;
  }

  /**
   * Update monitoring configuration
   */
  async updateConfig(config: Partial<MonitoringConfig>): Promise<MonitoringConfig> {
    const response = await this.http.put<MonitoringConfig>('/monitoring/config', config);
    return response.data;
  }

  /**
   * Trigger manual check for an address
   */
  async triggerCheck(address: string): Promise<{
    checked: boolean;
    alertsGenerated: number;
    results: Record<string, any>;
  }> {
    const response = await this.http.post(`/monitoring/check/${address}`);
    return response.data;
  }

  /**
   * Get monitoring statistics
   */
  async getStatistics(): Promise<{
    monitoredAddresses: number;
    totalAlerts: number;
    openAlerts: number;
    alertsByType: Record<AlertType, number>;
    alertsBySeverity: Record<AlertSeverity, number>;
    averageResolutionTime: number;
  }> {
    const response = await this.http.get('/monitoring/statistics');
    return response.data;
  }

  /**
   * Get risk trend for an address
   */
  async getRiskTrend(address: string, options?: {
    days?: number;
  }): Promise<{
    address: string;
    dataPoints: {
      timestamp: string;
      riskScore: number;
      events?: string[];
    }[];
    trend: 'stable' | 'increasing' | 'decreasing';
    averageScore: number;
  }> {
    const params = new URLSearchParams();
    if (options?.days) params.append('days', options.days.toString());

    const response = await this.http.get(`/monitoring/trend/${address}?${params.toString()}`);
    return response.data;
  }
}
