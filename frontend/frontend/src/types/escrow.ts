/**
 * Escrow Types
 * 
 * Ground Truth Reference:
 * - Escrow is risk mitigation, not a payment rail
 * - Triggered by policy, not user preference
 * - Clear lifecycle: Created → Funded → Released/Disputed → Resolved
 * - Focus Mode users see simplified status, War Room sees full details
 */

import { Role } from './rbac';

// ═══════════════════════════════════════════════════════════════════════════════
// ESCROW STATUS
// ═══════════════════════════════════════════════════════════════════════════════

export enum EscrowStatus {
  PENDING_FUNDING = 'PENDING_FUNDING',
  FUNDED = 'FUNDED',
  RELEASE_REQUESTED = 'RELEASE_REQUESTED',
  RELEASING = 'RELEASING',
  RELEASED = 'RELEASED',
  DISPUTE_RAISED = 'DISPUTE_RAISED',
  IN_ARBITRATION = 'IN_ARBITRATION',
  RESOLVED_TO_SENDER = 'RESOLVED_TO_SENDER',
  RESOLVED_TO_RECIPIENT = 'RESOLVED_TO_RECIPIENT',
  RESOLVED_SPLIT = 'RESOLVED_SPLIT',
  EXPIRED = 'EXPIRED',
  CANCELLED = 'CANCELLED',
}

export enum EscrowTrigger {
  HIGH_RISK_SCORE = 'HIGH_RISK_SCORE',
  NEW_COUNTERPARTY = 'NEW_COUNTERPARTY',
  VELOCITY_ANOMALY = 'VELOCITY_ANOMALY',
  POLICY_MANDATE = 'POLICY_MANDATE',
  USER_REQUESTED = 'USER_REQUESTED',
  CROSS_BORDER = 'CROSS_BORDER',
  LARGE_VALUE = 'LARGE_VALUE',
}

export enum EscrowType {
  TIME_LOCKED = 'TIME_LOCKED',
  CONDITION_BASED = 'CONDITION_BASED',
  MULTI_RELEASE = 'MULTI_RELEASE',
  MILESTONE_BASED = 'MILESTONE_BASED',
}

// ═══════════════════════════════════════════════════════════════════════════════
// ESCROW CONTRACT
// ═══════════════════════════════════════════════════════════════════════════════

export interface EscrowContract {
  id: string;
  type: EscrowType;
  status: EscrowStatus;
  
  // Parties
  sender: {
    address: string;
    name?: string;
    verified: boolean;
  };
  recipient: {
    address: string;
    name?: string;
    verified: boolean;
  };
  
  // Funds
  token: string;
  amount: string;
  amountUSD: number;
  chainId: number;
  
  // Trigger
  trigger: EscrowTrigger;
  triggerReason: string;
  riskScoreAtCreation: number;
  
  // Timeline
  createdAt: string;
  fundedAt?: string;
  releaseRequestedAt?: string;
  releasedAt?: string;
  expiresAt: string;
  
  // Lock conditions
  lockDurationHours: number;
  releaseConditions: ReleaseCondition[];
  
  // Dispute info
  disputeId?: string;
  disputeRaisedAt?: string;
  
  // On-chain
  contractAddress: string;
  txHash: string;
  
  // UI integrity
  uiSnapshotHash: string;
}

export interface ReleaseCondition {
  id: string;
  type: 'time_elapsed' | 'signature_required' | 'milestone_confirmed' | 'dispute_window_passed';
  description: string;
  met: boolean;
  metAt?: string;
  requiredBy?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// ESCROW ACTIONS
// ═══════════════════════════════════════════════════════════════════════════════

export interface EscrowAction {
  type: 'fund' | 'request_release' | 'approve_release' | 'raise_dispute' | 'cancel';
  escrowId: string;
  timestamp: string;
  actor: string;
  actorRole: Role;
  signature?: string;
  reason?: string;
}

export interface FundEscrowParams {
  escrowId: string;
  amount: string;
  token: string;
}

export interface ReleaseEscrowParams {
  escrowId: string;
  reason?: string;
  partialAmount?: string; // For partial releases
}

export interface DisputeEscrowParams {
  escrowId: string;
  reason: string;
  evidenceHashes: string[];
  requestedOutcome: 'full_refund' | 'partial_refund' | 'release_to_recipient';
}

// ═══════════════════════════════════════════════════════════════════════════════
// ESCROW POLICY
// ═══════════════════════════════════════════════════════════════════════════════

export interface EscrowPolicy {
  id: string;
  name: string;
  active: boolean;
  
  // Trigger conditions
  triggers: {
    riskScoreThreshold?: number;
    velocityDeviationThreshold?: number;
    newCounterpartyDays?: number;
    minAmountUSD?: number;
    crossBorderRequired?: boolean;
  };
  
  // Lock parameters
  defaultLockHours: number;
  maxLockHours: number;
  
  // Release conditions
  requiresMultisig: boolean;
  requiredSignatures?: number;
  
  // Fees
  escrowFeePercent: number;
  disputeFeePercent: number;
}

// ═══════════════════════════════════════════════════════════════════════════════
// ESCROW SUMMARY (Focus Mode View)
// ═══════════════════════════════════════════════════════════════════════════════

export interface EscrowSummary {
  id: string;
  status: EscrowStatus;
  statusLabel: string;
  statusColor: 'green' | 'yellow' | 'orange' | 'red' | 'blue' | 'gray';
  
  // Simplified display
  counterparty: string;
  amount: string;
  token: string;
  
  // Timeline
  createdDate: string;
  releaseDate?: string;
  timeRemaining?: string;
  
  // Actions available
  canRequestRelease: boolean;
  canRaiseDispute: boolean;
  canCancel: boolean;
  
