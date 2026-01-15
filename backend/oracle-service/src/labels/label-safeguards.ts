/**
 * AMTTP Label Pipeline Safeguards
 * RBAC, dual-control, and provenance tracking for /label/submit
 * Prevents model poisoning and ensures audit trail
 */

import { createHash, randomUUID } from 'crypto';

// ═══════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════

export type LabelType = 
  | 'FRAUD'
  | 'LEGITIMATE'
  | 'SUSPICIOUS'
  | 'FALSE_POSITIVE'
  | 'FALSE_NEGATIVE'
  | 'SANCTIONED'
  | 'PEP'
  | 'HIGH_RISK'
  | 'LOW_RISK';

export type LabelImpact = 'HIGH' | 'MEDIUM' | 'LOW';

export type Role = 
  | 'ANALYST'
  | 'SENIOR_ANALYST'
  | 'COMPLIANCE_OFFICER'
  | 'MLRO'           // Money Laundering Reporting Officer
  | 'SYSTEM_ADMIN'
  | 'AUDITOR';

export interface User {
  id: string;
  email: string;
  roles: Role[];
  department: string;
  createdAt: Date;
  lastActive: Date;
  mfaEnabled: boolean;
}

export interface LabelSubmission {
  id: string;
  transactionId: string;
  addressLabeled: string;
  labelType: LabelType;
  confidence: number;
  evidence: string;
  evidenceHash: string;
  submittedBy: string;
  submittedAt: Date;
  ipAddress: string;
  userAgent: string;
  sessionId: string;
}

export interface LabelApproval {
  id: string;
  labelSubmissionId: string;
  approvedBy: string;
  approvedAt: Date;
  decision: 'APPROVED' | 'REJECTED' | 'NEEDS_INFO';
  comments: string;
  ipAddress: string;
}

export interface LabelRecord {
  submission: LabelSubmission;
  approvals: LabelApproval[];
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'APPLIED';
  impact: LabelImpact;
  requiredApprovals: number;
  appliedToModel: boolean;
  appliedAt?: Date;
  provenanceHash: string;
}

// ═══════════════════════════════════════════════════════════════════════════
// RBAC CONFIGURATION
// ═══════════════════════════════════════════════════════════════════════════

interface RolePermissions {
  canSubmitLabels: boolean;
  canApproveLabels: boolean;
  canApproveHighImpact: boolean;
  canViewAuditLogs: boolean;
  canExportLabels: boolean;
  canDeleteLabels: boolean;
  canConfigureRules: boolean;
}

const ROLE_PERMISSIONS: Record<Role, RolePermissions> = {
  ANALYST: {
    canSubmitLabels: true,
    canApproveLabels: false,
    canApproveHighImpact: false,
    canViewAuditLogs: false,
    canExportLabels: false,
    canDeleteLabels: false,
    canConfigureRules: false,
  },
  SENIOR_ANALYST: {
    canSubmitLabels: true,
    canApproveLabels: true,
    canApproveHighImpact: false,
    canViewAuditLogs: true,
    canExportLabels: false,
    canDeleteLabels: false,
    canConfigureRules: false,
  },
  COMPLIANCE_OFFICER: {
    canSubmitLabels: true,
    canApproveLabels: true,
    canApproveHighImpact: true,
    canViewAuditLogs: true,
    canExportLabels: true,
    canDeleteLabels: false,
    canConfigureRules: false,
  },
  MLRO: {
    canSubmitLabels: true,
    canApproveLabels: true,
    canApproveHighImpact: true,
    canViewAuditLogs: true,
    canExportLabels: true,
    canDeleteLabels: true,
    canConfigureRules: true,
  },
  SYSTEM_ADMIN: {
    canSubmitLabels: false,
    canApproveLabels: false,
    canApproveHighImpact: false,
    canViewAuditLogs: true,
    canExportLabels: true,
    canDeleteLabels: false,
    canConfigureRules: true,
  },
  AUDITOR: {
    canSubmitLabels: false,
    canApproveLabels: false,
    canApproveHighImpact: false,
    canViewAuditLogs: true,
    canExportLabels: true,
    canDeleteLabels: false,
    canConfigureRules: false,
  },
};

