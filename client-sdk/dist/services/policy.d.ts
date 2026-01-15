/**
 * Policy Service
 * Wraps /policy endpoints for policy management and evaluation
 */
import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
import { BaseService } from './base';
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
export declare class PolicyService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Evaluate policies for a transaction
     */
    evaluate(request: PolicyEvaluationRequest): Promise<PolicyEvaluationResult>;
    /**
     * Get all policies
     */
    list(options?: {
        type?: string;
        enabled?: boolean;
        limit?: number;
        offset?: number;
    }): Promise<{
        policies: Policy[];
        total: number;
    }>;
    /**
     * Get policy by ID
     */
    get(id: string): Promise<Policy>;
    /**
     * Create a new policy
     */
    create(request: PolicyCreateRequest): Promise<Policy>;
    /**
     * Update an existing policy
     */
    update(id: string, updates: Partial<PolicyCreateRequest>): Promise<Policy>;
    /**
     * Delete a policy
     */
    delete(id: string): Promise<void>;
    /**
     * Enable a policy
     */
    enable(id: string): Promise<Policy>;
    /**
     * Disable a policy
     */
    disable(id: string): Promise<Policy>;
    /**
     * Test policy against sample data
     */
    test(id: string, testData: PolicyEvaluationRequest): Promise<{
        wouldApply: boolean;
        result: PolicyEvaluationResult;
    }>;
    /**
     * Get policy templates
     */
    getTemplates(): Promise<{
        templates: {
            id: string;
            name: string;
            description: string;
            category: string;
            policy: PolicyCreateRequest;
        }[];
    }>;
    /**
     * Create policy from template
     */
    createFromTemplate(templateId: string, overrides?: Partial<PolicyCreateRequest>): Promise<Policy>;
    /**
     * Get policy audit log
     */
    getAuditLog(id: string, options?: {
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
    }>;
    /**
     * Validate policy configuration
     */
    validate(policy: PolicyCreateRequest): Promise<{
        valid: boolean;
        errors: string[];
        warnings: string[];
    }>;
}
//# sourceMappingURL=policy.d.ts.map