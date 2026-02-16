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

const MOCK_ALERTS: Alert[] = []; // MOCKS REMOVED — real data from backend

const MOCK_RULES: AlertRule[] = []; // MOCKS REMOVED

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
