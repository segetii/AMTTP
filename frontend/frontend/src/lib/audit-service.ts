/**
 * Audit Trail Service
 * 
 * Sprint 9: Audit Trail & Logging
 * 
 * Ground Truth Reference:
 * - Immutable audit chain with hash integrity
 * - Every action traced to actor and UI state
 * - Compliance-ready export and reporting
 */

import { useState, useEffect, useCallback } from 'react';
import { sha256 } from '@/lib/ui-snapshot-chain';
import {
  AuditEvent,
  AuditCategory,
  AuditAction,
  AuditSeverity,
  ActorType,
  AuditQuery,
  AuditQueryResult,
  AuditTrail,
  AuditReport,
  AuditStats,
  AuditEventSummary,
  ComplianceEvidence,
  EvidenceType,
} from '@/types/audit';

// ═══════════════════════════════════════════════════════════════════════════════
// MOCK DATA
// ═══════════════════════════════════════════════════════════════════════════════

const generateMockEvents = (): AuditEvent[] => []; // MOCKS REMOVED

// ═══════════════════════════════════════════════════════════════════════════════
// SERVICE STATE
// ═══════════════════════════════════════════════════════════════════════════════

let auditEvents: AuditEvent[] = generateMockEvents();
let lastHash: string = auditEvents[auditEvents.length - 1]?.hash || '';

// ═══════════════════════════════════════════════════════════════════════════════
// AUDIT HOOK
// ═══════════════════════════════════════════════════════════════════════════════

