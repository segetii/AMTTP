/**
 * Dispute Resolution Types
 * 
 * Ground Truth Reference:
 * - Disputes are evidence-driven, not emotion-driven
 * - Kleros integration for decentralized arbitration
 * - Clear lifecycle: Filed → Evidence → Arbitration → Resolved
 * - Both parties can submit evidence
 */

import { Role } from './rbac';

// ═══════════════════════════════════════════════════════════════════════════════
// DISPUTE STATUS
// ═══════════════════════════════════════════════════════════════════════════════

export enum DisputeStatus {
  DRAFT = 'DRAFT',
  FILED = 'FILED',
  EVIDENCE_PERIOD = 'EVIDENCE_PERIOD',
  AWAITING_ARBITRATION = 'AWAITING_ARBITRATION',
  IN_ARBITRATION = 'IN_ARBITRATION',
  APPEAL_PERIOD = 'APPEAL_PERIOD',
  APPEALED = 'APPEALED',
  RESOLVED = 'RESOLVED',
  WITHDRAWN = 'WITHDRAWN',
}

export enum DisputeCategory {
  NON_DELIVERY = 'NON_DELIVERY',
  NOT_AS_DESCRIBED = 'NOT_AS_DESCRIBED',
  UNAUTHORIZED = 'UNAUTHORIZED',
  DUPLICATE = 'DUPLICATE',
  FRAUD = 'FRAUD',
  CONTRACT_BREACH = 'CONTRACT_BREACH',
  OTHER = 'OTHER',
}

export enum DisputeOutcome {
  PENDING = 'PENDING',
  CLAIMANT_WINS = 'CLAIMANT_WINS',
  RESPONDENT_WINS = 'RESPONDENT_WINS',
  SPLIT = 'SPLIT',
  DISMISSED = 'DISMISSED',
  SETTLED = 'SETTLED',
}

// ═══════════════════════════════════════════════════════════════════════════════
// EVIDENCE
// ═══════════════════════════════════════════════════════════════════════════════

export interface Evidence {
  id: string;
  disputeId: string;
  submittedBy: string;
  submittedAt: string;
  
  // Content
  title: string;
  description: string;
  category: 'document' | 'screenshot' | 'transaction' | 'communication' | 'witness' | 'other';
  
  // Files
  fileHashes: string[];
  ipfsLinks?: string[];
  
  // Verification
  verified: boolean;
  verifiedAt?: string;
  verifiedBy?: string;
  
  // Metadata
  onChainTxHash?: string;
}

export interface EvidenceSubmission {
  disputeId: string;
  title: string;
  description: string;
  category: Evidence['category'];
  files: File[];
}

// ═══════════════════════════════════════════════════════════════════════════════
// DISPUTE
// ═══════════════════════════════════════════════════════════════════════════════

export interface Dispute {
  id: string;
  status: DisputeStatus;
  category: DisputeCategory;
  outcome: DisputeOutcome;
  
  // Related escrow
  escrowId: string;
  escrowAmount: string;
  escrowToken: string;
  
  // Parties
  claimant: {
    address: string;
    name?: string;
    role: 'sender' | 'recipient';
  };
  respondent: {
    address: string;
    name?: string;
    role: 'sender' | 'recipient';
  };
  
  // Claim
  claim: {
    summary: string;
    requestedOutcome: 'full_refund' | 'partial_refund' | 'release_to_recipient' | 'split';
    requestedAmount?: string;
    details: string;
  };
  
  // Response
  response?: {
    summary: string;
    counterClaim?: string;
    submittedAt: string;
  };
  
  // Evidence
  evidence: Evidence[];
  evidenceDeadline: string;
  
  // Arbitration
  arbitrationProvider: 'kleros' | 'internal' | 'mediation';
  klerosDisputeId?: number;
  klerosCourtId?: number;
  arbitrationFee: string;
  arbitrationFeeToken: string;
  
  // Timeline
  filedAt: string;
  responseDeadline: string;
  arbitrationStartedAt?: string;
  resolvedAt?: string;
  
