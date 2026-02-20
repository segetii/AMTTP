/**
 * EDD (Enhanced Due Diligence) Service
 * Wraps /edd endpoints for EDD case management
 */
import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
import { BaseService } from './base';
export type EDDStatus = 'pending' | 'in_review' | 'awaiting_documents' | 'approved' | 'rejected' | 'escalated';
export type EDDTrigger = 'high_risk_score' | 'pep_match' | 'large_transaction' | 'suspicious_pattern' | 'manual_request' | 'regulatory_requirement';
export interface EDDCase {
    id: string;
    address: string;
    status: EDDStatus;
    trigger: EDDTrigger;
    triggerDetails: Record<string, any>;
    riskScore: number;
    assignedTo?: string;
    documents: EDDDocument[];
    notes: EDDNote[];
    timeline: EDDTimelineEvent[];
    createdAt: string;
    updatedAt: string;
    resolvedAt?: string;
    resolution?: {
        decision: 'approved' | 'rejected';
        reason: string;
        resolvedBy: string;
    };
}
export interface EDDDocument {
    id: string;
    type: string;
    name: string;
    contentHash: string;
    mimeType: string;
    status: 'pending' | 'verified' | 'rejected';
    uploadedAt: string;
    verifiedAt?: string;
    verifiedBy?: string;
    rejectionReason?: string;
}
export interface EDDNote {
    id: string;
    content: string;
    createdBy: string;
    createdAt: string;
    visibility: 'internal' | 'customer_visible';
}
export interface EDDTimelineEvent {
    event: string;
    timestamp: string;
    actor?: string;
    details?: Record<string, any>;
}
export interface EDDCreateRequest {
    address: string;
    trigger: EDDTrigger;
    triggerDetails?: Record<string, any>;
    priority?: 'low' | 'medium' | 'high' | 'urgent';
    notes?: string;
}
export interface EDDListOptions {
    status?: EDDStatus;
    trigger?: EDDTrigger;
    assignedTo?: string;
    priority?: string;
    limit?: number;
    offset?: number;
    sortBy?: 'createdAt' | 'updatedAt' | 'riskScore';
    sortOrder?: 'asc' | 'desc';
}
export declare class EDDService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Create an EDD case
     */
    create(request: EDDCreateRequest): Promise<EDDCase>;
    /**
     * Get EDD case by ID
     */
    get(id: string): Promise<EDDCase>;
    /**
     * Get EDD case for an address
     */
    getByAddress(address: string): Promise<EDDCase | null>;
    /**
     * List EDD cases
     */
    list(options?: EDDListOptions): Promise<{
        cases: EDDCase[];
        total: number;
        hasMore: boolean;
    }>;
    /**
     * Assign EDD case to reviewer
     */
    assign(id: string, assignee: string): Promise<EDDCase>;
    /**
     * Update EDD case status
     */
    updateStatus(id: string, status: EDDStatus, note?: string): Promise<EDDCase>;
    /**
     * Upload document for EDD case
     */
    uploadDocument(id: string, document: {
        type: string;
        name: string;
        contentHash: string;
        mimeType: string;
    }): Promise<EDDDocument>;
    /**
     * Get documents for EDD case
     */
    getDocuments(id: string): Promise<EDDDocument[]>;
    /**
     * Verify document
     */
    verifyDocument(caseId: string, documentId: string, decision: {
        verified: boolean;
        reason?: string;
        verifiedBy: string;
    }): Promise<EDDDocument>;
    /**
     * Add note to EDD case
     */
    addNote(id: string, note: {
        content: string;
        visibility?: 'internal' | 'customer_visible';
    }): Promise<EDDNote>;
    /**
     * Get notes for EDD case
     */
    getNotes(id: string): Promise<EDDNote[]>;
    /**
     * Resolve EDD case
     */
    resolve(id: string, resolution: {
        decision: 'approved' | 'rejected';
        reason: string;
        resolvedBy: string;
    }): Promise<EDDCase>;
    /**
     * Escalate EDD case
     */
    escalate(id: string, reason: string, escalateTo?: string): Promise<EDDCase>;
    /**
     * Get EDD case timeline
     */
    getTimeline(id: string): Promise<EDDTimelineEvent[]>;
    /**
     * Get EDD requirements for a trigger type
     */
    getRequirements(trigger: EDDTrigger): Promise<{
        requiredDocuments: string[];
        requiredChecks: string[];
        estimatedDuration: string;
    }>;
    /**
     * Get EDD statistics
     */
    getStatistics(): Promise<{
        totalCases: number;
        byStatus: Record<EDDStatus, number>;
        byTrigger: Record<EDDTrigger, number>;
        averageResolutionTime: number;
        approvalRate: number;
    }>;
    /**
     * Check if address requires EDD
     */
    checkRequired(address: string): Promise<{
        required: boolean;
        reasons: EDDTrigger[];
        existingCase?: string;
    }>;
}
//# sourceMappingURL=edd.d.ts.map