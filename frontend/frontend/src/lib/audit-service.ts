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

const generateMockEvents = (): AuditEvent[] => {
  const events: AuditEvent[] = [
    {
      id: 'evt-001',
      timestamp: Date.now() - 3600000,
      category: AuditCategory.AUTHENTICATION,
      action: AuditAction.LOGIN,
      severity: AuditSeverity.INFO,
      actorId: 'user-001',
      actorType: ActorType.USER,
      actorRole: 'R3_COMPLIANCE',
      actorWallet: '0x742d35Cc6634C0532925a3b844Bc9e7595f7',
      resourceType: 'session',
      resourceId: 'sess-001',
      description: 'User logged in successfully via wallet connect',
      metadata: { method: 'wallet_connect', chain: 'ethereum' },
      ipAddress: '192.168.1.100',
      userAgent: 'Mozilla/5.0...',
      success: true,
      hash: 'abc123',
    },
    {
      id: 'evt-002',
      timestamp: Date.now() - 3500000,
      category: AuditCategory.TRANSFER,
      action: AuditAction.INITIATED,
      severity: AuditSeverity.NOTICE,
      actorId: 'user-001',
      actorType: ActorType.USER,
      actorRole: 'R3_COMPLIANCE',
      actorWallet: '0x742d35Cc6634C0532925a3b844Bc9e7595f7',
      resourceType: 'transfer',
      resourceId: 'tx-001',
      resourceName: 'USDC Transfer',
      description: 'Transfer of 50,000 USDC initiated',
      metadata: { amount: 50000, asset: 'USDC', recipient: '0x8ba1f...' },
      success: true,
      previousHash: 'abc123',
      hash: 'def456',
      snapshotHash: 'snap-001',
    },
    {
      id: 'evt-003',
      timestamp: Date.now() - 3400000,
      category: AuditCategory.POLICY,
      action: AuditAction.TRIGGERED,
      severity: AuditSeverity.WARNING,
      actorId: 'system',
      actorType: ActorType.SYSTEM,
      resourceType: 'policy',
      resourceId: 'pol-001',
      resourceName: 'High-Value Transfer Policy',
      description: 'Policy triggered: amount exceeds threshold',
      metadata: { threshold: 10000, amount: 50000, action: 'REQUIRE_APPROVAL' },
      success: true,
      previousHash: 'def456',
      hash: 'ghi789',
    },
    {
      id: 'evt-004',
      timestamp: Date.now() - 3300000,
      category: AuditCategory.MULTISIG,
      action: AuditAction.SIGNED,
      severity: AuditSeverity.INFO,
      actorId: 'user-002',
      actorType: ActorType.USER,
      actorRole: 'R5_CFO',
      actorWallet: '0x9ca1f109551bD432803012645Ac136ddd64DBA73',
      resourceType: 'multisig_proposal',
      resourceId: 'msig-001',
      description: 'Multisig proposal signed (2/3 required)',
      metadata: { proposalId: 'msig-001', signatureIndex: 1, requiredSignatures: 3 },
      success: true,
      previousHash: 'ghi789',
      hash: 'jkl012',
    },
    {
      id: 'evt-005',
      timestamp: Date.now() - 3200000,
      category: AuditCategory.TRANSFER,
      action: AuditAction.APPROVED,
      severity: AuditSeverity.NOTICE,
      actorId: 'user-003',
      actorType: ActorType.USER,
      actorRole: 'R6_CEO',
      actorWallet: '0x7ba1f109551bD432803012645Ac136ddd64DBA74',
      resourceType: 'transfer',
      resourceId: 'tx-001',
      description: 'Transfer approved via multisig (3/3 signatures)',
      metadata: { approvalChain: ['user-001', 'user-002', 'user-003'] },
      success: true,
      previousHash: 'jkl012',
      hash: 'mno345',
    },
    {
      id: 'evt-006',
      timestamp: Date.now() - 3100000,
      category: AuditCategory.TRANSFER,
      action: AuditAction.EXECUTED,
      severity: AuditSeverity.INFO,
      actorId: 'system',
      actorType: ActorType.CONTRACT,
      resourceType: 'transfer',
      resourceId: 'tx-001',
      description: 'Transfer executed on-chain',
      metadata: { txHash: '0x1234...', blockNumber: 18500000, gasUsed: 150000 },
      success: true,
      previousHash: 'mno345',
      hash: 'pqr678',
    },
    {
      id: 'evt-007',
      timestamp: Date.now() - 2000000,
      category: AuditCategory.AUTHENTICATION,
      action: AuditAction.LOGIN_FAILED,
      severity: AuditSeverity.WARNING,
      actorId: 'unknown',
      actorType: ActorType.USER,
      resourceType: 'session',
      resourceId: 'sess-002',
      description: 'Failed login attempt - invalid signature',
      metadata: { attemptedWallet: '0xabc...', reason: 'INVALID_SIGNATURE' },
      ipAddress: '10.0.0.50',
      success: false,
      errorCode: 'AUTH_001',
      errorMessage: 'Signature verification failed',
      previousHash: 'pqr678',
      hash: 'stu901',
    },
    {
      id: 'evt-008',
      timestamp: Date.now() - 1800000,
      category: AuditCategory.ESCROW,
      action: AuditAction.LOCKED,
      severity: AuditSeverity.INFO,
      actorId: 'user-001',
      actorType: ActorType.USER,
      actorRole: 'R3_COMPLIANCE',
      resourceType: 'escrow',
      resourceId: 'esc-001',
      description: 'Funds locked in escrow pending verification',
      metadata: { amount: 25000, asset: 'USDC', releaseConditions: ['KYC_VERIFIED', 'AML_CLEAR'] },
      success: true,
      previousHash: 'stu901',
      hash: 'vwx234',
    },
    {
      id: 'evt-009',
      timestamp: Date.now() - 600000,
      category: AuditCategory.COMPLIANCE,
      action: AuditAction.ALERT_TRIGGERED,
      severity: AuditSeverity.CRITICAL,
      actorId: 'aml-oracle',
      actorType: ActorType.ORACLE,
      resourceType: 'compliance_check',
      resourceId: 'chk-001',
      description: 'AML alert: recipient address flagged',
      metadata: { riskScore: 85, flags: ['SANCTIONED_ENTITY'], source: 'CHAINALYSIS' },
      success: true,
      previousHash: 'vwx234',
      hash: 'yza567',
    },
    {
      id: 'evt-010',
      timestamp: Date.now() - 300000,
      category: AuditCategory.DISPUTE,
      action: AuditAction.CREATE,
      severity: AuditSeverity.NOTICE,
      actorId: 'user-004',
      actorType: ActorType.USER,
      actorRole: 'R2_OPS',
      resourceType: 'dispute',
      resourceId: 'dsp-001',
      description: 'Dispute filed for transfer tx-002',
      metadata: { reason: 'UNAUTHORIZED_TRANSFER', relatedTransferId: 'tx-002', amountDisputed: 15000 },
      success: true,
      previousHash: 'yza567',
      hash: 'bcd890',
    },
  ];
  
  return events;
};

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