export function useAudit() {
  const [events, setEvents] = useState<AuditEvent[]>(auditEvents);
  const [isLoading, setIsLoading] = useState(false);
  
  // Log a new audit event
  const logEvent = useCallback(async (
    event: Omit<AuditEvent, 'id' | 'timestamp' | 'hash' | 'previousHash'>
  ): Promise<AuditEvent> => {
    const timestamp = Date.now();
    const id = `evt-${timestamp}-${Math.random().toString(36).substr(2, 9)}`;
    
    // Calculate hash for integrity
    const hashInput = JSON.stringify({
      id,
      timestamp,
      ...event,
      previousHash: lastHash,
    });
    const hash = await sha256(hashInput);
    
    const newEvent: AuditEvent = {
      ...event,
      id,
      timestamp,
      previousHash: lastHash,
      hash,
    };
    
    lastHash = hash;
    auditEvents = [...auditEvents, newEvent];
    setEvents(auditEvents);
    
    return newEvent;
  }, []);
  
  // Query events
  const queryEvents = useCallback(async (query: AuditQuery): Promise<AuditQueryResult> => {
    setIsLoading(true);
    await new Promise(r => setTimeout(r, 300));
    
    let filtered = [...auditEvents];
    
    // Time range
    if (query.startTime) {
      filtered = filtered.filter(e => e.timestamp >= query.startTime!);
    }
    if (query.endTime) {
      filtered = filtered.filter(e => e.timestamp <= query.endTime!);
    }
    
    // Categories
    if (query.categories?.length) {
      filtered = filtered.filter(e => query.categories!.includes(e.category));
    }
    
    // Actions
    if (query.actions?.length) {
      filtered = filtered.filter(e => query.actions!.includes(e.action));
    }
    
    // Severities
    if (query.severities?.length) {
      filtered = filtered.filter(e => query.severities!.includes(e.severity));
    }
    
    // Actors
    if (query.actorIds?.length) {
      filtered = filtered.filter(e => query.actorIds!.includes(e.actorId));
    }
    
    // Resources
    if (query.resourceTypes?.length) {
      filtered = filtered.filter(e => query.resourceTypes!.includes(e.resourceType));
    }
    if (query.resourceIds?.length) {
      filtered = filtered.filter(e => query.resourceIds!.includes(e.resourceId));
    }
    
    // Success/Failure
    if (query.successOnly) {
      filtered = filtered.filter(e => e.success);
    }
    if (query.failuresOnly) {
      filtered = filtered.filter(e => !e.success);
    }
    
    // Search
    if (query.searchText) {
      const searchLower = query.searchText.toLowerCase();
      filtered = filtered.filter(e => 
        e.description.toLowerCase().includes(searchLower) ||
        e.resourceName?.toLowerCase().includes(searchLower) ||
        e.resourceId.toLowerCase().includes(searchLower)
      );
    }
    
    // Sort
    const sortOrder = query.sortOrder === 'asc' ? 1 : -1;
    filtered.sort((a, b) => {
      if (query.sortBy === 'severity') {
        const severityOrder = Object.values(AuditSeverity);
        return sortOrder * (severityOrder.indexOf(a.severity) - severityOrder.indexOf(b.severity));
      }
      if (query.sortBy === 'category') {
        return sortOrder * a.category.localeCompare(b.category);
      }
      return sortOrder * (a.timestamp - b.timestamp);
    });
    
    // Pagination
    const page = query.page || 1;
    const pageSize = query.pageSize || 20;
    const total = filtered.length;
    const totalPages = Math.ceil(total / pageSize);
    const start = (page - 1) * pageSize;
    const paginatedEvents = filtered.slice(start, start + pageSize);
    
    setIsLoading(false);
    
    return {
      events: paginatedEvents,
      total,
      page,
      pageSize,
      totalPages,
      query,
      executedAt: Date.now(),
    };
  }, []);
  
  // Get audit trail for a resource
  const getAuditTrail = useCallback(async (
    resourceType: string,
    resourceId: string
  ): Promise<AuditTrail> => {
    const relatedEvents = auditEvents.filter(
      e => e.resourceType === resourceType && e.resourceId === resourceId
    ).sort((a, b) => a.timestamp - b.timestamp);
    
    return {
      resourceType,
      resourceId,
      events: relatedEvents,
      firstEvent: relatedEvents[0]?.timestamp || 0,
      lastEvent: relatedEvents[relatedEvents.length - 1]?.timestamp || 0,
      eventCount: relatedEvents.length,
    };
  }, []);
  
  // Generate statistics
  const getStats = useCallback(async (startTime: number, endTime: number): Promise<AuditStats> => {
    const filtered = auditEvents.filter(e => e.timestamp >= startTime && e.timestamp <= endTime);
    
    const byCategory = {} as Record<AuditCategory, number>;
    const byAction = {} as Record<AuditAction, number>;
    const bySeverity = {} as Record<AuditSeverity, number>;
    const uniqueActors = new Set<string>();
    const uniqueResources = new Set<string>();
    let successCount = 0;
    let failureCount = 0;
    
    filtered.forEach((e) => {
      byCategory[e.category] = (byCategory[e.category] || 0) + 1;
      byAction[e.action] = (byAction[e.action] || 0) + 1;
      bySeverity[e.severity] = (bySeverity[e.severity] || 0) + 1;
      uniqueActors.add(e.actorId);
      uniqueResources.add(`${e.resourceType}:${e.resourceId}`);
      if (e.success) successCount++; else failureCount++;
    });
    
    return {
      totalEvents: filtered.length,
      byCategory,
      byAction,
      bySeverity,
      successCount,
      failureCount,
      uniqueActors: uniqueActors.size,
      uniqueResources: uniqueResources.size,
    };
  }, []);
  
  // Generate report
  const generateReport = useCallback(async (
    name: string,
    startTime: number,
    endTime: number,
    format: 'JSON' | 'CSV' | 'PDF' = 'JSON'
  ): Promise<AuditReport> => {
    setIsLoading(true);
    
    const stats = await getStats(startTime, endTime);
    const filtered = auditEvents.filter(e => e.timestamp >= startTime && e.timestamp <= endTime);
    
    // Generate summary
    const summaryMap = new Map<string, AuditEventSummary>();
    filtered.forEach((e) => {
      const key = `${e.category}:${e.action}`;
      const existing = summaryMap.get(key);
      if (existing) {
        existing.count++;
        if (e.success) existing.successCount++; else existing.failureCount++;
        if (e.timestamp < existing.firstOccurrence) existing.firstOccurrence = e.timestamp;
        if (e.timestamp > existing.lastOccurrence) existing.lastOccurrence = e.timestamp;
      } else {
        summaryMap.set(key, {
          category: e.category,
          action: e.action,
          count: 1,
          successCount: e.success ? 1 : 0,
          failureCount: e.success ? 0 : 1,
          firstOccurrence: e.timestamp,
          lastOccurrence: e.timestamp,
        });
      }
    });
    
    setIsLoading(false);
    
    return {
      id: `report-${Date.now()}`,
      name,
      description: `Audit report from ${new Date(startTime).toLocaleDateString()} to ${new Date(endTime).toLocaleDateString()}`,
      startTime,
      endTime,
      generatedAt: Date.now(),
      generatedBy: 'current-user',
      stats,
      eventsSummary: Array.from(summaryMap.values()),
      events: filtered,
      format,
    };
  }, [getStats]);
  
  // Verify chain integrity
  const verifyIntegrity = useCallback(async (): Promise<{ valid: boolean; brokenAt?: string }> => {
    for (let i = 1; i < auditEvents.length; i++) {
      const current = auditEvents[i];
      const previous = auditEvents[i - 1];
      
      if (current.previousHash !== previous.hash) {
        return { valid: false, brokenAt: current.id };
      }
    }
    return { valid: true };
  }, []);
  
  return {
    events,
    isLoading,
    logEvent,
    queryEvents,
    getAuditTrail,
    getStats,
    generateReport,
    verifyIntegrity,
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// AUDIT LOGGER UTILITY
// ═══════════════════════════════════════════════════════════════════════════════

export class AuditLogger {
  private static instance: AuditLogger;
  
  static getInstance(): AuditLogger {
    if (!AuditLogger.instance) {
      AuditLogger.instance = new AuditLogger();
    }
    return AuditLogger.instance;
  }
  
  async log(
    category: AuditCategory,
    action: AuditAction,
    options: {
      severity?: AuditSeverity;
      actorId: string;
      actorType?: ActorType;
      actorRole?: string;
      actorWallet?: string;
      resourceType: string;
      resourceId: string;
      resourceName?: string;
      description: string;
      metadata?: Record<string, unknown>;
      success?: boolean;
      errorCode?: string;
      errorMessage?: string;
      snapshotHash?: string;
    }
  ): Promise<void> {
    const event: Omit<AuditEvent, 'id' | 'timestamp' | 'hash' | 'previousHash'> = {
      category,
      action,
      severity: options.severity || AuditSeverity.INFO,
      actorId: options.actorId,
      actorType: options.actorType || ActorType.USER,
      actorRole: options.actorRole,
      actorWallet: options.actorWallet,
      resourceType: options.resourceType,
      resourceId: options.resourceId,
      resourceName: options.resourceName,
      description: options.description,
      metadata: options.metadata || {},
      success: options.success !== false,
      errorCode: options.errorCode,
      errorMessage: options.errorMessage,
      snapshotHash: options.snapshotHash,
    };
    
    // In production, this would call an API
    const timestamp = Date.now();
    const id = `evt-${timestamp}-${Math.random().toString(36).substr(2, 9)}`;
    const hashInput = JSON.stringify({ id, timestamp, ...event, previousHash: lastHash });
    const hash = await sha256(hashInput);
    
    const fullEvent: AuditEvent = {
      ...event,
      id,
      timestamp,
      previousHash: lastHash,
      hash,
    };
    
    lastHash = hash;
    auditEvents = [...auditEvents, fullEvent];
    
    // Console log in development
    if (process.env.NODE_ENV === 'development') {
      console.log(`[AUDIT] ${category}.${action}:`, fullEvent);
    }
  }
}

export const auditLogger = AuditLogger.getInstance();