// High-impact labels require dual control (2 approvers from different roles)
const HIGH_IMPACT_LABELS: LabelType[] = ['FRAUD', 'SANCTIONED', 'PEP', 'FALSE_NEGATIVE'];
const DUAL_CONTROL_LABELS: LabelType[] = ['FRAUD', 'SANCTIONED'];

// ═══════════════════════════════════════════════════════════════════════════
// LABEL SAFEGUARDS SERVICE
// ═══════════════════════════════════════════════════════════════════════════

export class LabelSafeguards {
  private labels: Map<string, LabelRecord> = new Map();
  private auditLog: Array<{
    action: string;
    labelId: string;
    userId: string;
    timestamp: Date;
    details: object;
  }> = [];

  /**
   * Check if user has permission for action
   */
  hasPermission(user: User, permission: keyof RolePermissions): boolean {
    return user.roles.some(role => ROLE_PERMISSIONS[role][permission]);
  }

  /**
   * Determine impact level of a label
   */
  private determineImpact(labelType: LabelType, confidence: number): LabelImpact {
    if (HIGH_IMPACT_LABELS.includes(labelType)) return 'HIGH';
    if (confidence > 0.9) return 'MEDIUM';
    return 'LOW';
  }

  /**
   * Get required number of approvals based on impact
   */
  private getRequiredApprovals(labelType: LabelType, impact: LabelImpact): number {
    if (DUAL_CONTROL_LABELS.includes(labelType)) return 2;
    if (impact === 'HIGH') return 2;
    if (impact === 'MEDIUM') return 1;
    return 1;
  }

  /**
   * Submit a new label (requires RBAC check)
   */
  async submitLabel(
    user: User,
    submission: Omit<LabelSubmission, 'id' | 'submittedBy' | 'submittedAt' | 'evidenceHash'>
  ): Promise<LabelRecord> {
    // RBAC check
    if (!this.hasPermission(user, 'canSubmitLabels')) {
      throw new Error(`User ${user.id} lacks permission to submit labels`);
    }

    // MFA check for high-impact labels
    if (HIGH_IMPACT_LABELS.includes(submission.labelType) && !user.mfaEnabled) {
      throw new Error('MFA required for high-impact labels');
    }

    const id = randomUUID();
    const evidenceHash = createHash('sha256').update(submission.evidence).digest('hex');
    const impact = this.determineImpact(submission.labelType, submission.confidence);

    const fullSubmission: LabelSubmission = {
      ...submission,
      id,
      submittedBy: user.id,
      submittedAt: new Date(),
      evidenceHash,
    };

    const record: LabelRecord = {
      submission: fullSubmission,
      approvals: [],
      status: 'PENDING',
      impact,
      requiredApprovals: this.getRequiredApprovals(submission.labelType, impact),
      appliedToModel: false,
      provenanceHash: this.computeProvenanceHash(fullSubmission),
    };

    this.labels.set(id, record);
    this.logAction('LABEL_SUBMITTED', id, user.id, { labelType: submission.labelType, impact });

    return record;
  }

