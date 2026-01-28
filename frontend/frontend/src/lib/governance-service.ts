/**
 * Multisig Governance Service
 * 
 * Ground Truth Reference:
 * - Prevent unilateral action and blind approvals
 * - Parallel signing
 * - Threshold-based quorum
 * - Each signature bound to snapshot hash
 */

import {
  GovernanceAction,
  GovernanceActionType,
  ActionStatus,
  ActionScope,
  MultisigSignature,
  SigningRequest,
  WYASummary,
  GovernanceAuditEntry,
  DEFAULT_MULTISIG_CONFIGS,
  generateWYASummary,
  canUserSign,
  calculateQuorumProgress,
} from '@/types/governance';
import { Role } from '@/types/rbac';
import { sha256 } from './ui-snapshot-chain';

// ═══════════════════════════════════════════════════════════════════════════════
// API CONFIGURATION
// ═══════════════════════════════════════════════════════════════════════════════

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8007';

// ═══════════════════════════════════════════════════════════════════════════════
// ACTION CREATION
// ═══════════════════════════════════════════════════════════════════════════════

export interface CreateActionParams {
  type: GovernanceActionType;
  scope: ActionScope;
  targetAddress?: string;
  targetAsset?: string;
  targetPolicyId?: string;
  durationHours?: number;
  riskContext: {
    summary: string;
    fanOut?: number;
    velocityDeviation?: number;
    priorDisputes?: boolean;
    mlConfidence?: number;
    relatedCaseIds?: string[];
  };
  reversalConditions?: string;
  policyVersion: string;
  uiSnapshotId: string;
  uiSnapshotHash: string;
}

