/**
 * Multisig Governance Types
 * 
 * Ground Truth Reference:
 * - Multisig is not a feature, it's a ceremony
 * - Prevent blind signing
 * - Prove informed consent
 * - Each signature bound to snapshot hash
 */

import { Role, TrustPillar } from './rbac';

// ═══════════════════════════════════════════════════════════════════════════════
// GOVERNANCE ACTIONS
// ═══════════════════════════════════════════════════════════════════════════════

export enum GovernanceActionType {
  WALLET_PAUSE = 'WALLET_PAUSE',
  WALLET_UNPAUSE = 'WALLET_UNPAUSE',
  ASSET_BLOCK = 'ASSET_BLOCK',
  ASSET_UNBLOCK = 'ASSET_UNBLOCK',
  MANDATORY_ESCROW = 'MANDATORY_ESCROW',
  POLICY_UPDATE = 'POLICY_UPDATE',
  THRESHOLD_CHANGE = 'THRESHOLD_CHANGE',
  EMERGENCY_OVERRIDE = 'EMERGENCY_OVERRIDE',
}

export enum ActionScope {
  SINGLE_WALLET = 'SINGLE_WALLET',
  WALLET_CLUSTER = 'WALLET_CLUSTER',
  ASSET_TYPE = 'ASSET_TYPE',
  ORGANIZATION = 'ORGANIZATION',
  GLOBAL = 'GLOBAL',
}

export enum ActionStatus {
  PENDING = 'PENDING',
  AWAITING_SIGNATURES = 'AWAITING_SIGNATURES',
  QUORUM_REACHED = 'QUORUM_REACHED',
  EXECUTED = 'EXECUTED',
  EXPIRED = 'EXPIRED',
  REJECTED = 'REJECTED',
  CANCELLED = 'CANCELLED',
}

// ═══════════════════════════════════════════════════════════════════════════════
// MULTISIG CONFIGURATION
// ═══════════════════════════════════════════════════════════════════════════════

export interface MultisigConfig {
  requiredSignatures: number;
  totalSigners: number;
  expirationHours: number;
  allowedRoles: Role[];
}

// Default configs per action type
export const DEFAULT_MULTISIG_CONFIGS: Record<GovernanceActionType, MultisigConfig> = {
  [GovernanceActionType.WALLET_PAUSE]: {
    requiredSignatures: 2,
    totalSigners: 5,
    expirationHours: 24,
    allowedRoles: [Role.R4_INSTITUTION_COMPLIANCE],
  },
  [GovernanceActionType.WALLET_UNPAUSE]: {
    requiredSignatures: 2,
    totalSigners: 5,
    expirationHours: 24,
    allowedRoles: [Role.R4_INSTITUTION_COMPLIANCE],
  },
  [GovernanceActionType.ASSET_BLOCK]: {
    requiredSignatures: 3,
    totalSigners: 5,
    expirationHours: 12,
    allowedRoles: [Role.R4_INSTITUTION_COMPLIANCE],
  },
  [GovernanceActionType.ASSET_UNBLOCK]: {
    requiredSignatures: 2,
    totalSigners: 5,
    expirationHours: 24,
    allowedRoles: [Role.R4_INSTITUTION_COMPLIANCE],
  },
  [GovernanceActionType.MANDATORY_ESCROW]: {
    requiredSignatures: 2,
    totalSigners: 5,
    expirationHours: 48,
    allowedRoles: [Role.R4_INSTITUTION_COMPLIANCE],
  },
  [GovernanceActionType.POLICY_UPDATE]: {
    requiredSignatures: 3,
    totalSigners: 5,
    expirationHours: 72,
    allowedRoles: [Role.R4_INSTITUTION_COMPLIANCE],
  },
  [GovernanceActionType.THRESHOLD_CHANGE]: {
    requiredSignatures: 4,
    totalSigners: 5,
    expirationHours: 72,
    allowedRoles: [Role.R4_INSTITUTION_COMPLIANCE],
  },
  [GovernanceActionType.EMERGENCY_OVERRIDE]: {
    requiredSignatures: 4,
    totalSigners: 5,
    expirationHours: 1,
    allowedRoles: [Role.R6_SUPER_ADMIN],
  },
};