  /**
   * Approve or reject a label (requires RBAC + dual control checks)
   */
  async approveLabel(
    user: User,
    labelId: string,
    decision: LabelApproval['decision'],
    comments: string,
    ipAddress: string
  ): Promise<LabelRecord> {
    const record = this.labels.get(labelId);
    if (!record) throw new Error(`Label ${labelId} not found`);

    // RBAC check
    if (!this.hasPermission(user, 'canApproveLabels')) {
      throw new Error(`User ${user.id} lacks permission to approve labels`);
    }

    // High-impact check
    if (record.impact === 'HIGH' && !this.hasPermission(user, 'canApproveHighImpact')) {
      throw new Error(`User ${user.id} lacks permission to approve high-impact labels`);
    }

    // Self-approval check (submitter cannot approve own label)
    if (record.submission.submittedBy === user.id) {
      throw new Error('Cannot approve your own label submission');
    }

    // Duplicate approval check
    if (record.approvals.some(a => a.approvedBy === user.id)) {
      throw new Error('You have already reviewed this label');
    }

    // Dual control: different roles for high-impact
    if (DUAL_CONTROL_LABELS.includes(record.submission.labelType)) {
      const existingApproverRoles = record.approvals
        .filter(a => a.decision === 'APPROVED')
        .map(a => this.getUserRoles(a.approvedBy))
        .flat();
      
      const hasRoleOverlap = user.roles.some(role => existingApproverRoles.includes(role));
      if (hasRoleOverlap && record.approvals.length > 0) {
        throw new Error('Dual control requires approvers from different roles');
      }
    }

    const approval: LabelApproval = {
      id: randomUUID(),
      labelSubmissionId: labelId,
      approvedBy: user.id,
      approvedAt: new Date(),
      decision,
      comments,
      ipAddress,
    };

    record.approvals.push(approval);
    this.logAction('LABEL_REVIEWED', labelId, user.id, { decision, comments });

    // Check if we have enough approvals
    const approvalCount = record.approvals.filter(a => a.decision === 'APPROVED').length;
    const rejectionCount = record.approvals.filter(a => a.decision === 'REJECTED').length;

    if (rejectionCount > 0) {
      record.status = 'REJECTED';
      this.logAction('LABEL_REJECTED', labelId, 'SYSTEM', { rejectedBy: user.id });
    } else if (approvalCount >= record.requiredApprovals) {
      record.status = 'APPROVED';
      this.logAction('LABEL_APPROVED', labelId, 'SYSTEM', { approvalCount });
    }

    // Update provenance
    record.provenanceHash = this.computeProvenanceHash(record.submission, record.approvals);
    this.labels.set(labelId, record);

    return record;
  }

  /**
   * Apply approved label to model training data
   */
  async applyToModel(labelId: string): Promise<LabelRecord> {
    const record = this.labels.get(labelId);
    if (!record) throw new Error(`Label ${labelId} not found`);

    if (record.status !== 'APPROVED') {
      throw new Error('Only approved labels can be applied to model');
    }

    record.appliedToModel = true;
    record.appliedAt = new Date();
    record.status = 'APPLIED';
    
    this.logAction('LABEL_APPLIED', labelId, 'SYSTEM', { appliedAt: record.appliedAt });
    this.labels.set(labelId, record);

    return record;
  }

  /**
   * Get pending labels for review
   */
  getPendingLabels(impact?: LabelImpact): LabelRecord[] {
    return Array.from(this.labels.values())
      .filter(r => r.status === 'PENDING')
      .filter(r => !impact || r.impact === impact)
      .sort((a, b) => {
        // High impact first
        const impactOrder = { HIGH: 0, MEDIUM: 1, LOW: 2 };
        return impactOrder[a.impact] - impactOrder[b.impact];
      });
  }

  /**
   * Get audit log (requires permission)
   */
  getAuditLog(user: User, filters?: { labelId?: string; userId?: string; action?: string }): typeof this.auditLog {
    if (!this.hasPermission(user, 'canViewAuditLogs')) {
      throw new Error(`User ${user.id} lacks permission to view audit logs`);
    }

    let log = [...this.auditLog];
    if (filters?.labelId) log = log.filter(l => l.labelId === filters.labelId);
    if (filters?.userId) log = log.filter(l => l.userId === filters.userId);
    if (filters?.action) log = log.filter(l => l.action === filters.action);
    
    return log;
  }

