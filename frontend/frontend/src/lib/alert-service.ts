/**
 * Alert Service
 * 
 * Sprint 10: Real-Time Alerts & Notifications
 * 
 * Ground Truth Reference:
 * - Real-time alert delivery to UI
 * - Multi-channel notification support
 * - Alert rule evaluation and triggering
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Alert,
  AlertPriority,
  AlertCategory,
  AlertStatus,
  AlertRule,
  AlertStats,
  NotificationPreferences,
  DeliveryChannel,
  ActionType,
} from '@/types/alert';

// ═══════════════════════════════════════════════════════════════════════════════
// MOCK DATA
// ═══════════════════════════════════════════════════════════════════════════════

const MOCK_ALERTS: Alert[] = [
  {
    id: 'alert-001',
    priority: AlertPriority.CRITICAL,
    category: AlertCategory.AML,
    status: AlertStatus.NEW,
    title: 'High-Risk Transaction Detected',
    message: 'Transfer of 250,000 USDC to sanctioned address detected',
    details: 'Recipient address 0xabc... is on OFAC sanctions list',
    source: { type: 'ORACLE', id: 'chainalysis', name: 'Chainalysis' },
    resourceType: 'transfer',
    resourceId: 'tx-001',
    metadata: { amount: 250000, asset: 'USDC', riskScore: 95 },
    tags: ['sanctions', 'high-value'],
    createdAt: Date.now() - 120000,
    actions: [
      { id: 'ack', label: 'Acknowledge', type: 'primary', actionType: ActionType.ACKNOWLEDGE },
      { id: 'view', label: 'View Transfer', type: 'secondary', actionType: ActionType.VIEW_DETAILS },
      { id: 'escalate', label: 'Escalate', type: 'danger', actionType: ActionType.ESCALATE },
    ],
    deliveryChannels: [DeliveryChannel.UI, DeliveryChannel.EMAIL, DeliveryChannel.SLACK],
    deliveryStatus: [
      { channel: DeliveryChannel.UI, status: 'DELIVERED', deliveredAt: Date.now() - 120000 },
      { channel: DeliveryChannel.EMAIL, status: 'SENT', sentAt: Date.now() - 119000 },
      { channel: DeliveryChannel.SLACK, status: 'DELIVERED', deliveredAt: Date.now() - 118000 },
    ],
  },
  {
    id: 'alert-002',
    priority: AlertPriority.HIGH,
    category: AlertCategory.SECURITY,
    status: AlertStatus.ACKNOWLEDGED,
    title: 'Multiple Failed Login Attempts',
    message: '5 failed login attempts from IP 10.0.0.50 in the last 10 minutes',
    source: { type: 'SYSTEM', id: 'auth-service', name: 'Auth Service' },
    metadata: { ip: '10.0.0.50', attempts: 5, wallet: '0xdef...' },
    tags: ['security', 'brute-force'],
    createdAt: Date.now() - 600000,
    acknowledgedAt: Date.now() - 300000,
    acknowledgedBy: 'user-001',
    actions: [
      { id: 'block', label: 'Block IP', type: 'danger', actionType: ActionType.EXECUTE_ACTION },
      { id: 'dismiss', label: 'Dismiss', type: 'secondary', actionType: ActionType.DISMISS },
    ],
    deliveryChannels: [DeliveryChannel.UI],
    deliveryStatus: [
      { channel: DeliveryChannel.UI, status: 'DELIVERED', deliveredAt: Date.now() - 600000 },
    ],
  },
  {
    id: 'alert-003',
    priority: AlertPriority.MEDIUM,
    category: AlertCategory.GOVERNANCE,
    status: AlertStatus.NEW,
    title: 'Multisig Proposal Pending',
    message: 'Proposal #42 requires your signature (2/3 collected)',
    source: { type: 'CONTRACT', id: 'multisig-001', name: 'Treasury Multisig' },
    resourceType: 'multisig_proposal',
    resourceId: 'prop-042',
    metadata: { proposalId: 42, currentSignatures: 2, requiredSignatures: 3 },
    tags: ['governance', 'action-required'],
    createdAt: Date.now() - 1800000,
    actions: [
      { id: 'sign', label: 'Sign Proposal', type: 'primary', actionType: ActionType.NAVIGATE, actionData: { path: '/war-room/multisig/prop-042' } },
      { id: 'view', label: 'View Details', type: 'secondary', actionType: ActionType.VIEW_DETAILS },
    ],
    deliveryChannels: [DeliveryChannel.UI, DeliveryChannel.EMAIL],
    deliveryStatus: [
      { channel: DeliveryChannel.UI, status: 'DELIVERED', deliveredAt: Date.now() - 1800000 },
      { channel: DeliveryChannel.EMAIL, status: 'DELIVERED', deliveredAt: Date.now() - 1799000 },
    ],
  },
  {
    id: 'alert-004',
    priority: AlertPriority.LOW,
    category: AlertCategory.SYSTEM,
    status: AlertStatus.RESOLVED,
    title: 'Scheduled Maintenance Complete',
    message: 'Oracle service upgrade completed successfully',
    source: { type: 'SYSTEM', id: 'devops', name: 'DevOps' },
    metadata: { service: 'oracle-service', version: '2.1.0' },
    tags: ['maintenance'],
    createdAt: Date.now() - 7200000,
    resolvedAt: Date.now() - 3600000,
    resolvedBy: 'system',
    resolution: {
      type: 'AUTO_RESOLVED',
      reason: 'Maintenance window closed',
      timestamp: Date.now() - 3600000,
      resolvedBy: 'system',
    },
    actions: [],
    deliveryChannels: [DeliveryChannel.UI],
    deliveryStatus: [
      { channel: DeliveryChannel.UI, status: 'DELIVERED', deliveredAt: Date.now() - 7200000 },
    ],
  },
  {
    id: 'alert-005',
    priority: AlertPriority.HIGH,
    category: AlertCategory.TRANSFER,
    status: AlertStatus.IN_PROGRESS,
    title: 'Cross-Chain Transfer Stuck',
    message: 'Transfer tx-003 stuck at destination chain for > 1 hour',
    source: { type: 'SYSTEM', id: 'bridge-monitor', name: 'Bridge Monitor' },
    resourceType: 'cross_chain_transfer',
    resourceId: 'tx-003',
    metadata: { sourceChain: 'arbitrum', destChain: 'base', amount: 75000, asset: 'USDC' },
    tags: ['cross-chain', 'stuck'],
    createdAt: Date.now() - 3600000,
    acknowledgedAt: Date.now() - 3000000,
    acknowledgedBy: 'user-002',
    assignedTo: 'user-002',
    actions: [
      { id: 'retry', label: 'Retry Transfer', type: 'primary', actionType: ActionType.EXECUTE_ACTION },
      { id: 'escalate', label: 'Escalate to Bridge Team', type: 'secondary', actionType: ActionType.ESCALATE },
    ],
    deliveryChannels: [DeliveryChannel.UI, DeliveryChannel.SLACK],
    deliveryStatus: [
      { channel: DeliveryChannel.UI, status: 'DELIVERED', deliveredAt: Date.now() - 3600000 },
      { channel: DeliveryChannel.SLACK, status: 'DELIVERED', deliveredAt: Date.now() - 3599000 },
    ],
  },
];

const MOCK_RULES: AlertRule[] = [
  {
    id: 'rule-001',
    name: 'High-Value Transfer Alert',
    description: 'Alert when transfer amount exceeds threshold',
    enabled: true,
    conditions: [
      { field: 'amount', operator: 'GREATER_THAN' as any, value: 100000, valueType: 'number' },
    ],
    conditionLogic: 'AND',
    priority: AlertPriority.HIGH,
    category: AlertCategory.TRANSFER,
    titleTemplate: 'High-Value Transfer: ${amount} ${asset}',
    messageTemplate: 'Transfer of ${amount} ${asset} from ${sender} to ${recipient}',
    channels: [DeliveryChannel.UI, DeliveryChannel.EMAIL],
    recipients: [{ type: 'ROLE', value: 'R3_COMPLIANCE' }],
    cooldownMinutes: 0,
    tags: ['high-value'],
    createdAt: Date.now() - 86400000 * 30,
    updatedAt: Date.now() - 86400000,
    createdBy: 'admin',
  },
  {
    id: 'rule-002',
    name: 'Sanctions Match Alert',
    description: 'Alert when address matches sanctions list',
    enabled: true,
    conditions: [
      { field: 'sanctionsMatch', operator: 'EQUALS' as any, value: true, valueType: 'boolean' },
    ],
    conditionLogic: 'AND',
    priority: AlertPriority.CRITICAL,
    category: AlertCategory.SANCTIONS,
    titleTemplate: 'Sanctions Match Detected',
    messageTemplate: 'Address ${address} matches ${listName} sanctions list',
    channels: [DeliveryChannel.UI, DeliveryChannel.EMAIL, DeliveryChannel.SLACK],
    recipients: [{ type: 'ROLE', value: 'R3_COMPLIANCE' }, { type: 'ROLE', value: 'R5_CFO' }],
    cooldownMinutes: 0,
    tags: ['sanctions', 'compliance'],
    createdAt: Date.now() - 86400000 * 60,
    updatedAt: Date.now() - 86400000 * 7,
    createdBy: 'admin',
  },
];

// ═══════════════════════════════════════════════════════════════════════════════
// SERVICE STATE
// ═══════════════════════════════════════════════════════════════════════════════

let alerts: Alert[] = [...MOCK_ALERTS];
let rules: AlertRule[] = [...MOCK_RULES];
let listeners: Array<(alert: Alert) => void> = [];

// ═══════════════════════════════════════════════════════════════════════════════
// ALERT HOOK
// ═══════════════════════════════════════════════════════════════════════════════

export function useAlerts() {
  const [alertsState, setAlertsState] = useState<Alert[]>(alerts);
  const [rulesState, setRulesState] = useState<AlertRule[]>(rules);
  const [isLoading, setIsLoading] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  
  // Calculate unread count
  useEffect(() => {
    const count = alertsState.filter(a => a.status === AlertStatus.NEW).length;
    setUnreadCount(count);
  }, [alertsState]);
  
  // Subscribe to new alerts
  useEffect(() => {
    const handler = (alert: Alert) => {
      setAlertsState(prev => [alert, ...prev]);
    };
    listeners.push(handler);
    
    return () => {
      listeners = listeners.filter(l => l !== handler);
    };
  }, []);
  
  // Acknowledge alert
  const acknowledgeAlert = useCallback(async (alertId: string, userId: string) => {
    setIsLoading(true);
    await new Promise(r => setTimeout(r, 300));
    
    alerts = alerts.map(a =>
      a.id === alertId
        ? { ...a, status: AlertStatus.ACKNOWLEDGED, acknowledgedAt: Date.now(), acknowledgedBy: userId }
        : a
    );
    setAlertsState(alerts);
    setIsLoading(false);
  }, []);
  
  // Resolve alert
  const resolveAlert = useCallback(async (alertId: string, userId: string, notes?: string) => {
    setIsLoading(true);
    await new Promise(r => setTimeout(r, 300));
    
    alerts = alerts.map(a =>
      a.id === alertId
        ? {
            ...a,
            status: AlertStatus.RESOLVED,
            resolvedAt: Date.now(),
            resolvedBy: userId,
            resolution: {
              type: 'RESOLVED' as const,
              notes,
              timestamp: Date.now(),
              resolvedBy: userId,
            },
          }
        : a
    );
    setAlertsState(alerts);
    setIsLoading(false);
  }, []);
  
  // Dismiss alert
  const dismissAlert = useCallback(async (alertId: string, userId: string, reason?: string) => {
    setIsLoading(true);
    await new Promise(r => setTimeout(r, 300));
    
    alerts = alerts.map(a =>
      a.id === alertId
        ? {
            ...a,
            status: AlertStatus.DISMISSED,
            resolvedAt: Date.now(),
            resolution: {
              type: 'DISMISSED' as const,
              reason,
              timestamp: Date.now(),
              resolvedBy: userId,
            },
          }
        : a
    );
    setAlertsState(alerts);
    setIsLoading(false);
  }, []);
  
  // Escalate alert
  const escalateAlert = useCallback(async (alertId: string, userId: string, assignTo?: string) => {
    setIsLoading(true);
    await new Promise(r => setTimeout(r, 300));
    
    alerts = alerts.map(a =>
      a.id === alertId
        ? { ...a, status: AlertStatus.ESCALATED, assignedTo: assignTo }
        : a
    );
    setAlertsState(alerts);
    setIsLoading(false);
  }, []);
  
  // Create alert (for testing/manual alerts)
  const createAlert = useCallback(async (alertData: Omit<Alert, 'id' | 'createdAt' | 'deliveryStatus'>) => {
    const newAlert: Alert = {
      ...alertData,
      id: `alert-${Date.now()}`,
      createdAt: Date.now(),
      deliveryStatus: alertData.deliveryChannels.map(ch => ({
        channel: ch,
        status: 'DELIVERED' as const,
        deliveredAt: Date.now(),
      })),
    };
    
    alerts = [newAlert, ...alerts];
    setAlertsState(alerts);
    
    // Notify listeners
    listeners.forEach(l => l(newAlert));
    
    return newAlert;
  }, []);
  
  // Get statistics
  const getStats = useCallback(async (startTime: number, endTime: number): Promise<AlertStats> => {
    const filtered = alertsState.filter(a => a.createdAt >= startTime && a.createdAt <= endTime);
    
    const byPriority = {} as Record<AlertPriority, number>;
    const byCategory = {} as Record<AlertCategory, number>;
    const byStatus = {} as Record<AlertStatus, number>;
    let totalAckTime = 0;
    let totalResTime = 0;
    let ackCount = 0;
    let resCount = 0;
    
    filtered.forEach((a) => {
      byPriority[a.priority] = (byPriority[a.priority] || 0) + 1;
      byCategory[a.category] = (byCategory[a.category] || 0) + 1;
      byStatus[a.status] = (byStatus[a.status] || 0) + 1;
      
      if (a.acknowledgedAt) {
        totalAckTime += (a.acknowledgedAt - a.createdAt) / 1000;
        ackCount++;
      }
      if (a.resolvedAt) {
        totalResTime += (a.resolvedAt - a.createdAt) / 1000;
        resCount++;
      }
    });
    
    return {
      timeRange: { start: startTime, end: endTime },
      total: filtered.length,
      byPriority,
      byCategory,
      byStatus,
      avgAcknowledgeTime: ackCount > 0 ? totalAckTime / ackCount : 0,
      avgResolutionTime: resCount > 0 ? totalResTime / resCount : 0,
      acknowledgeRate: filtered.length > 0 ? (ackCount / filtered.length) * 100 : 0,
      resolutionRate: filtered.length > 0 ? (resCount / filtered.length) * 100 : 0,
      alertsOverTime: [],
    };
  }, [alertsState]);
  
  // Toggle rule
  const toggleRule = useCallback(async (ruleId: string, enabled: boolean) => {
    rules = rules.map(r => r.id === ruleId ? { ...r, enabled } : r);
    setRulesState(rules);
  }, []);
  
  return {
    alerts: alertsState,
    rules: rulesState,
    unreadCount,
    isLoading,
    acknowledgeAlert,
    resolveAlert,
    dismissAlert,
    escalateAlert,
    createAlert,
    getStats,
    toggleRule,
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// NOTIFICATION TOAST HOOK
// ═══════════════════════════════════════════════════════════════════════════════

export function useNotificationToast() {
  const [toasts, setToasts] = useState<Alert[]>([]);
  const timeoutsRef = useRef<Map<string, NodeJS.Timeout>>(new Map());
  
  // Subscribe to new alerts for toast display
  useEffect(() => {
    const handler = (alert: Alert) => {
      // Only show toast for high priority alerts
      if ([AlertPriority.HIGH, AlertPriority.CRITICAL].includes(alert.priority)) {
        setToasts(prev => [...prev, alert]);
        
        // Auto-remove after 10 seconds
        const timeout = setTimeout(() => {
          setToasts(prev => prev.filter(t => t.id !== alert.id));
          timeoutsRef.current.delete(alert.id);
        }, 10000);
        
        timeoutsRef.current.set(alert.id, timeout);
      }
    };
    
    listeners.push(handler);
    
    return () => {
      listeners = listeners.filter(l => l !== handler);
      timeoutsRef.current.forEach(t => clearTimeout(t));
    };
  }, []);
  
  const dismissToast = useCallback((alertId: string) => {
    setToasts(prev => prev.filter(t => t.id !== alertId));
    const timeout = timeoutsRef.current.get(alertId);
    if (timeout) {
      clearTimeout(timeout);
      timeoutsRef.current.delete(alertId);
    }
  }, []);
  
  return { toasts, dismissToast };
}

// ═══════════════════════════════════════════════════════════════════════════════
// TRIGGER ALERT (for other services to use)
// ═══════════════════════════════════════════════════════════════════════════════

export async function triggerAlert(alertData: Omit<Alert, 'id' | 'createdAt' | 'deliveryStatus'>): Promise<Alert> {
  const newAlert: Alert = {
    ...alertData,
    id: `alert-${Date.now()}`,
    createdAt: Date.now(),
    deliveryStatus: alertData.deliveryChannels.map(ch => ({
      channel: ch,
      status: 'DELIVERED' as const,
      deliveredAt: Date.now(),
    })),
  };
  
  alerts = [newAlert, ...alerts];
  
  // Notify all listeners
  listeners.forEach(l => l(newAlert));
  
  return newAlert;
}
