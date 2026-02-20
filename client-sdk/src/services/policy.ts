/**
 * Policy Service
 * Wraps /policy endpoints for policy management and evaluation
 */

import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
import { BaseService } from './base';

// Local type definitions
export type PolicyDecision = 'allow' | 'deny' | 'review' | 'escalate';
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

export interface Policy {
  id: string;
  name: string;
  description: string;
  type: 'allow' | 'deny' | 'require_approval' | 'limit';
  conditions: PolicyCondition[];
  actions: PolicyAction[];
  priority: number;
  enabled: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface PolicyCondition {
  field: string;
  operator: 'eq' | 'ne' | 'gt' | 'gte' | 'lt' | 'lte' | 'in' | 'nin' | 'contains' | 'regex';
  value: any;
  logical?: 'and' | 'or';
}

export interface PolicyAction {
  type: 'allow' | 'deny' | 'require_approval' | 'notify' | 'delay' | 'limit';
  params?: Record<string, any>;
}

export interface PolicyEvaluationRequest {
  from: string;
  to: string;
  amount: string;
  tokenAddress?: string;
  chainId: number;
  transactionType?: string;
  metadata?: Record<string, any>;
}

export interface PolicyEvaluationResult {
  decision: PolicyDecision;
  appliedPolicies: {
    id: string;
    name: string;
    action: string;
    reason?: string;
  }[];
  riskLevel: RiskLevel;
  requiredApprovals?: number;
  approvers?: string[];
  delaySeconds?: number;
  limits?: {
    type: string;
    current: string;
    max: string;
    remaining: string;
  }[];
  warnings: string[];
}

export interface PolicyCreateRequest {
  name: string;
  description: string;
  type: 'allow' | 'deny' | 'require_approval' | 'limit';
  conditions: PolicyCondition[];
  actions: PolicyAction[];
  priority?: number;
  enabled?: boolean;
}

export class PolicyService extends BaseService {
  constructor(http: AxiosInstance, events: EventEmitter) {
    super(http, events);
  }

  /**
   * Evaluate policies for a transaction
   */
  async evaluate(request: PolicyEvaluationRequest): Promise<PolicyEvaluationResult> {
    const response = await this.http.post<PolicyEvaluationResult>('/policy/evaluate', request);
    
    this.events.emit('policy:evaluated', {
      from: request.from,
      to: request.to,
      decision: response.data.decision,
      appliedPolicies: response.data.appliedPolicies.length
    });

    return response.data;
  }

  /**
   * Get all policies
   */
  async list(options?: {
    type?: string;
    enabled?: boolean;
    limit?: number;
    offset?: number;
  }): Promise<{
    policies: Policy[];
    total: number;
  }> {
    const params = new URLSearchParams();
    if (options?.type) params.append('type', options.type);
    if (options?.enabled !== undefined) params.append('enabled', options.enabled.toString());
    if (options?.limit) params.append('limit', options.limit.toString());
    if (options?.offset) params.append('offset', options.offset.toString());

    const response = await this.http.get<{
      policies: Policy[];
      total: number;
    }>(`/policy?${params.toString()}`);

    return response.data;
  }

  /**
   * Get policy by ID
   */
  async get(id: string): Promise<Policy> {
    const response = await this.http.get<Policy>(`/policy/${id}`);
    return response.data;
  }

  /**
   * Create a new policy
   */
  async create(request: PolicyCreateRequest): Promise<Policy> {
    const response = await this.http.post<Policy>('/policy', request);
    
    this.events.emit('policy:created', {
      id: response.data.id,
      name: response.data.name,
      type: response.data.type
    });

    return response.data;
  }

  /**
   * Update an existing policy
   */
  async update(id: string, updates: Partial<PolicyCreateRequest>): Promise<Policy> {
    const response = await this.http.put<Policy>(`/policy/${id}`, updates);
    
    this.events.emit('policy:updated', { id });

    return response.data;
  }

  /**
   * Delete a policy
   */
  async delete(id: string): Promise<void> {
    await this.http.delete(`/policy/${id}`);
    
    this.events.emit('policy:deleted', { id });
  }

  /**
   * Enable a policy
   */
  async enable(id: string): Promise<Policy> {
    const response = await this.http.post<Policy>(`/policy/${id}/enable`);
    return response.data;
  }

  /**
   * Disable a policy
   */
  async disable(id: string): Promise<Policy> {
    const response = await this.http.post<Policy>(`/policy/${id}/disable`);
    return response.data;
  }

  /**
   * Test policy against sample data
   */
  async test(id: string, testData: PolicyEvaluationRequest): Promise<{
    wouldApply: boolean;
    result: PolicyEvaluationResult;
  }> {
    const response = await this.http.post(`/policy/${id}/test`, testData);
    return response.data;
  }

  /**
   * Get policy templates
   */
  async getTemplates(): Promise<{
    templates: {
      id: string;
      name: string;
      description: string;
      category: string;
      policy: PolicyCreateRequest;
    }[];
  }> {
    const response = await this.http.get('/policy/templates');
    return response.data;
  }

  /**
   * Create policy from template
   */
  async createFromTemplate(templateId: string, overrides?: Partial<PolicyCreateRequest>): Promise<Policy> {
    const response = await this.http.post<Policy>(`/policy/templates/${templateId}/create`, overrides);
    return response.data;
  }

  /**
   * Get policy audit log
   */
  async getAuditLog(id: string, options?: {
    limit?: number;
    offset?: number;
  }): Promise<{
    logs: {
      action: string;
      performedBy: string;
      timestamp: string;
      changes?: Record<string, any>;
    }[];
    total: number;
  }> {
    const params = new URLSearchParams();
    if (options?.limit) params.append('limit', options.limit.toString());
    if (options?.offset) params.append('offset', options.offset.toString());

    const response = await this.http.get(`/policy/${id}/audit?${params.toString()}`);
    return response.data;
  }

  /**
   * Validate policy configuration
   */
  async validate(policy: PolicyCreateRequest): Promise<{
    valid: boolean;
    errors: string[];
    warnings: string[];
  }> {
    const response = await this.http.post('/policy/validate', policy);
    return response.data;
  }
}