// ═══════════════════════════════════════════════════════════════════════════════
// GOVERNANCE ACTION
// ═══════════════════════════════════════════════════════════════════════════════

export interface GovernanceAction {
  id: string;
  type: GovernanceActionType;
  status: ActionStatus;
  
  // Target
  scope: ActionScope;
  targetAddress?: string;
  targetAsset?: string;
  targetPolicyId?: string;
  
  // Duration
  durationHours?: number;
  expiresAt: string;
  
  // Risk Context (from investigation)
  riskContext: {
    summary: string;
    fanOut?: number;
    velocityDeviation?: number;
    priorDisputes?: boolean;
    mlConfidence?: number;
    relatedCaseIds?: string[];
  };
  
  // Reversibility
  isReversible: boolean;
  reversalConditions?: string;
  
  // Initiator
  initiatedBy: string;
  initiatedAt: string;
  
  // UI Integrity
  uiSnapshotHash: string;
  uiSnapshotId: string;
  
  // Policy reference
  policyVersion: string;
  
  // Signatures
  requiredSignatures: number;
  signatures: MultisigSignature[];
  
  // Execution
  executedAt?: string;
  executionTxHash?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SIGNATURES
// ═══════════════════════════════════════════════════════════════════════════════

export interface MultisigSignature {
  signerId: string;
  signerRole: Role;
  signerAddress: string;
  
  // Signature data
  signature: string;
  signedAt: string;
  
  // What was acknowledged
  acknowledgedSnapshotHash: string;
  hashVerified: boolean;
  
  // MFA verification
  mfaMethod: 'biometric' | 'hardware_key' | 'totp' | 'sms';
  mfaVerifiedAt: string;
}

export interface SigningRequest {
  actionId: string;
  action: GovernanceAction;
  
  // What-You-Approve summary
  wyaSummary: WYASummary;
  
  // Integrity verification
  currentSnapshotHash: string;
  snapshotMatches: boolean;
  
  // Signer context
  signerCanSign: boolean;
  signerHasSigned: boolean;
  remainingSignatures: number;
}

// ═══════════════════════════════════════════════════════════════════════════════
// WHAT-YOU-APPROVE (WYA)
// ═══════════════════════════════════════════════════════════════════════════════

export interface WYASummary {
  // Plain English action description
  actionDescription: string;
  
  // Target details
  targetType: string;
  targetIdentifier: string;
  
  // Scope
  scopeDescription: string;
  affectedEntities: number;
  
  // Duration
  durationDescription: string;
  
  // Risk summary
  riskFactors: string[];
  
  // Reversibility
  reversibilityDescription: string;
  
  // Contract details
  contractAddress: string;
  contractFunction: string;
  
  // On-chain impact
  onChainImpact: string[];
}

// ═══════════════════════════════════════════════════════════════════════════════
// AUDIT TRAIL
// ═══════════════════════════════════════════════════════════════════════════════

export interface GovernanceAuditEntry {
  id: string;
  actionId: string;
  timestamp: string;
  
  eventType: 
    | 'ACTION_CREATED'
    | 'SIGNATURE_ADDED'
    | 'QUORUM_REACHED'
    | 'ACTION_EXECUTED'
    | 'ACTION_EXPIRED'
    | 'ACTION_REJECTED'
    | 'INTEGRITY_VIOLATION';
  
  actorId: string;
  actorRole: Role;
  
  snapshotHash: string;
  previousHash: string;
  
