/**
 * Audit Trail Types
 * 
 * Sprint 9: Audit Trail & Logging
 * 
 * Ground Truth Reference:
 * - Every action must be logged and attributable
 * - Immutable audit records for compliance
 * - Full chain of custody for regulatory review
 */

// ═══════════════════════════════════════════════════════════════════════════════
// AUDIT EVENT CATEGORIES
// ═══════════════════════════════════════════════════════════════════════════════

export enum AuditCategory {
  // Authentication & Access
  AUTHENTICATION = 'AUTHENTICATION',
  AUTHORIZATION = 'AUTHORIZATION',
  SESSION = 'SESSION',
  
  // Transfer Operations
  TRANSFER = 'TRANSFER',
  ESCROW = 'ESCROW',
  CROSS_CHAIN = 'CROSS_CHAIN',
  
  // Governance
  GOVERNANCE = 'GOVERNANCE',
  MULTISIG = 'MULTISIG',
  APPROVAL = 'APPROVAL',
  
  // Policy & Compliance
  POLICY = 'POLICY',
  COMPLIANCE = 'COMPLIANCE',
  DISPUTE = 'DISPUTE',
  
  // System
  SYSTEM = 'SYSTEM',
  CONFIGURATION = 'CONFIGURATION',
  SECURITY = 'SECURITY',
}

export enum AuditAction {
  // Auth actions
  LOGIN = 'LOGIN',
  LOGOUT = 'LOGOUT',
  LOGIN_FAILED = 'LOGIN_FAILED',
  SESSION_EXPIRED = 'SESSION_EXPIRED',
  MFA_VERIFIED = 'MFA_VERIFIED',
  MFA_FAILED = 'MFA_FAILED',
  
  // CRUD actions
  CREATE = 'CREATE',
  READ = 'READ',
  UPDATE = 'UPDATE',
  DELETE = 'DELETE',
  
  // Transfer actions
  INITIATED = 'INITIATED',
  APPROVED = 'APPROVED',
  REJECTED = 'REJECTED',
  EXECUTED = 'EXECUTED',
  CANCELLED = 'CANCELLED',
  FAILED = 'FAILED',
  
  // Escrow actions
  LOCKED = 'LOCKED',
  RELEASED = 'RELEASED',
  REFUNDED = 'REFUNDED',
  
  // Policy actions
  ACTIVATED = 'ACTIVATED',
  DEACTIVATED = 'DEACTIVATED',
  TRIGGERED = 'TRIGGERED',
  
  // Governance actions
  PROPOSED = 'PROPOSED',
  VOTED = 'VOTED',
  SIGNED = 'SIGNED',
  
  // System actions
  STARTED = 'STARTED',
  STOPPED = 'STOPPED',
  CONFIGURED = 'CONFIGURED',
  ALERT_TRIGGERED = 'ALERT_TRIGGERED',
}

// ═══════════════════════════════════════════════════════════════════════════════
// AUDIT SEVERITY
// ═══════════════════════════════════════════════════════════════════════════════

export enum AuditSeverity {
  DEBUG = 'DEBUG',     // Development only
  INFO = 'INFO',       // Normal operations
  NOTICE = 'NOTICE',   // Notable events
  WARNING = 'WARNING', // Potential issues
  ERROR = 'ERROR',     // Errors
  CRITICAL = 'CRITICAL', // Critical security/compliance
  ALERT = 'ALERT',     // Requires immediate attention
}

// ═══════════════════════════════════════════════════════════════════════════════
// AUDIT EVENT
// ═══════════════════════════════════════════════════════════════════════════════

export interface AuditEvent {
  id: string;
  timestamp: number;
  
  // Classification
  category: AuditCategory;
  action: AuditAction;
  severity: AuditSeverity;
  
  // Actor
  actorId: string;
  actorType: ActorType;
  actorRole?: string;
  actorWallet?: string;
  
  // Resource
  resourceType: string;
  resourceId: string;
  resourceName?: string;
  
  // Context
  description: string;
  metadata: Record<string, unknown>;
  
  // Request context
  requestId?: string;
  sessionId?: string;
  ipAddress?: string;
  userAgent?: string;
  
  // Result
  success: boolean;
  errorCode?: string;
  errorMessage?: string;
  
  // Integrity
  previousHash?: string;
  hash: string;
  signature?: string;
  
  // UI Snapshot (for UI actions)
  snapshotHash?: string;
}

export enum ActorType {
  USER = 'USER',
  SYSTEM = 'SYSTEM',
  SERVICE = 'SERVICE',
  CONTRACT = 'CONTRACT',
  ORACLE = 'ORACLE',
  SCHEDULER = 'SCHEDULER',
}

// ═══════════════════════════════════════════════════════════════════════════════
// AUDIT TRAIL
// ═══════════════════════════════════════════════════════════════════════════════

export interface AuditTrail {
  resourceType: string;
  resourceId: string;
  events: AuditEvent[];
  firstEvent: number;
  lastEvent: number;
  eventCount: number;
}

