/**
 * Ongoing Monitoring Service
 * Wraps /monitoring endpoints for continuous compliance monitoring
 */
import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
import { BaseService } from './base';
export type AlertSeverity = 'info' | 'low' | 'medium' | 'high' | 'critical';
export type AlertStatus = 'open' | 'acknowledged' | 'investigating' | 'resolved' | 'dismissed';
export type AlertType = 'risk_increase' | 'new_sanction_match' | 'suspicious_pattern' | 'velocity_breach' | 'pep_status_change' | 'kyc_expiry' | 'threshold_breach' | 'unusual_activity';
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
export declare class MonitoringService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Add address to monitoring
     */
    addAddress(address: string, options?: {
        tags?: string[];
        priority?: 'low' | 'medium' | 'high';
    }): Promise<MonitoredAddress>;
    /**
     * Remove address from monitoring
     */
    removeAddress(address: string): Promise<void>;
    /**
     * Get monitored addresses
     */
    getAddresses(options?: {
        enabled?: boolean;
        hasAlerts?: boolean;
        tags?: string[];
        limit?: number;
        offset?: number;
    }): Promise<{
        addresses: MonitoredAddress[];
        total: number;
    }>;
    /**
     * Get address monitoring status
     */
    getAddressStatus(address: string): Promise<MonitoredAddress>;
    /**
     * Get alerts
     */
    getAlerts(options?: {
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
    }>;
    /**
     * Get alert by ID
     */
    getAlert(id: string): Promise<MonitoringAlert>;
    /**
     * Acknowledge an alert
     */
    acknowledgeAlert(id: string, acknowledgedBy: string): Promise<MonitoringAlert>;
    /**
     * Resolve an alert
     */
    resolveAlert(id: string, resolution: {
        resolvedBy: string;
        resolution: string;
        actionsTaken?: string[];
    }): Promise<MonitoringAlert>;
    /**
     * Dismiss an alert
     */
    dismissAlert(id: string, reason: string, dismissedBy: string): Promise<MonitoringAlert>;
    /**
     * Get monitoring rules
     */
    getRules(): Promise<MonitoringRule[]>;
    /**
     * Create a monitoring rule
     */
    createRule(rule: Omit<MonitoringRule, 'id' | 'createdAt' | 'updatedAt'>): Promise<MonitoringRule>;
    /**
     * Update a monitoring rule
     */
    updateRule(id: string, updates: Partial<MonitoringRule>): Promise<MonitoringRule>;
    /**
     * Delete a monitoring rule
     */
    deleteRule(id: string): Promise<void>;
    /**
     * Enable/disable a rule
     */
    toggleRule(id: string, enabled: boolean): Promise<MonitoringRule>;
    /**
     * Get monitoring configuration
     */
    getConfig(): Promise<MonitoringConfig>;
    /**
     * Update monitoring configuration
     */
    updateConfig(config: Partial<MonitoringConfig>): Promise<MonitoringConfig>;
    /**
     * Trigger manual check for an address
     */
    triggerCheck(address: string): Promise<{
        checked: boolean;
        alertsGenerated: number;
        results: Record<string, any>;
    }>;
    /**
     * Get monitoring statistics
     */
    getStatistics(): Promise<{
        monitoredAddresses: number;
        totalAlerts: number;
        openAlerts: number;
        alertsByType: Record<AlertType, number>;
        alertsBySeverity: Record<AlertSeverity, number>;
        averageResolutionTime: number;
    }>;
    /**
     * Get risk trend for an address
     */
    getRiskTrend(address: string, options?: {
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
    }>;
}
//# sourceMappingURL=monitoring.d.ts.map