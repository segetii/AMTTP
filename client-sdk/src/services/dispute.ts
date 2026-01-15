/**
 * Dispute Service
 * Wraps /dispute endpoints for Kleros-based dispute resolution
 */

import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
import { BaseService } from './base';

// Local type definitions
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

export class DisputeService extends BaseService {
  constructor(http: AxiosInstance, events: EventEmitter) {
    super(http, events);
  }

  /**
   * Create a new dispute
   */
  async create(request: DisputeCreateRequest): Promise<Dispute> {
    const response = await this.http.post<Dispute>('/dispute', request);
    
    this.events.emit('dispute:created', {
      id: response.data.id,
      transactionId: request.transactionId,
      category: request.category
    });

    return response.data;
  }

  /**
   * Get dispute by ID
   */
  async get(id: string): Promise<Dispute> {
    const response = await this.http.get<Dispute>(`/dispute/${id}`);
    return response.data;
  }

  /**
   * Get dispute by Kleros dispute ID
   */
  async getByKlerosId(klerosDisputeId: string): Promise<Dispute> {
    const response = await this.http.get<Dispute>(`/dispute/kleros/${klerosDisputeId}`);
    return response.data;
  }

  /**
   * List disputes
   */
  async list(options?: DisputeListOptions): Promise<{
    disputes: Dispute[];
    total: number;
    hasMore: boolean;
  }> {
    const params = new URLSearchParams();
    if (options?.status) params.append('status', options.status);
    if (options?.claimant) params.append('claimant', options.claimant);
    if (options?.respondent) params.append('respondent', options.respondent);
    if (options?.category) params.append('category', options.category);
    if (options?.limit) params.append('limit', options.limit.toString());
    if (options?.offset) params.append('offset', options.offset.toString());
    if (options?.sortBy) params.append('sortBy', options.sortBy);
    if (options?.sortOrder) params.append('sortOrder', options.sortOrder);

    const response = await this.http.get<{
      disputes: Dispute[];
      total: number;
      hasMore: boolean;
    }>(`/dispute?${params.toString()}`);

    return response.data;
  }

  /**
   * Submit evidence for a dispute
   */
  async submitEvidence(disputeId: string, evidence: {
    type: Evidence['type'];
    title: string;
    description?: string;
    contentHash: string;
  }): Promise<Evidence> {
    const response = await this.http.post<Evidence>(`/dispute/${disputeId}/evidence`, evidence);
    
    this.events.emit('dispute:evidenceSubmitted', {
      disputeId,
      evidenceId: response.data.id,
      type: evidence.type
    });

    return response.data;
  }

  /**
   * Get evidence for a dispute
   */
  async getEvidence(disputeId: string): Promise<Evidence[]> {
    const response = await this.http.get<{ evidence: Evidence[] }>(`/dispute/${disputeId}/evidence`);
    return response.data.evidence;
  }

  /**
   * Escalate dispute to Kleros
   */
  async escalateToKleros(disputeId: string): Promise<{
    klerosDisputeId: string;
    arbitrationCost: string;
    estimatedResolutionTime: string;
  }> {
    const response = await this.http.post(`/dispute/${disputeId}/escalate`);
    
    this.events.emit('dispute:escalated', {
      disputeId,
      klerosDisputeId: response.data.klerosDisputeId
    });

    return response.data;
  }

  /**
   * Get arbitration cost estimate
   */
  async getArbitrationCost(category: string): Promise<{
    cost: string;
    currency: string;
    estimatedDuration: string;
  }> {
    const response = await this.http.get(`/dispute/arbitration-cost?category=${category}`);
    return response.data;
  }

  /**
   * Accept dispute resolution
   */
  async acceptResolution(disputeId: string): Promise<Dispute> {
    const response = await this.http.post<Dispute>(`/dispute/${disputeId}/accept`);
    
    this.events.emit('dispute:resolutionAccepted', { disputeId });

    return response.data;
  }

  /**
   * Appeal dispute ruling
   */
  async appeal(disputeId: string, reason: string): Promise<{
    appealId: string;
    appealCost: string;
    deadline: string;
  }> {
    const response = await this.http.post(`/dispute/${disputeId}/appeal`, { reason });
    
    this.events.emit('dispute:appealed', {
      disputeId,
      appealId: response.data.appealId
    });

    return response.data;
  }

  /**
   * Withdraw dispute
   */
  async withdraw(disputeId: string, reason?: string): Promise<Dispute> {
    const response = await this.http.post<Dispute>(`/dispute/${disputeId}/withdraw`, { reason });
    
    this.events.emit('dispute:withdrawn', { disputeId });

    return response.data;
  }

  /**
   * Get dispute statistics
   */
  async getStatistics(address?: string): Promise<{
    total: number;
    byStatus: Record<DisputeStatus, number>;
    byCategory: Record<string, number>;
    averageResolutionTime: number;
    winRate?: number;
  }> {
    const url = address ? `/dispute/statistics?address=${address}` : '/dispute/statistics';
    const response = await this.http.get(url);
    return response.data;
  }

  /**
   * Get dispute timeline
   */
  async getTimeline(disputeId: string): Promise<TimelineEvent[]> {
    const response = await this.http.get<{ timeline: TimelineEvent[] }>(`/dispute/${disputeId}/timeline`);
    return response.data.timeline;
  }

  /**
   * Check if dispute is eligible for arbitration
   */
  async checkEligibility(disputeId: string): Promise<{
    eligible: boolean;
    reason?: string;
    requirements?: string[];
  }> {
    const response = await this.http.get(`/dispute/${disputeId}/eligibility`);
    return response.data;
  }
}