  // Resolution
  resolution?: {
    outcome: DisputeOutcome;
    summary: string;
    claimantAmount: string;
    respondentAmount: string;
    arbitratorNotes?: string;
    appealDeadline?: string;
  };
  
  // On-chain
  txHash: string;
  contractAddress: string;
  
  // UI integrity
  uiSnapshotHash: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// DISPUTE ACTIONS
// ═══════════════════════════════════════════════════════════════════════════════

export interface FileDisputeParams {
  escrowId: string;
  category: DisputeCategory;
  summary: string;
  details: string;
  requestedOutcome: Dispute['claim']['requestedOutcome'];
  requestedAmount?: string;
  initialEvidence?: EvidenceSubmission;
}

export interface RespondToDisputeParams {
  disputeId: string;
  summary: string;
  counterClaim?: string;
}

export interface AppealDisputeParams {
  disputeId: string;
  reason: string;
  additionalEvidence?: EvidenceSubmission;
}

// ═══════════════════════════════════════════════════════════════════════════════
// KLEROS INTEGRATION
// ═══════════════════════════════════════════════════════════════════════════════

export interface KlerosConfig {
  courtId: number;
  courtName: string;
  minStake: string;
  feeForJuror: string;
  jurorsForCourtJump: number;
  timesPerPeriod: number[];
}

export const KLEROS_COURTS: Record<string, KlerosConfig> = {
  general: {
    courtId: 0,
    courtName: 'General Court',
    minStake: '0.1',
    feeForJuror: '0.01',
    jurorsForCourtJump: 31,
    timesPerPeriod: [280800, 583200, 583200, 388800, 280800],
  },
  ecommerce: {
    courtId: 2,
    courtName: 'E-commerce Court',
    minStake: '0.2',
    feeForJuror: '0.02',
    jurorsForCourtJump: 15,
    timesPerPeriod: [280800, 432000, 432000, 259200, 280800],
  },
  technical: {
    courtId: 6,
    courtName: 'Technical Court',
    minStake: '0.5',
    feeForJuror: '0.05',
    jurorsForCourtJump: 31,
    timesPerPeriod: [604800, 604800, 604800, 432000, 604800],
  },
};

// ═══════════════════════════════════════════════════════════════════════════════
// DISPUTE SUMMARY (Focus Mode View)
// ═══════════════════════════════════════════════════════════════════════════════

export interface DisputeSummary {
  id: string;
  status: DisputeStatus;
  statusLabel: string;
  statusColor: 'blue' | 'yellow' | 'orange' | 'red' | 'green' | 'gray';
  
  // Simplified display
  counterparty: string;
  amount: string;
  token: string;
  category: string;
  
  // Timeline
  filedDate: string;
  deadline?: string;
  
  // Role
  isClaimant: boolean;
  