  /**
   * Export labels for FCA audit
   */
  exportForAudit(user: User): object {
    if (!this.hasPermission(user, 'canExportLabels')) {
      throw new Error(`User ${user.id} lacks permission to export labels`);
    }

    const records = Array.from(this.labels.values());
    
    return {
      exportedAt: new Date().toISOString(),
      exportedBy: user.id,
      totalLabels: records.length,
      byStatus: {
        pending: records.filter(r => r.status === 'PENDING').length,
        approved: records.filter(r => r.status === 'APPROVED').length,
        rejected: records.filter(r => r.status === 'REJECTED').length,
        applied: records.filter(r => r.status === 'APPLIED').length,
      },
      byImpact: {
        high: records.filter(r => r.impact === 'HIGH').length,
        medium: records.filter(r => r.impact === 'MEDIUM').length,
        low: records.filter(r => r.impact === 'LOW').length,
      },
      labels: records.map(r => ({
        id: r.submission.id,
        transactionId: r.submission.transactionId,
        labelType: r.submission.labelType,
        status: r.status,
        impact: r.impact,
        submittedBy: r.submission.submittedBy,
        submittedAt: r.submission.submittedAt,
        approvals: r.approvals.length,
        provenanceHash: r.provenanceHash,
      })),
      auditLogHash: createHash('sha256')
        .update(JSON.stringify(this.auditLog))
        .digest('hex'),
    };
  }

  private computeProvenanceHash(submission: LabelSubmission, approvals?: LabelApproval[]): string {
    const data = {
      submission: {
        id: submission.id,
        transactionId: submission.transactionId,
        labelType: submission.labelType,
        submittedBy: submission.submittedBy,
        submittedAt: submission.submittedAt.toISOString(),
        evidenceHash: submission.evidenceHash,
      },
      approvals: approvals?.map(a => ({
        id: a.id,
        approvedBy: a.approvedBy,
        decision: a.decision,
        approvedAt: a.approvedAt.toISOString(),
      })) || [],
    };
    return createHash('sha256').update(JSON.stringify(data)).digest('hex');
  }

  private logAction(action: string, labelId: string, userId: string, details: object): void {
    this.auditLog.push({
      action,
      labelId,
      userId,
      timestamp: new Date(),
      details,
    });
  }

  // Mock function - in production would look up from user store
  private getUserRoles(userId: string): Role[] {
    // This would query the user database
    return ['ANALYST'];
  }

  /**
   * Get statistics for dashboard
   */
  getStats(): object {
    const records = Array.from(this.labels.values());
    const now = new Date();
    const last24h = new Date(now.getTime() - 24 * 60 * 60 * 1000);

    return {
      total: records.length,
      pending: records.filter(r => r.status === 'PENDING').length,
      pendingHighImpact: records.filter(r => r.status === 'PENDING' && r.impact === 'HIGH').length,
      approved24h: records.filter(r => 
        r.status === 'APPROVED' && 
        r.approvals.some(a => a.approvedAt > last24h)
      ).length,
      avgApprovalTime: this.calculateAvgApprovalTime(records),
      dualControlPending: records.filter(r => 
        r.status === 'PENDING' && 
        DUAL_CONTROL_LABELS.includes(r.submission.labelType)
      ).length,
    };
  }

  private calculateAvgApprovalTime(records: LabelRecord[]): number {
    const approved = records.filter(r => r.status !== 'PENDING' && r.approvals.length > 0);
    if (approved.length === 0) return 0;

    const times = approved.map(r => {
      const lastApproval = r.approvals[r.approvals.length - 1];
      return lastApproval.approvedAt.getTime() - r.submission.submittedAt.getTime();
    });

    return times.reduce((a, b) => a + b, 0) / times.length / 1000 / 60; // minutes
  }
}

// Singleton
let safeguardsInstance: LabelSafeguards | null = null;

export function getLabelSafeguards(): LabelSafeguards {
  if (!safeguardsInstance) {
    safeguardsInstance = new LabelSafeguards();
  }
  return safeguardsInstance;
}

export default LabelSafeguards;
