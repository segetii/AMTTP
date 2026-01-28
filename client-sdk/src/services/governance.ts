/**
 * Governance Service - Multisig and Action Management
 * 
 * Provides governance controls for multi-signature approvals,
 * policy changes, and enforcement actions.
 */

import { AxiosInstance } from 'axios';
import { BaseService } from './base';
import { EventEmitter } from '../events';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export type ActionType = 
  | 'WALLET_PAUSE'
  | 'WALLET_UNPAUSE'
  | 'MANDATORY_ESCROW'
  | 'RELEASE_ESCROW'
  | 'POLICY_UPDATE'
  | 'WHITELIST_ADD'
  | 'WHITELIST_REMOVE'
  | 'BLACKLIST_ADD'
  | 'BLACKLIST_REMOVE'
  | 'EMERGENCY_STOP';

export type ActionStatus = 
  | 'PENDING'
  | 'AWAITING_SIGNATURES'
  | 'QUORUM_REACHED'
  | 'EXECUTED'
  | 'EXPIRED'
  | 'CANCELLED';

export type ActionScope = 
  | 'SINGLE_WALLET'
  | 'WALLET_CLUSTER'
  | 'GLOBAL';

export interface RiskContext {
  summary: string;
  fanOut?: number;
  velocityDeviation?: number;
  priorDisputes?: boolean;
  mlConfidence?: number;
  relatedCaseIds?: string[];
}

export interface Signature {
  signerId: string;
  signerRole: string;
  signerAddress: string;
  signature: string;
  signedAt: string;
  acknowledgedSnapshotHash: string;
  hashVerified: boolean;
  mfaMethod?: string;
  mfaVerifiedAt?: string;
}

export interface GovernanceAction {
  id: string;
  type: ActionType;
  status: ActionStatus;
  scope: ActionScope;
  targetAddress?: string;
  durationHours?: number;
  expiresAt: string;
  riskContext: RiskContext;
  isReversible: boolean;
  reversalConditions?: string;
  initiatedBy: string;
  initiatedAt: string;
  uiSnapshotHash: string;
  uiSnapshotId: string;
  policyVersion: string;
  requiredSignatures: number;
  signatures: Signature[];
}

export interface CreateActionRequest {
  type: ActionType;
  scope: ActionScope;
  targetAddress?: string;
  durationHours?: number;
  riskContext: RiskContext;
  uiSnapshotHash: string;
  policyVersion: string;
}

export interface SignActionRequest {
  actionId: string;
  signature: string;
  acknowledgedSnapshotHash: string;
  mfaToken?: string;
}

export interface SigningResult {
  success: boolean;
  actionId: string;
  signatureId?: string;
  currentSignatures: number;
  requiredSignatures: number;
  quorumReached: boolean;
  error?: string;
}

export interface ExecutionResult {
  success: boolean;
  actionId: string;
  transactionHash?: string;
  executedAt?: string;
  error?: string;
}

export interface WYASummary {
  actionType: string;
  scope: string;
  target: string;
  riskSummary: string;
  reversible: boolean;
  signatures: { current: number; required: number };
}

export interface ActionListOptions {
  status?: ActionStatus;
  type?: ActionType;
  limit?: number;
  offset?: number;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SERVICE
// ═══════════════════════════════════════════════════════════════════════════════

export class GovernanceService extends BaseService {
  constructor(http: AxiosInstance, events: EventEmitter) {
    super(http, events);
  }

  /**
   * Create a new governance action
   */
  async createAction(request: CreateActionRequest): Promise<GovernanceAction> {
    const response = await this.http.post<GovernanceAction>('/governance/actions', request);
    this.events.emit('governance:action_created', response.data);
    return response.data;
  }

  /**
   * Get a governance action by ID
   */
  async getAction(actionId: string): Promise<GovernanceAction | null> {
    try {
      const response = await this.http.get<GovernanceAction>(`/governance/actions/${actionId}`);
      return response.data;
    } catch {
      return null;
    }
  }

  /**
   * List governance actions
   */
  async listActions(options?: ActionListOptions): Promise<GovernanceAction[]> {
    const response = await this.http.get<{ actions: GovernanceAction[] }>(
      '/governance/actions',
      { params: options }
    );
    return response.data.actions;
  }

  /**
   * Get pending actions for a user
   */
  async getPendingActions(userId: string): Promise<GovernanceAction[]> {
    const response = await this.http.get<GovernanceAction[]>(
      `/governance/actions/pending`,
      { params: { userId } }
    );
    return response.data;
  }

  /**
   * Sign a governance action
   */
  async signAction(request: SignActionRequest): Promise<SigningResult> {
    const response = await this.http.post<SigningResult>(
      `/governance/actions/${request.actionId}/sign`,
      request
    );
    
    this.events.emit('governance:signature_added', response.data);
    
    if (response.data.quorumReached) {
      this.events.emit('governance:quorum_reached', response.data);
    }
    
    return response.data;
  }

  /**
   * Execute a governance action (after quorum reached)
   */
  async executeAction(actionId: string): Promise<ExecutionResult> {
    const response = await this.http.post<ExecutionResult>(
      `/governance/actions/${actionId}/execute`
    );
    return response.data;
  }

  /**
   * Cancel a governance action
   */
  async cancelAction(actionId: string, reason: string): Promise<{ success: boolean }> {
    const response = await this.http.post(`/governance/actions/${actionId}/cancel`, { reason });
    return response.data;
  }

  /**
   * Get What-You-Approve summary for an action
   */
  async getWYASummary(actionId: string): Promise<WYASummary> {
    const response = await this.http.get<WYASummary>(`/governance/actions/${actionId}/wya`);
    return response.data;
  }

  /**
   * Get audit trail for an action
   */
  async getAuditTrail(actionId: string): Promise<Array<{
    event: string;
    timestamp: string;
    userId: string;
    details: Record<string, unknown>;
  }>> {
    const response = await this.http.get(`/governance/actions/${actionId}/audit`);
    return response.data.events;
  }

  /**
   * Check if user can sign an action
   */
  async canUserSign(actionId: string, userId: string): Promise<{
    canSign: boolean;
    reason?: string;
  }> {
    const response = await this.http.get(`/governance/actions/${actionId}/can-sign`, {
      params: { userId },
    });
    return response.data;
  }

  /**
   * Calculate quorum progress
   */
  static calculateQuorumProgress(action: GovernanceAction): {
    current: number;
    required: number;
    percentage: number;
  } {
    const current = action.signatures.length;
    const required = action.requiredSignatures;
    return {
      current,
      required,
      percentage: Math.min(100, (current / required) * 100),
    };
  }

  /**
   * Get action type label
   */
  static getActionTypeLabel(type: ActionType): string {
    const labels: Record<ActionType, string> = {
      WALLET_PAUSE: 'Pause Wallet',
      WALLET_UNPAUSE: 'Unpause Wallet',
      MANDATORY_ESCROW: 'Mandatory Escrow',
      RELEASE_ESCROW: 'Release Escrow',
      POLICY_UPDATE: 'Update Policy',
      WHITELIST_ADD: 'Add to Whitelist',
      WHITELIST_REMOVE: 'Remove from Whitelist',
      BLACKLIST_ADD: 'Add to Blacklist',
      BLACKLIST_REMOVE: 'Remove from Blacklist',
      EMERGENCY_STOP: 'Emergency Stop',
    };
    return labels[type] || type;
  }
}
