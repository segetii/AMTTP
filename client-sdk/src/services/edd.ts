/**
 * EDD (Enhanced Due Diligence) Service
 * Wraps /edd endpoints for EDD case management
 */

import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
import { BaseService } from './base';

export type EDDStatus = 
  | 'pending'
  | 'in_review'
  | 'awaiting_documents'
  | 'approved'
  | 'rejected'
  | 'escalated';

export type EDDTrigger = 
  | 'high_risk_score'
  | 'pep_match'
  | 'large_transaction'
  | 'suspicious_pattern'
  | 'manual_request'
  | 'regulatory_requirement';

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

export class EDDService extends BaseService {
  constructor(http: AxiosInstance, events: EventEmitter) {
    super(http, events);
  }

  /**
   * Create an EDD case
   */
  async create(request: EDDCreateRequest): Promise<EDDCase> {
    const response = await this.http.post<EDDCase>('/edd', request);
    return response.data;
  }

  /**
   * Get EDD case by ID
   */
  async get(id: string): Promise<EDDCase> {
    const response = await this.http.get<EDDCase>(`/edd/${id}`);
    return response.data;
  }

  /**
   * Get EDD case for an address
   */
  async getByAddress(address: string): Promise<EDDCase | null> {
    try {
      const response = await this.http.get<EDDCase>(`/edd/address/${address}`);
      return response.data;
    } catch (error: any) {
      if (error.response?.status === 404) {
        return null;
      }
      throw error;
    }
  }

  /**
   * List EDD cases
   */
  async list(options?: EDDListOptions): Promise<{
    cases: EDDCase[];
    total: number;
    hasMore: boolean;
  }> {
    const params = new URLSearchParams();
    if (options?.status) params.append('status', options.status);
    if (options?.trigger) params.append('trigger', options.trigger);
    if (options?.assignedTo) params.append('assignedTo', options.assignedTo);
    if (options?.priority) params.append('priority', options.priority);
    if (options?.limit) params.append('limit', options.limit.toString());
    if (options?.offset) params.append('offset', options.offset.toString());
    if (options?.sortBy) params.append('sortBy', options.sortBy);
    if (options?.sortOrder) params.append('sortOrder', options.sortOrder);

    const response = await this.http.get<{
      cases: EDDCase[];
      total: number;
      hasMore: boolean;
    }>(`/edd?${params.toString()}`);

    return response.data;
  }

  /**
   * Assign EDD case to reviewer
   */
  async assign(id: string, assignee: string): Promise<EDDCase> {
    const response = await this.http.post<EDDCase>(`/edd/${id}/assign`, { assignee });
    return response.data;
  }

  /**
   * Update EDD case status
   */
  async updateStatus(id: string, status: EDDStatus, note?: string): Promise<EDDCase> {
    const response = await this.http.put<EDDCase>(`/edd/${id}/status`, { status, note });
    return response.data;
  }

  /**
   * Upload document for EDD case
   */
  async uploadDocument(id: string, document: {
    type: string;
    name: string;
    contentHash: string;
    mimeType: string;
  }): Promise<EDDDocument> {
    const response = await this.http.post<EDDDocument>(`/edd/${id}/documents`, document);
    return response.data;
  }

  /**
   * Get documents for EDD case
   */
  async getDocuments(id: string): Promise<EDDDocument[]> {
    const response = await this.http.get<{ documents: EDDDocument[] }>(`/edd/${id}/documents`);
    return response.data.documents;
  }

  /**
   * Verify document
   */
  async verifyDocument(caseId: string, documentId: string, decision: {
    verified: boolean;
    reason?: string;
    verifiedBy: string;
  }): Promise<EDDDocument> {
    const response = await this.http.post<EDDDocument>(
      `/edd/${caseId}/documents/${documentId}/verify`,
      decision
    );
    return response.data;
  }

  /**
   * Add note to EDD case
   */
  async addNote(id: string, note: {
    content: string;
    visibility?: 'internal' | 'customer_visible';
  }): Promise<EDDNote> {
    const response = await this.http.post<EDDNote>(`/edd/${id}/notes`, note);
    return response.data;
  }

  /**
   * Get notes for EDD case
   */
  async getNotes(id: string): Promise<EDDNote[]> {
    const response = await this.http.get<{ notes: EDDNote[] }>(`/edd/${id}/notes`);
    return response.data.notes;
  }

  /**
   * Resolve EDD case
   */
  async resolve(id: string, resolution: {
    decision: 'approved' | 'rejected';
    reason: string;
    resolvedBy: string;
  }): Promise<EDDCase> {
    const response = await this.http.post<EDDCase>(`/edd/${id}/resolve`, resolution);
    return response.data;
  }

  /**
   * Escalate EDD case
   */
  async escalate(id: string, reason: string, escalateTo?: string): Promise<EDDCase> {
    const response = await this.http.post<EDDCase>(`/edd/${id}/escalate`, { reason, escalateTo });
    return response.data;
  }

  /**
   * Get EDD case timeline
   */
  async getTimeline(id: string): Promise<EDDTimelineEvent[]> {
    const response = await this.http.get<{ timeline: EDDTimelineEvent[] }>(`/edd/${id}/timeline`);
    return response.data.timeline;
  }

  /**
   * Get EDD requirements for a trigger type
   */
  async getRequirements(trigger: EDDTrigger): Promise<{
    requiredDocuments: string[];
    requiredChecks: string[];
    estimatedDuration: string;
  }> {
    const response = await this.http.get(`/edd/requirements?trigger=${trigger}`);
    return response.data;
  }

  /**
   * Get EDD statistics
   */
  async getStatistics(): Promise<{
    totalCases: number;
    byStatus: Record<EDDStatus, number>;
    byTrigger: Record<EDDTrigger, number>;
    averageResolutionTime: number;
    approvalRate: number;
  }> {
    const response = await this.http.get('/edd/statistics');
    return response.data;
  }

  /**
   * Check if address requires EDD
   */
  async checkRequired(address: string): Promise<{
    required: boolean;
    reasons: EDDTrigger[];
    existingCase?: string;
  }> {
    const response = await this.http.get(`/edd/check/${address}`);
    return response.data;
  }
}