  // Actions
  canSubmitEvidence: boolean;
  canRespond: boolean;
  canAppeal: boolean;
}

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

export function getDisputeStatusLabel(status: DisputeStatus): string {
  const labels: Record<DisputeStatus, string> = {
    [DisputeStatus.DRAFT]: 'Draft',
    [DisputeStatus.FILED]: 'Filed',
    [DisputeStatus.EVIDENCE_PERIOD]: 'Collecting Evidence',
    [DisputeStatus.AWAITING_ARBITRATION]: 'Awaiting Arbitrators',
    [DisputeStatus.IN_ARBITRATION]: 'Under Review',
    [DisputeStatus.APPEAL_PERIOD]: 'Appeal Window',
    [DisputeStatus.APPEALED]: 'Appealed',
    [DisputeStatus.RESOLVED]: 'Resolved',
    [DisputeStatus.WITHDRAWN]: 'Withdrawn',
  };
  return labels[status];
}

export function getDisputeStatusColor(status: DisputeStatus): DisputeSummary['statusColor'] {
  switch (status) {
    case DisputeStatus.DRAFT:
      return 'gray';
    case DisputeStatus.FILED:
    case DisputeStatus.EVIDENCE_PERIOD:
      return 'blue';
    case DisputeStatus.AWAITING_ARBITRATION:
    case DisputeStatus.IN_ARBITRATION:
      return 'yellow';
    case DisputeStatus.APPEAL_PERIOD:
    case DisputeStatus.APPEALED:
      return 'orange';
    case DisputeStatus.RESOLVED:
      return 'green';
    case DisputeStatus.WITHDRAWN:
      return 'gray';
    default:
      return 'gray';
  }
}

export function getCategoryLabel(category: DisputeCategory): string {
  const labels: Record<DisputeCategory, string> = {
    [DisputeCategory.NON_DELIVERY]: 'Non-Delivery',
    [DisputeCategory.NOT_AS_DESCRIBED]: 'Not As Described',
    [DisputeCategory.UNAUTHORIZED]: 'Unauthorized Transaction',
    [DisputeCategory.DUPLICATE]: 'Duplicate Transaction',
    [DisputeCategory.FRAUD]: 'Fraud',
    [DisputeCategory.CONTRACT_BREACH]: 'Contract Breach',
    [DisputeCategory.OTHER]: 'Other',
  };
  return labels[category];
}

export function getOutcomeLabel(outcome: DisputeOutcome): string {
  const labels: Record<DisputeOutcome, string> = {
    [DisputeOutcome.PENDING]: 'Pending',
    [DisputeOutcome.CLAIMANT_WINS]: 'Ruled for Claimant',
    [DisputeOutcome.RESPONDENT_WINS]: 'Ruled for Respondent',
    [DisputeOutcome.SPLIT]: 'Split Decision',
    [DisputeOutcome.DISMISSED]: 'Dismissed',
    [DisputeOutcome.SETTLED]: 'Settled',
  };
  return labels[outcome];
}

export function canSubmitEvidence(dispute: Dispute): boolean {
  return [DisputeStatus.FILED, DisputeStatus.EVIDENCE_PERIOD].includes(dispute.status) &&
         new Date(dispute.evidenceDeadline) > new Date();
}

export function canAppeal(dispute: Dispute, userAddress: string): boolean {
  if (dispute.status !== DisputeStatus.APPEAL_PERIOD) return false;
  if (!dispute.resolution?.appealDeadline) return false;
  if (new Date(dispute.resolution.appealDeadline) < new Date()) return false;
  
  const isClaimant = dispute.claimant.address.toLowerCase() === userAddress.toLowerCase();
  const isRespondent = dispute.respondent.address.toLowerCase() === userAddress.toLowerCase();
  
  // Can appeal if you lost
  if (isClaimant && dispute.outcome === DisputeOutcome.RESPONDENT_WINS) return true;
  if (isRespondent && dispute.outcome === DisputeOutcome.CLAIMANT_WINS) return true;
  
  return false;
}

export function toDisputeSummary(dispute: Dispute, userAddress: string): DisputeSummary {
  const isClaimant = dispute.claimant.address.toLowerCase() === userAddress.toLowerCase();
  const counterparty = isClaimant ? dispute.respondent : dispute.claimant;
  
  let deadline: string | undefined;
  if (dispute.status === DisputeStatus.EVIDENCE_PERIOD) {
    deadline = new Date(dispute.evidenceDeadline).toLocaleDateString();
  } else if (dispute.status === DisputeStatus.APPEAL_PERIOD && dispute.resolution?.appealDeadline) {
    deadline = new Date(dispute.resolution.appealDeadline).toLocaleDateString();
  }
  
  return {
    id: dispute.id,
    status: dispute.status,
    statusLabel: getDisputeStatusLabel(dispute.status),
    statusColor: getDisputeStatusColor(dispute.status),
    counterparty: counterparty.name || counterparty.address.slice(0, 10) + '...',
    amount: dispute.escrowAmount,
    token: dispute.escrowToken,
    category: getCategoryLabel(dispute.category),
    filedDate: new Date(dispute.filedAt).toLocaleDateString(),
    deadline,
    isClaimant,
    canSubmitEvidence: canSubmitEvidence(dispute),
    canRespond: !isClaimant && dispute.status === DisputeStatus.FILED && !dispute.response,
    canAppeal: canAppeal(dispute, userAddress),
  };
}