// ═══════════════════════════════════════════════════════════════════════════════
// AUDIT QUERY
// ═══════════════════════════════════════════════════════════════════════════════

export interface AuditQuery {
  // Time range
  startTime?: number;
  endTime?: number;
  
  // Filters
  categories?: AuditCategory[];
  actions?: AuditAction[];
  severities?: AuditSeverity[];
  actorIds?: string[];
  resourceTypes?: string[];
  resourceIds?: string[];
  
  // Search
  searchText?: string;
  
  // Flags
  successOnly?: boolean;
  failuresOnly?: boolean;
  
  // Pagination
  page?: number;
  pageSize?: number;
  sortBy?: 'timestamp' | 'severity' | 'category';
  sortOrder?: 'asc' | 'desc';
}

export interface AuditQueryResult {
  events: AuditEvent[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
  query: AuditQuery;
  executedAt: number;
}

// ═══════════════════════════════════════════════════════════════════════════════
// AUDIT REPORT
// ═══════════════════════════════════════════════════════════════════════════════

export interface AuditReport {
  id: string;
  name: string;
  description: string;
  
  // Time range
  startTime: number;
  endTime: number;
  
  // Generated data
  generatedAt: number;
  generatedBy: string;
  
  // Statistics
  stats: AuditStats;
  
  // Events (summary or full based on report type)
  eventsSummary: AuditEventSummary[];
  events?: AuditEvent[];
  
  // Export
  format: 'JSON' | 'CSV' | 'PDF';
  downloadUrl?: string;
}

export interface AuditStats {
  totalEvents: number;
  byCategory: Record<AuditCategory, number>;
  byAction: Record<AuditAction, number>;
  bySeverity: Record<AuditSeverity, number>;
  successCount: number;
  failureCount: number;
  uniqueActors: number;
  uniqueResources: number;
}

export interface AuditEventSummary {
  category: AuditCategory;
  action: AuditAction;
  count: number;
  successCount: number;
  failureCount: number;
  firstOccurrence: number;
  lastOccurrence: number;
}

// ═══════════════════════════════════════════════════════════════════════════════
// COMPLIANCE EVIDENCE
// ═══════════════════════════════════════════════════════════════════════════════

export interface ComplianceEvidence {
  id: string;
  type: EvidenceType;
  description: string;
  
  // Related events
  auditEventIds: string[];
  
  // Timestamps
  collectedAt: number;
  validFrom: number;
  validTo?: number;
  
  // Verification
  verified: boolean;
  verifiedBy?: string;
  verifiedAt?: number;
  
  // Attachments
  attachments: EvidenceAttachment[];
  
  // Hash for integrity
  hash: string;
}

export enum EvidenceType {
  TRANSFER_RECORD = 'TRANSFER_RECORD',
  KYC_VERIFICATION = 'KYC_VERIFICATION',
  AML_CHECK = 'AML_CHECK',
  POLICY_ENFORCEMENT = 'POLICY_ENFORCEMENT',
  APPROVAL_CHAIN = 'APPROVAL_CHAIN',
  DISPUTE_RESOLUTION = 'DISPUTE_RESOLUTION',
  SYSTEM_LOG = 'SYSTEM_LOG',
}

export interface EvidenceAttachment {
  id: string;
  name: string;
  type: string;
  size: number;
  hash: string;
  url: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

export function getSeverityColor(severity: AuditSeverity): string {
  const colors: Record<AuditSeverity, string> = {
    [AuditSeverity.DEBUG]: 'gray',
    [AuditSeverity.INFO]: 'blue',
    [AuditSeverity.NOTICE]: 'cyan',
    [AuditSeverity.WARNING]: 'yellow',
    [AuditSeverity.ERROR]: 'orange',
    [AuditSeverity.CRITICAL]: 'red',
    [AuditSeverity.ALERT]: 'red',
  };
  return colors[severity];
}

export function getCategoryIcon(category: AuditCategory): string {
  const icons: Record<AuditCategory, string> = {
    [AuditCategory.AUTHENTICATION]: '🔐',
    [AuditCategory.AUTHORIZATION]: '🛡️',
    [AuditCategory.SESSION]: '📱',
    [AuditCategory.TRANSFER]: '💸',
    [AuditCategory.ESCROW]: '🔒',
    [AuditCategory.CROSS_CHAIN]: '🌐',
    [AuditCategory.GOVERNANCE]: '🏛️',
    [AuditCategory.MULTISIG]: '✍️',
    [AuditCategory.APPROVAL]: '✅',
    [AuditCategory.POLICY]: '📋',
    [AuditCategory.COMPLIANCE]: '⚖️',
    [AuditCategory.DISPUTE]: '⚔️',
    [AuditCategory.SYSTEM]: '⚙️',
    [AuditCategory.CONFIGURATION]: '🔧',
    [AuditCategory.SECURITY]: '🚨',
  };
  return icons[category];
}

export function formatAuditTimestamp(timestamp: number): string {
  return new Date(timestamp).toISOString();
}