  // Risk indicator
  riskLevel: 'low' | 'medium' | 'high';
}

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

export function getStatusLabel(status: EscrowStatus): string {
  const labels: Record<EscrowStatus, string> = {
    [EscrowStatus.PENDING_FUNDING]: 'Awaiting Funding',
    [EscrowStatus.FUNDED]: 'Funds Secured',
    [EscrowStatus.RELEASE_REQUESTED]: 'Release Pending',
    [EscrowStatus.RELEASING]: 'Processing Release',
    [EscrowStatus.RELEASED]: 'Released',
    [EscrowStatus.DISPUTE_RAISED]: 'Dispute Filed',
    [EscrowStatus.IN_ARBITRATION]: 'Under Review',
    [EscrowStatus.RESOLVED_TO_SENDER]: 'Returned to Sender',
    [EscrowStatus.RESOLVED_TO_RECIPIENT]: 'Sent to Recipient',
    [EscrowStatus.RESOLVED_SPLIT]: 'Split Resolution',
    [EscrowStatus.EXPIRED]: 'Expired',
    [EscrowStatus.CANCELLED]: 'Cancelled',
  };
  return labels[status];
}

export function getStatusColor(status: EscrowStatus): 'green' | 'yellow' | 'orange' | 'red' | 'blue' | 'gray' {
  switch (status) {
    case EscrowStatus.RELEASED:
    case EscrowStatus.RESOLVED_TO_RECIPIENT:
      return 'green';
    case EscrowStatus.FUNDED:
    case EscrowStatus.RELEASE_REQUESTED:
      return 'blue';
    case EscrowStatus.RELEASING:
    case EscrowStatus.PENDING_FUNDING:
      return 'yellow';
    case EscrowStatus.DISPUTE_RAISED:
    case EscrowStatus.IN_ARBITRATION:
      return 'orange';
    case EscrowStatus.RESOLVED_TO_SENDER:
    case EscrowStatus.RESOLVED_SPLIT:
      return 'red';
    case EscrowStatus.EXPIRED:
    case EscrowStatus.CANCELLED:
      return 'gray';
    default:
      return 'gray';
  }
}

export function getTriggerLabel(trigger: EscrowTrigger): string {
  const labels: Record<EscrowTrigger, string> = {
    [EscrowTrigger.HIGH_RISK_SCORE]: 'High Risk Score Detected',
    [EscrowTrigger.NEW_COUNTERPARTY]: 'New Counterparty',
    [EscrowTrigger.VELOCITY_ANOMALY]: 'Unusual Transfer Pattern',
    [EscrowTrigger.POLICY_MANDATE]: 'Policy Requirement',
    [EscrowTrigger.USER_REQUESTED]: 'Buyer Protection',
    [EscrowTrigger.CROSS_BORDER]: 'Cross-Border Transfer',
    [EscrowTrigger.LARGE_VALUE]: 'Large Value Transfer',
  };
  return labels[trigger];
}

export function canPerformAction(
  escrow: EscrowContract,
  action: EscrowAction['type'],
  userAddress: string
): boolean {
  const isSender = escrow.sender.address.toLowerCase() === userAddress.toLowerCase();
  const isRecipient = escrow.recipient.address.toLowerCase() === userAddress.toLowerCase();
  
  switch (action) {
    case 'fund':
      return isSender && escrow.status === EscrowStatus.PENDING_FUNDING;
    case 'request_release':
      return isRecipient && escrow.status === EscrowStatus.FUNDED;
    case 'approve_release':
      return isSender && escrow.status === EscrowStatus.RELEASE_REQUESTED;
    case 'raise_dispute':
      return (isSender || isRecipient) && 
             [EscrowStatus.FUNDED, EscrowStatus.RELEASE_REQUESTED].includes(escrow.status);
    case 'cancel':
      return isSender && escrow.status === EscrowStatus.PENDING_FUNDING;
    default:
      return false;
  }
}

export function calculateTimeRemaining(expiresAt: string): string {
  const now = new Date();
  const expires = new Date(expiresAt);
  const diffMs = expires.getTime() - now.getTime();
  
  if (diffMs <= 0) return 'Expired';
  
  const hours = Math.floor(diffMs / (1000 * 60 * 60));
  const days = Math.floor(hours / 24);
  
  if (days > 0) {
    return `${days}d ${hours % 24}h remaining`;
  }
  return `${hours}h remaining`;
}

export function toEscrowSummary(escrow: EscrowContract, userAddress: string): EscrowSummary {
  const isSender = escrow.sender.address.toLowerCase() === userAddress.toLowerCase();
  
  return {
    id: escrow.id,
    status: escrow.status,
    statusLabel: getStatusLabel(escrow.status),
    statusColor: getStatusColor(escrow.status),
    counterparty: isSender 
      ? (escrow.recipient.name || escrow.recipient.address.slice(0, 10) + '...')
      : (escrow.sender.name || escrow.sender.address.slice(0, 10) + '...'),
    amount: escrow.amount,
    token: escrow.token,
    createdDate: new Date(escrow.createdAt).toLocaleDateString(),
    releaseDate: escrow.releasedAt ? new Date(escrow.releasedAt).toLocaleDateString() : undefined,
    timeRemaining: calculateTimeRemaining(escrow.expiresAt),
    canRequestRelease: canPerformAction(escrow, 'request_release', userAddress),
    canRaiseDispute: canPerformAction(escrow, 'raise_dispute', userAddress),
    canCancel: canPerformAction(escrow, 'cancel', userAddress),
    riskLevel: escrow.riskScoreAtCreation > 70 ? 'high' : escrow.riskScoreAtCreation > 40 ? 'medium' : 'low',
  };
}