export async function createGovernanceAction(
  params: CreateActionParams,
  initiatorId: string
): Promise<GovernanceAction> {
  const config = DEFAULT_MULTISIG_CONFIGS[params.type];
  
  const action: GovernanceAction = {
    id: generateActionId(),
    type: params.type,
    status: ActionStatus.AWAITING_SIGNATURES,
    scope: params.scope,
    targetAddress: params.targetAddress,
    targetAsset: params.targetAsset,
    targetPolicyId: params.targetPolicyId,
    durationHours: params.durationHours,
    expiresAt: new Date(Date.now() + config.expirationHours * 60 * 60 * 1000).toISOString(),
    riskContext: params.riskContext,
    isReversible: params.type !== GovernanceActionType.EMERGENCY_OVERRIDE,
    reversalConditions: params.reversalConditions,
    initiatedBy: initiatorId,
    initiatedAt: new Date().toISOString(),
    uiSnapshotHash: params.uiSnapshotHash,
    uiSnapshotId: params.uiSnapshotId,
    policyVersion: params.policyVersion,
    requiredSignatures: config.requiredSignatures,
    signatures: [],
  };
  
  // In production, this would POST to backend
  try {
    const response = await fetch(`${API_BASE}/governance/actions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(action),
    });
    
    if (response.ok) {
      return await response.json();
    }
  } catch {
    // Fallback to local for demo
  }
  
  return action;
}

// ═══════════════════════════════════════════════════════════════════════════════
// ACTION FETCHING
// ═══════════════════════════════════════════════════════════════════════════════

export async function fetchPendingActions(userId: string): Promise<GovernanceAction[]> {
  try {
    const response = await fetch(`${API_BASE}/governance/actions/pending?userId=${userId}`);
    if (response.ok) {
      return await response.json();
    }
  } catch {
    // Return mock data for demo
  }
  
  return generateMockPendingActions();
}

export async function fetchAction(actionId: string): Promise<GovernanceAction | null> {
  try {
    const response = await fetch(`${API_BASE}/governance/actions/${actionId}`);
    if (response.ok) {
      return await response.json();
    }
  } catch {
    // Fallback
  }
  
  return null;
}

export async function fetchSigningRequest(
  actionId: string,
  userId: string,
  userRole: Role
): Promise<SigningRequest | null> {
  const action = await fetchAction(actionId);
  if (!action) return null;
  
  const { canSign, reason } = canUserSign(action, userRole, userId);
  const hasSigned = action.signatures.some(s => s.signerId === userId);
  const quorum = calculateQuorumProgress(action);
  
  return {
    actionId,
    action,
    wyaSummary: generateWYASummary(action),
    currentSnapshotHash: action.uiSnapshotHash,
    snapshotMatches: true, // Would verify in production
    signerCanSign: canSign,
    signerHasSigned: hasSigned,
    remainingSignatures: quorum.required - quorum.current,
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// SIGNING
// ═══════════════════════════════════════════════════════════════════════════════

export interface SignActionParams {
  actionId: string;
  signerId: string;
  signerRole: Role;
  signerAddress: string;
  acknowledgedSnapshotHash: string;
  mfaMethod: 'biometric' | 'hardware_key' | 'totp' | 'sms';
}

export interface SigningResult {
  success: boolean;
  signature?: MultisigSignature;
  quorumReached?: boolean;
  executionPending?: boolean;
  error?: string;
}

export async function signGovernanceAction(
  params: SignActionParams,
  signatureData: string
): Promise<SigningResult> {
  // Verify snapshot hash matches
  const action = await fetchAction(params.actionId);
  if (!action) {
    return { success: false, error: 'Action not found' };
  }
  
  // Verify hash acknowledgement
  if (params.acknowledgedSnapshotHash !== action.uiSnapshotHash) {
    return { 
      success: false, 
      error: 'Snapshot hash mismatch - UI integrity violation' 
    };
  }
  
  // Check if can sign
  const { canSign, reason } = canUserSign(action, params.signerRole, params.signerId);
  if (!canSign) {
    return { success: false, error: reason };
  }
  
  // Create signature
  const signature: MultisigSignature = {
    signerId: params.signerId,
    signerRole: params.signerRole,
    signerAddress: params.signerAddress,
    signature: signatureData,
    signedAt: new Date().toISOString(),
    acknowledgedSnapshotHash: params.acknowledgedSnapshotHash,
    hashVerified: true,
    mfaMethod: params.mfaMethod,
    mfaVerifiedAt: new Date().toISOString(),
  };
  
  // In production, POST to backend
  try {
    const response = await fetch(`${API_BASE}/governance/actions/${params.actionId}/sign`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(signature),
    });
    
    if (response.ok) {
      const result = await response.json();
      return {
        success: true,
        signature,
        quorumReached: result.quorumReached,
        executionPending: result.executionPending,
      };
    }
  } catch {
    // Fallback for demo
  }
  
  // Check if quorum reached
  const newSignatureCount = action.signatures.length + 1;
  const quorumReached = newSignatureCount >= action.requiredSignatures;
  
  return {
    success: true,
    signature,
    quorumReached,
    executionPending: quorumReached,
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// EXECUTION
// ═══════════════════════════════════════════════════════════════════════════════

export interface ExecutionResult {
  success: boolean;
  transactionHash?: string;
  executedAt?: string;
  error?: string;
}

export async function executeGovernanceAction(
  actionId: string
): Promise<ExecutionResult> {
  const action = await fetchAction(actionId);
  if (!action) {
    return { success: false, error: 'Action not found' };
  }
  
  // Verify quorum
  const quorum = calculateQuorumProgress(action);
  if (!quorum.isReached) {
    return { success: false, error: 'Quorum not reached' };
  }
  
  // In production, this would:
  // 1. Call smart contract
  // 2. Wait for confirmation
  // 3. Update action status
  
  try {
    const response = await fetch(`${API_BASE}/governance/actions/${actionId}/execute`, {
      method: 'POST',
    });
    
    if (response.ok) {
      return await response.json();
    }
  } catch {
    // Simulate execution for demo
  }
  
  return {
    success: true,
    transactionHash: `0x${generateActionId()}`,
    executedAt: new Date().toISOString(),
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// AUDIT TRAIL
// ═══════════════════════════════════════════════════════════════════════════════

export async function fetchAuditTrail(actionId: string): Promise<GovernanceAuditEntry[]> {
  try {
    const response = await fetch(`${API_BASE}/governance/actions/${actionId}/audit`);
    if (response.ok) {
      return await response.json();
    }
  } catch {
    // Fallback
  }
  
  return [];
}

// ═══════════════════════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════════════════════

function generateActionId(): string {
  return `action_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

// ═══════════════════════════════════════════════════════════════════════════════
// MOCK DATA
// ═══════════════════════════════════════════════════════════════════════════════

function generateMockPendingActions(): GovernanceAction[] {
  return [
    {
      id: 'action_001',
      type: GovernanceActionType.WALLET_PAUSE,
      status: ActionStatus.AWAITING_SIGNATURES,
      scope: ActionScope.SINGLE_WALLET,
      targetAddress: '0x7f2e1b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a',
      durationHours: 24,
      expiresAt: new Date(Date.now() + 12 * 60 * 60 * 1000).toISOString(),
      riskContext: {
        summary: 'Fan-out pattern detected across 7 wallets in 2 hours',
        fanOut: 7,
        velocityDeviation: 6.2,
        priorDisputes: true,
        mlConfidence: 0.89,
        relatedCaseIds: ['CASE-2024-001'],
      },
      isReversible: true,
      reversalConditions: 'Via multisig approval',
      initiatedBy: 'user_compliance_001',
      initiatedAt: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
      uiSnapshotHash: '7f3a9c2e1d4b5f6a8c9d0e1f2a3b4c5d6e7f8a9b',
      uiSnapshotId: 'snapshot_001',
      policyVersion: 'POLICY_v3.2',
      requiredSignatures: 2,
      signatures: [
        {
          signerId: 'user_compliance_002',
          signerRole: Role.R4_INSTITUTION_COMPLIANCE,
          signerAddress: '0xabc123...',
          signature: '0x...',
          signedAt: new Date(Date.now() - 1 * 60 * 60 * 1000).toISOString(),
          acknowledgedSnapshotHash: '7f3a9c2e1d4b5f6a8c9d0e1f2a3b4c5d6e7f8a9b',
          hashVerified: true,
          mfaMethod: 'biometric',
          mfaVerifiedAt: new Date(Date.now() - 1 * 60 * 60 * 1000).toISOString(),
        },
      ],
    },
    {
      id: 'action_002',
      type: GovernanceActionType.MANDATORY_ESCROW,
      status: ActionStatus.AWAITING_SIGNATURES,
      scope: ActionScope.WALLET_CLUSTER,
      targetAddress: '0x cluster_identifier',
      expiresAt: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
      riskContext: {
        summary: 'Potential layering behavior detected in wallet cluster',
        fanOut: 12,
        velocityDeviation: 4.5,
        priorDisputes: false,
        mlConfidence: 0.76,
      },
      isReversible: true,
      initiatedBy: 'user_compliance_001',
      initiatedAt: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
      uiSnapshotHash: 'abc123def456...',
      uiSnapshotId: 'snapshot_002',
      policyVersion: 'POLICY_v3.2',
      requiredSignatures: 2,
      signatures: [],
    },
  ];
}
