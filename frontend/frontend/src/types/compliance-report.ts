/**
 * Compliance Report Types
 * 
 * Sprint 11: Compliance Reporting & Export System
 * 
 * Ground Truth Reference:
 * - PDF/JSON export for regulators
 * - Snapshot explorer for audit replay
 * - Evidence linking for complete audit trails
 * - Chain replay tool for UI state reconstruction
 */

// ═══════════════════════════════════════════════════════════════════════════════
// SNAPSHOT TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface UISnapshot {
  id: string;
  timestamp: string;
  userId: string;
  sessionId: string;
  screenId: string;
  screenName: string;
  version: string;
  
  // State hash for verification
  stateHash: string;
  previousHash: string;
  
  // Component state
  components: SnapshotComponent[];
  
  // User context at snapshot time
  userContext: {
    role: string;
    permissions: string[];
    mode: 'focus' | 'war-room';
    activeView: string;
  };
  
  // Transaction context (if applicable)
  transactionContext?: {
    transactionId: string;
    transactionHash?: string;
    action: string;
    amount?: string;
    recipient?: string;
  };
  
  // Integrity verification
  integrityProof: {
    merkleRoot: string;
    merkleProof: string[];
    onChainAnchor?: string;
    blockNumber?: number;
    verified: boolean;
  };
}

export interface SnapshotComponent {
  id: string;
  type: string;
  name: string;
  props: Record<string, unknown>;
  state: Record<string, unknown>;
  visible: boolean;
  interacted: boolean;
}

export interface SnapshotFilter {
  startDate?: string;
  endDate?: string;
  userId?: string;
  screenId?: string;
  transactionId?: string;
  verified?: boolean;
}

// ═══════════════════════════════════════════════════════════════════════════════
// EVIDENCE TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export enum EvidenceType {
  UI_SNAPSHOT = 'UI_SNAPSHOT',
  TRANSACTION = 'TRANSACTION',
  SIGNATURE = 'SIGNATURE',
  AUDIT_LOG = 'AUDIT_LOG',
  DOCUMENT = 'DOCUMENT',
  CHAIN_DATA = 'CHAIN_DATA',
  USER_INPUT = 'USER_INPUT',
  SYSTEM_EVENT = 'SYSTEM_EVENT',
}

export enum EvidenceStatus {
  PENDING = 'PENDING',
  VERIFIED = 'VERIFIED',
  DISPUTED = 'DISPUTED',
  INVALID = 'INVALID',
}

export interface Evidence {
  id: string;
  type: EvidenceType;
  status: EvidenceStatus;
  timestamp: string;
  
  // Reference to related entities
  relatedSnapshots: string[];
  relatedTransactions: string[];
  relatedAuditEvents: string[];
  
  // Content
  title: string;
  description: string;
  contentHash: string;
  content?: unknown;
  
  // Metadata
  submittedBy: string;
  submittedAt: string;
  verifiedBy?: string;
  verifiedAt?: string;
  
  // Chain verification
  onChainReference?: string;
  blockNumber?: number;
}

export interface EvidenceLink {
  id: string;
  sourceId: string;
  sourceType: 'snapshot' | 'transaction' | 'audit' | 'evidence';
  targetId: string;
  targetType: 'snapshot' | 'transaction' | 'audit' | 'evidence';
  relationship: 'precedes' | 'follows' | 'verifies' | 'references' | 'triggers';
  createdAt: string;
  createdBy: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// COMPLIANCE REPORT TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export enum ReportType {
  REGULATORY = 'REGULATORY',
  INCIDENT = 'INCIDENT',
  AUDIT = 'AUDIT',
  TRANSACTION = 'TRANSACTION',
  COMPLIANCE = 'COMPLIANCE',
  CUSTOM = 'CUSTOM',
}

export enum ReportFormat {
  JSON = 'JSON',
  PDF = 'PDF',
  CSV = 'CSV',
  HTML = 'HTML',
}

export enum ReportStatus {
  DRAFT = 'DRAFT',
  GENERATING = 'GENERATING',
  READY = 'READY',
  EXPORTED = 'EXPORTED',
  ARCHIVED = 'ARCHIVED',
  ERROR = 'ERROR',
}

export interface ComplianceReport {
  id: string;
  title: string;
  type: ReportType;
  status: ReportStatus;
  format: ReportFormat;
  
  // Time range
  periodStart: string;
  periodEnd: string;
  
  // Content
  sections: ReportSection[];
  summary: ReportSummary;
  
  // Metadata
  createdBy: string;
  createdAt: string;
  exportedAt?: string;
  exportCount: number;
  
  // Integrity
  contentHash: string;
  signature?: string;
  signedBy?: string;
  signedAt?: string;
}

export interface ReportSection {
  id: string;
  title: string;
  type: 'summary' | 'transactions' | 'snapshots' | 'evidence' | 'audit' | 'analysis' | 'custom';
  content: unknown;
  order: number;
}

