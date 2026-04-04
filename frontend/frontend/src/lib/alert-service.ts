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

const MOCK_ALERTS: Alert[] = []; // Seed from backend on first load

const MOCK_RULES: AlertRule[] = []; // Seed from backend on first load

// ═══════════════════════════════════════════════════════════════════════════════
// SERVICE STATE
// ═══════════════════════════════════════════════════════════════════════════════

let alerts: Alert[] = [...MOCK_ALERTS];
let rules: AlertRule[] = [...MOCK_RULES];
let listeners: Array<(alert: Alert) => void> = [];
let _hasFetched = false;

// Convert MongoDB flagged_transactions to Alert objects
function mongoDocToAlert(doc: Record<string, unknown>, idx: number): Alert {
  const riskScore = (doc.riskScore as number) ?? 0;
  const riskLevel = (doc.riskLevel as string) || 'MEDIUM';
  const priority =
    riskLevel === 'CRITICAL' ? AlertPriority.CRITICAL :
    riskLevel === 'HIGH' ? AlertPriority.HIGH :
    riskLevel === 'MEDIUM' ? AlertPriority.MEDIUM : AlertPriority.LOW;
  const category =
    ((doc.reason as string) || '').toLowerCase().includes('sanction') ? AlertCategory.SANCTIONS :
    ((doc.reason as string) || '').toLowerCase().includes('mixer') ? AlertCategory.AML :
    AlertCategory.COMPLIANCE;

  return {
    id: (doc.id as string) || (doc._id as string) || `alert-${idx}`,
    priority,
    category,
    status: (doc.status as string) === 'resolved' ? AlertStatus.RESOLVED
      : (doc.status as string) === 'reviewing' ? AlertStatus.ACKNOWLEDGED
      : (doc.status as string) === 'escalated' ? AlertStatus.ESCALATED
      : AlertStatus.NEW,
    title: `${riskLevel} Risk Transaction Flagged`,
    message: (doc.reason as string) || 'Suspicious activity detected',
    details: `Risk Score: ${riskScore.toFixed(1)} • Address: ${(doc.address as string) || 'Unknown'}`,
    source: { type: 'SYSTEM', id: 'ml-engine', name: 'ML Risk Engine' },
    resourceType: 'transaction',
    resourceId: (doc.hash as string) || (doc.id as string) || '',
    metadata: { riskScore, riskLevel, address: doc.address, from: doc.from, to: doc.to, value: doc.value },
    tags: Array.isArray(doc.flags) ? (doc.flags as string[]) : [(doc.reason as string) || 'flagged'],
    createdAt: doc.timestamp ? new Date(doc.timestamp as string).getTime() : Date.now() - idx * 60000,
    actions: [
      { id: 'ack', label: 'Acknowledge', type: 'primary', actionType: ActionType.ACKNOWLEDGE },
      { id: 'esc', label: 'Escalate', type: 'secondary', actionType: ActionType.ESCALATE },
      { id: 'dis', label: 'Dismiss', type: 'danger', actionType: ActionType.DISMISS },
    ],
    deliveryChannels: [DeliveryChannel.UI],
    deliveryStatus: [{ channel: DeliveryChannel.UI, status: 'DELIVERED' as const, deliveredAt: Date.now() }],
  };
}

async function fetchAlertsFromBackend(): Promise<void> {
  if (_hasFetched) return;
  _hasFetched = true;
  try {
    const resp = await fetch('/app-api/data/alerts', { credentials: 'same-origin', signal: AbortSignal.timeout(8000) });
    if (!resp.ok) throw new Error(`${resp.status}`);
    const data = await resp.json();
    if (Array.isArray(data) && data.length > 0) {
      alerts = data.map((d: Record<string, unknown>, i: number) => mongoDocToAlert(d, i));
    }
  } catch (e) {
    console.warn('[alert-service] Backend fetch failed, using empty state:', e);
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// ALERT HOOK
// ═══════════════════════════════════════════════════════════════════════════════

export function useAlerts() {
  const [alertsState, setAlertsState] = useState<Alert[]>(alerts);
  const [rulesState, setRulesState] = useState<AlertRule[]>(rules);
  const [isLoading, setIsLoading] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);

  // Fetch alerts from MongoDB on first mount
  useEffect(() => {
    setIsLoading(true);
    fetchAlertsFromBackend()
      .then(() => setAlertsState([...alerts]))
      .finally(() => setIsLoading(false));
  }, []);
  
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