  details: Record<string, any>;
}

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

export function getActionTypeLabel(type: GovernanceActionType): string {
  const labels: Record<GovernanceActionType, string> = {
    [GovernanceActionType.WALLET_PAUSE]: 'Wallet Pause',
    [GovernanceActionType.WALLET_UNPAUSE]: 'Wallet Unpause',
    [GovernanceActionType.ASSET_BLOCK]: 'Asset Block',
    [GovernanceActionType.ASSET_UNBLOCK]: 'Asset Unblock',
    [GovernanceActionType.MANDATORY_ESCROW]: 'Mandatory Escrow',
    [GovernanceActionType.POLICY_UPDATE]: 'Policy Update',
    [GovernanceActionType.THRESHOLD_CHANGE]: 'Threshold Change',
    [GovernanceActionType.EMERGENCY_OVERRIDE]: 'Emergency Override',
  };
  return labels[type];
}

export function getStatusColor(status: ActionStatus): string {
  const colors: Record<ActionStatus, string> = {
    [ActionStatus.PENDING]: '#f59e0b',
    [ActionStatus.AWAITING_SIGNATURES]: '#3b82f6',
    [ActionStatus.QUORUM_REACHED]: '#10b981',
    [ActionStatus.EXECUTED]: '#22c55e',
    [ActionStatus.EXPIRED]: '#6b7280',
    [ActionStatus.REJECTED]: '#ef4444',
    [ActionStatus.CANCELLED]: '#9ca3af',
  };
  return colors[status];
}

export function canUserSign(
  action: GovernanceAction,
  Role: Role,
  userId: string
): { canSign: boolean; reason?: string } {
  const config = DEFAULT_MULTISIG_CONFIGS[action.type];
  
  // Check role
  if (!config.allowedRoles.includes(Role)) {
    return { canSign: false, reason: 'Role not authorized for this action type' };
  }
  
  // Check if already signed
  if (action.signatures.some(s => s.signerId === userId)) {
    return { canSign: false, reason: 'Already signed' };
  }
  
  // Check status
  if (action.status !== ActionStatus.AWAITING_SIGNATURES) {
    return { canSign: false, reason: `Action is ${action.status.toLowerCase()}` };
  }
  
  // Check expiration
  if (new Date(action.expiresAt) < new Date()) {
    return { canSign: false, reason: 'Action has expired' };
  }
  
  return { canSign: true };
}

export function calculateQuorumProgress(action: GovernanceAction): {
  current: number;
  required: number;
  percentage: number;
  isReached: boolean;
} {
  const current = action.signatures.length;
  const required = action.requiredSignatures;
  
  return {
    current,
    required,
    percentage: Math.min(100, (current / required) * 100),
    isReached: current >= required,
  };
}

export function generateWYASummary(action: GovernanceAction): WYASummary {
  const typeLabel = getActionTypeLabel(action.type);
  
  return {
    actionDescription: `${typeLabel} on ${action.scope.replace('_', ' ').toLowerCase()}`,
    targetType: action.scope.replace('_', ' '),
    targetIdentifier: action.targetAddress || action.targetAsset || action.targetPolicyId || 'N/A',
    scopeDescription: action.scope === ActionScope.SINGLE_WALLET 
      ? 'Single wallet affected' 
      : `Multiple entities affected (${action.scope})`,
    affectedEntities: action.scope === ActionScope.SINGLE_WALLET ? 1 : 0, // Would be calculated
    durationDescription: action.durationHours 
      ? `${action.durationHours} hours` 
      : 'Indefinite (manual reversal required)',
    riskFactors: [
      action.riskContext.summary,
      action.riskContext.fanOut ? `Fan-out: ${action.riskContext.fanOut} wallets` : '',
      action.riskContext.velocityDeviation ? `Velocity: ${action.riskContext.velocityDeviation}σ above baseline` : '',
      action.riskContext.priorDisputes ? 'Prior dispute history' : '',
    ].filter(Boolean),
    reversibilityDescription: action.isReversible 
      ? `Reversible: ${action.reversalConditions || 'Via multisig approval'}` 
      : 'IRREVERSIBLE - Requires new action to undo',
    contractAddress: '0x...', // Would come from config
    contractFunction: `${action.type.toLowerCase()}()`,
    onChainImpact: [
      `Smart contract function will be called`,
      action.durationHours ? `Time-locked for ${action.durationHours}h` : '',
      `Transaction hash will be recorded`,
    ].filter(Boolean),
  };
}