export interface ReportSummary {
  totalTransactions: number;
  totalSnapshots: number;
  totalEvidence: number;
  totalAuditEvents: number;
  
  riskDistribution: {
    high: number;
    medium: number;
    low: number;
  };
  
  complianceScore: number;
  integrityScore: number;
  verifiedPercentage: number;
  
  keyFindings: string[];
  recommendations: string[];
}

export interface ReportTemplate {
  id: string;
  name: string;
  type: ReportType;
  description: string;
  sections: string[];
  defaultFormat: ReportFormat;
  isDefault: boolean;
}

// ═══════════════════════════════════════════════════════════════════════════════
// CHAIN REPLAY TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface ReplaySession {
  id: string;
  name: string;
  description?: string;
  
  // Time range to replay
  startTime: string;
  endTime: string;
  
  // Filter criteria
  userId?: string;
  transactionId?: string;
  sessionId?: string;
  
  // Replay state
  status: 'idle' | 'loading' | 'playing' | 'paused' | 'complete';
  currentSnapshotIndex: number;
  totalSnapshots: number;
  playbackSpeed: number;
  
  // Loaded snapshots
  snapshots: UISnapshot[];
  
  // Metadata
  createdAt: string;
  createdBy: string;
}

export interface ReplayStep {
  index: number;
  snapshot: UISnapshot;
  timestamp: string;
  changes: SnapshotDiff[];
  userAction?: string;
}

export interface SnapshotDiff {
  componentId: string;
  componentName: string;
  field: string;
  previousValue: unknown;
  newValue: unknown;
  changeType: 'added' | 'modified' | 'removed';
}

// ═══════════════════════════════════════════════════════════════════════════════
// EXPORT TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface ExportConfig {
  format: ReportFormat;
  includeSnapshots: boolean;
  includeEvidence: boolean;
  includeAuditLogs: boolean;
  includeChainData: boolean;
  includeSignatures: boolean;
  
  // PDF-specific
  letterhead?: boolean;
  digitalSignature?: boolean;
  watermark?: string;
  
  // Encryption
  encrypted?: boolean;
  password?: string;
}

export interface ExportResult {
  success: boolean;
  format: ReportFormat;
  fileName: string;
  fileSize: number;
  downloadUrl?: string;
  contentHash: string;
  exportedAt: string;
  error?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

export function formatSnapshotDate(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function getEvidenceTypeLabel(type: EvidenceType): string {
  const labels: Record<EvidenceType, string> = {
    [EvidenceType.UI_SNAPSHOT]: 'UI Snapshot',
    [EvidenceType.TRANSACTION]: 'Transaction',
    [EvidenceType.SIGNATURE]: 'Signature',
    [EvidenceType.AUDIT_LOG]: 'Audit Log',
    [EvidenceType.DOCUMENT]: 'Document',
    [EvidenceType.CHAIN_DATA]: 'Chain Data',
    [EvidenceType.USER_INPUT]: 'User Input',
    [EvidenceType.SYSTEM_EVENT]: 'System Event',
  };
  return labels[type];
}

export function getEvidenceStatusColor(status: EvidenceStatus): string {
  const colors: Record<EvidenceStatus, string> = {
    [EvidenceStatus.PENDING]: 'text-yellow-400',
    [EvidenceStatus.VERIFIED]: 'text-green-400',
    [EvidenceStatus.DISPUTED]: 'text-orange-400',
    [EvidenceStatus.INVALID]: 'text-red-400',
  };
  return colors[status];
}

export function getReportTypeLabel(type: ReportType): string {
  const labels: Record<ReportType, string> = {
    [ReportType.REGULATORY]: 'Regulatory Report',
    [ReportType.INCIDENT]: 'Incident Report',
    [ReportType.AUDIT]: 'Audit Report',
    [ReportType.TRANSACTION]: 'Transaction Report',
    [ReportType.COMPLIANCE]: 'Compliance Report',
    [ReportType.CUSTOM]: 'Custom Report',
  };
  return labels[type];
}

export function getReportStatusColor(status: ReportStatus): string {
  const colors: Record<ReportStatus, string> = {
    [ReportStatus.DRAFT]: 'text-slate-400',
    [ReportStatus.GENERATING]: 'text-cyan-400',
    [ReportStatus.READY]: 'text-green-400',
    [ReportStatus.EXPORTED]: 'text-blue-400',
    [ReportStatus.ARCHIVED]: 'text-slate-500',
    [ReportStatus.ERROR]: 'text-red-400',
  };
  return colors[status];
}

export function truncateHash(hash: string, length: number = 8): string {
  if (hash.length <= length * 2 + 2) return hash;
  return `${hash.slice(0, length + 2)}...${hash.slice(-length)}`;
}
