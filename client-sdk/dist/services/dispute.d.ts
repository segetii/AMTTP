/**
 * Dispute Service
 * Wraps /dispute endpoints for Kleros-based dispute resolution
 */
import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
import { BaseService } from './base';
export type DisputeStatus = 'open' | 'in_review' | 'awaiting_evidence' | 'resolved' | 'appealed' | 'closed';
export type DisputeRuling = 'claimant_wins' | 'respondent_wins' | 'split' | 'dismissed';
export interface Dispute {
    id: string;
    klerosDisputeId?: string;
    transactionId: string;
    transactionHash?: string;
    claimant: string;
    respondent: string;
    amount: string;
    reason: string;
    category: 'fraud' | 'non_delivery' | 'quality' | 'unauthorized' | 'other';
    status: DisputeStatus;
    ruling?: DisputeRuling;
    evidence: Evidence[];
    timeline: TimelineEvent[];
    arbitrationCost?: string;
    createdAt: string;
    updatedAt: string;
    resolvedAt?: string;
}
export interface Evidence {
    id: string;
    type: 'document' | 'screenshot' | 'communication' | 'blockchain_data' | 'other';
    title: string;
    description?: string;
    contentHash: string;
    submittedBy: string;
    submittedAt: string;
}
export interface TimelineEvent {
    event: string;
    timestamp: string;
    actor?: string;
    details?: Record<string, any>;
}
export interface DisputeCreateRequest {
    transactionId: string;
    reason: string;
    category: 'fraud' | 'non_delivery' | 'quality' | 'unauthorized' | 'other';
    description: string;
    evidence?: {
        type: Evidence['type'];
        title: string;
        description?: string;
        contentHash: string;
    }[];
}
export interface DisputeListOptions {
    status?: DisputeStatus;
    claimant?: string;
    respondent?: string;
    category?: string;
    limit?: number;
    offset?: number;
    sortBy?: 'createdAt' | 'amount' | 'status';
    sortOrder?: 'asc' | 'desc';
}
export declare class DisputeService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Create a new dispute
     */
    create(request: DisputeCreateRequest): Promise<Dispute>;
    /**
     * Get dispute by ID
     */
    get(id: string): Promise<Dispute>;
    /**
     * Get dispute by Kleros dispute ID
     */
    getByKlerosId(klerosDisputeId: string): Promise<Dispute>;
    /**
     * List disputes
     */
    list(options?: DisputeListOptions): Promise<{
        disputes: Dispute[];
        total: number;
        hasMore: boolean;
    }>;
    /**
     * Submit evidence for a dispute
     */
    submitEvidence(disputeId: string, evidence: {
        type: Evidence['type'];
        title: string;
        description?: string;
        contentHash: string;
    }): Promise<Evidence>;
    /**
     * Get evidence for a dispute
     */
    getEvidence(disputeId: string): Promise<Evidence[]>;
    /**
     * Escalate dispute to Kleros
     */
    escalateToKleros(disputeId: string): Promise<{
        klerosDisputeId: string;
        arbitrationCost: string;
        estimatedResolutionTime: string;
    }>;
    /**
     * Get arbitration cost estimate
     */
    getArbitrationCost(category: string): Promise<{
        cost: string;
        currency: string;
        estimatedDuration: string;
    }>;
    /**
     * Accept dispute resolution
     */
    acceptResolution(disputeId: string): Promise<Dispute>;
    /**
     * Appeal dispute ruling
     */
    appeal(disputeId: string, reason: string): Promise<{
        appealId: string;
        appealCost: string;
        deadline: string;
    }>;
    /**
     * Withdraw dispute
     */
    withdraw(disputeId: string, reason?: string): Promise<Dispute>;
    /**
     * Get dispute statistics
     */
    getStatistics(address?: string): Promise<{
        total: number;
        byStatus: Record<DisputeStatus, number>;
        byCategory: Record<string, number>;
        averageResolutionTime: number;
        winRate?: number;
    }>;
    /**
     * Get dispute timeline
     */
    getTimeline(disputeId: string): Promise<TimelineEvent[]>;
    /**
     * Check if dispute is eligible for arbitration
     */
    checkEligibility(disputeId: string): Promise<{
        eligible: boolean;
        reason?: string;
        requirements?: string[];
    }>;
}
//# sourceMappingURL=dispute.d.ts.map