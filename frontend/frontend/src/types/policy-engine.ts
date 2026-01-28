/**
 * Policy Engine Types
 * 
 * Ground Truth Reference:
 * - Policies are rules, not suggestions
 * - Every transfer checked against active policy set
 * - Policy versioning for audit trail
 * - War Room users can view/edit, Focus Mode users see effects only
 */

import { Role } from './rbac';

// ═══════════════════════════════════════════════════════════════════════════════
// POLICY STATUS & TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export enum PolicyStatus {
  DRAFT = 'DRAFT',
  PENDING_APPROVAL = 'PENDING_APPROVAL',
  ACTIVE = 'ACTIVE',
  SUSPENDED = 'SUSPENDED',
  DEPRECATED = 'DEPRECATED',
  ARCHIVED = 'ARCHIVED',
}

export enum PolicyType {
  TRANSFER_LIMIT = 'TRANSFER_LIMIT',
  VELOCITY_CHECK = 'VELOCITY_CHECK',
  COUNTERPARTY_RISK = 'COUNTERPARTY_RISK',
  GEOGRAPHIC_RESTRICTION = 'GEOGRAPHIC_RESTRICTION',
  ASSET_RESTRICTION = 'ASSET_RESTRICTION',
  TIME_RESTRICTION = 'TIME_RESTRICTION',
  KYC_REQUIREMENT = 'KYC_REQUIREMENT',
  AML_CHECK = 'AML_CHECK',
  ESCROW_TRIGGER = 'ESCROW_TRIGGER',
  CUSTOM = 'CUSTOM',
}

export enum PolicyAction {
  ALLOW = 'ALLOW',
  BLOCK = 'BLOCK',
  REQUIRE_ESCROW = 'REQUIRE_ESCROW',
  REQUIRE_APPROVAL = 'REQUIRE_APPROVAL',
  FLAG_FOR_REVIEW = 'FLAG_FOR_REVIEW',
  FLAG = 'FLAG',
  DELAY = 'DELAY',
  NOTIFY = 'NOTIFY',
}

export enum PolicyScope {
  GLOBAL = 'GLOBAL',
  ORGANIZATION = 'ORGANIZATION',
  WALLET = 'WALLET',
  ASSET = 'ASSET',
  CHAIN = 'CHAIN',
}

export enum RuleType {
  THRESHOLD = 'THRESHOLD',
  VELOCITY = 'VELOCITY',
  COUNTERPARTY = 'COUNTERPARTY',
  GEOGRAPHIC = 'GEOGRAPHIC',
  TIME_BASED = 'TIME_BASED',
  AMOUNT_LIMIT = 'AMOUNT_LIMIT',
  CUSTOM = 'CUSTOM',
}

export enum ConditionOperator {
  EQ = 'eq',
  NEQ = 'neq',
  GT = 'gt',
  GTE = 'gte',
  LT = 'lt',
  LTE = 'lte',
  IN = 'in',
  NOT_IN = 'not_in',
  CONTAINS = 'contains',
  REGEX = 'regex',
}

// ═══════════════════════════════════════════════════════════════════════════════
// POLICY RULE CONDITIONS
// ═══════════════════════════════════════════════════════════════════════════════

export interface PolicyCondition {
  id?: string;
  field: string;
  operator: 'eq' | 'neq' | 'gt' | 'gte' | 'lt' | 'lte' | 'in' | 'not_in' | 'contains' | 'regex';
  value: string | number | boolean | string[];
  description?: string;
}

export interface PolicyRule {
  id: string;
  name: string;
  description: string;
  priority: number;
  enabled: boolean;
  type?: RuleType;
  
  // Conditions (AND logic within a rule)
  conditions: PolicyCondition[];
  
  // Action when conditions match
  action: PolicyAction;
  actionParams?: {
    escrowDuration?: number;
    delayMinutes?: number;
    notifyRoles?: Role[];
    approvalRequired?: Role[];
    message?: string;
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// POLICY DEFINITION
// ═══════════════════════════════════════════════════════════════════════════════

export interface Policy {
  id: string;
  name: string;
  description: string;
  type: PolicyType;
  status: PolicyStatus;
  scope: PolicyScope;
  
  // Version control
  version: string;
  previousVersionId?: string;
  
  // Rules (OR logic between rules)
  rules: PolicyRule[];
  
  // Additional properties
  priority?: number;
  tags?: string[];
  
  // Metadata
  createdBy: string;
  createdAt: string;
  updatedBy?: string;
  updatedAt?: string;
  approvedBy?: string;
  approvedAt?: string;
  
  // Scope restrictions
  appliesTo?: {
    organizations?: string[];
    wallets?: string[];
    assets?: string[];
    chains?: number[];
  };
  
  // Scheduling
  effectiveFrom?: string;
  effectiveUntil?: string;
  
  // Statistics
  stats?: {
    evaluations: number;
    triggers: number;
    lastTriggered?: string;
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// POLICY SET (Collection of active policies)
// ═══════════════════════════════════════════════════════════════════════════════

export interface PolicySet {
  id: string;
  name: string;
  version: string;
  policies: Policy[];
  activatedAt: string;
  activatedBy: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// POLICY EVALUATION
// ═══════════════════════════════════════════════════════════════════════════════

export interface PolicyEvaluationContext {
  transferAmount: number;
  transferToken: string;
  senderAddress: string;
  recipientAddress: string;
  chainId: number;
  senderRiskScore?: number;
  recipientRiskScore?: number;
  velocity24h?: number;
  velocity7d?: number;
  isNewCounterparty?: boolean;
  senderKycLevel?: number;
  recipientKycLevel?: number;
}

export interface PolicyEvaluationResult {
  policyId: string;
  policyName: string;
  ruleId: string;
  ruleName: string;
  matched: boolean;
  action: PolicyAction;
  actionParams?: PolicyRule['actionParams'];
  evaluatedAt: string;
}

export interface PolicyEvaluationSummary {
  allowed: boolean;
  finalAction: PolicyAction;
  triggeredPolicies: PolicyEvaluationResult[];
  escrowRequired: boolean;
  escrowDuration?: number;
  approvalRequired: boolean;
  approvalRoles?: Role[];
  warnings: string[];
  evaluatedAt: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// POLICY CHANGE REQUEST
// ═══════════════════════════════════════════════════════════════════════════════

export interface PolicyChangeRequest {
  id: string;
  type: 'create' | 'update' | 'activate' | 'suspend' | 'deprecate';
  policyId?: string;
  proposedPolicy?: Policy;
  reason: string;
  requestedBy: string;
  requestedAt: string;
  status: 'pending' | 'approved' | 'rejected';
  approvals: {
    role: Role;
    approvedBy: string;
    approvedAt: string;
  }[];
  requiredApprovals: number;
}

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

export function getPolicyTypeLabel(type: PolicyType): string {
  const labels: Record<PolicyType, string> = {
    [PolicyType.TRANSFER_LIMIT]: 'Transfer Limit',
    [PolicyType.VELOCITY_CHECK]: 'Velocity Check',
    [PolicyType.COUNTERPARTY_RISK]: 'Counterparty Risk',
    [PolicyType.GEOGRAPHIC_RESTRICTION]: 'Geographic Restriction',
    [PolicyType.ASSET_RESTRICTION]: 'Asset Restriction',
    [PolicyType.TIME_RESTRICTION]: 'Time Restriction',
    [PolicyType.KYC_REQUIREMENT]: 'KYC Requirement',
    [PolicyType.AML_CHECK]: 'AML Check',
    [PolicyType.ESCROW_TRIGGER]: 'Escrow Trigger',
    [PolicyType.CUSTOM]: 'Custom Policy',
  };
  return labels[type];
}

export function getPolicyStatusColor(status: PolicyStatus): string {
  const colors: Record<PolicyStatus, string> = {
    [PolicyStatus.DRAFT]: 'gray',
    [PolicyStatus.PENDING_APPROVAL]: 'yellow',
    [PolicyStatus.ACTIVE]: 'green',
    [PolicyStatus.SUSPENDED]: 'orange',
    [PolicyStatus.DEPRECATED]: 'red',
    [PolicyStatus.ARCHIVED]: 'slate',
  };
  return colors[status];
}

export function getActionLabel(action: PolicyAction): string {
  const labels: Record<PolicyAction, string> = {
    [PolicyAction.ALLOW]: 'Allow',
    [PolicyAction.BLOCK]: 'Block',
    [PolicyAction.REQUIRE_ESCROW]: 'Require Escrow',
    [PolicyAction.REQUIRE_APPROVAL]: 'Require Approval',
    [PolicyAction.FLAG_FOR_REVIEW]: 'Flag for Review',
    [PolicyAction.FLAG]: 'Flag',
    [PolicyAction.DELAY]: 'Delay',
    [PolicyAction.NOTIFY]: 'Notify',
  };
  return labels[action];
}

export function getActionColor(action: PolicyAction): string {
  const colors: Record<PolicyAction, string> = {
    [PolicyAction.ALLOW]: 'green',
    [PolicyAction.BLOCK]: 'red',
    [PolicyAction.REQUIRE_ESCROW]: 'orange',
    [PolicyAction.REQUIRE_APPROVAL]: 'yellow',
    [PolicyAction.FLAG_FOR_REVIEW]: 'blue',
    [PolicyAction.FLAG]: 'blue',
    [PolicyAction.DELAY]: 'amber',
    [PolicyAction.NOTIFY]: 'cyan',
  };
  return colors[action];
}

export function getOperatorLabel(operator: PolicyCondition['operator']): string {
  const labels: Record<PolicyCondition['operator'], string> = {
    eq: 'equals',
    neq: 'not equals',
    gt: 'greater than',
    gte: 'greater than or equal',
    lt: 'less than',
    lte: 'less than or equal',
    in: 'is in',
    not_in: 'is not in',
    contains: 'contains',
    regex: 'matches pattern',
  };
  return labels[operator];
}

// Common policy templates
export const POLICY_TEMPLATES: Partial<Policy>[] = [
  {
    name: 'High Value Transfer Escrow',
    description: 'Require escrow for transfers above $10,000',
    type: PolicyType.ESCROW_TRIGGER,
    rules: [
      {
        id: 'rule_1',
        name: 'Large transfer check',
        description: 'Trigger escrow for high-value transfers',
        priority: 1,
        enabled: true,
        conditions: [
          {
            id: 'cond_1',
            field: 'transferAmountUSD',
            operator: 'gte',
            value: 10000,
            description: 'Transfer value >= $10,000',
          },
        ],
        action: PolicyAction.REQUIRE_ESCROW,
        actionParams: {
          escrowDuration: 48,
          message: 'High-value transfers require a 48-hour escrow period.',
        },
      },
    ],
  },
  {
    name: 'Velocity Anomaly Detection',
    description: 'Flag accounts with unusual transaction velocity',
    type: PolicyType.VELOCITY_CHECK,
    rules: [
      {
        id: 'rule_1',
        name: 'Velocity spike',
        description: 'Detect 3x velocity increase',
        priority: 1,
        enabled: true,
        conditions: [
          {
            id: 'cond_1',
            field: 'velocityDeviation',
            operator: 'gte',
            value: 3,
            description: 'Velocity 3x above baseline',
          },
        ],
        action: PolicyAction.FLAG_FOR_REVIEW,
        actionParams: {
          notifyRoles: [Role.R4_INSTITUTION_COMPLIANCE],
          message: 'Unusual transaction velocity detected.',
        },
      },
    ],
  },
  {
    name: 'New Counterparty Protection',
    description: 'Additional checks for first-time counterparties',
    type: PolicyType.COUNTERPARTY_RISK,
    rules: [
      {
        id: 'rule_1',
        name: 'New counterparty escrow',
        description: 'Escrow for new counterparties',
        priority: 1,
        enabled: true,
        conditions: [
          {
            id: 'cond_1',
            field: 'isNewCounterparty',
            operator: 'eq',
            value: true,
            description: 'First transaction with this counterparty',
          },
        ],
        action: PolicyAction.REQUIRE_ESCROW,
        actionParams: {
          escrowDuration: 24,
          message: 'First-time counterparty transfers are held for 24 hours.',
        },
      },
    ],
  },
];

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

export function getRuleTypeLabel(type: RuleType): string {
  const labels: Record<RuleType, string> = {
    [RuleType.THRESHOLD]: 'Threshold Rule',
    [RuleType.VELOCITY]: 'Velocity Rule',
    [RuleType.COUNTERPARTY]: 'Counterparty Rule',
    [RuleType.GEOGRAPHIC]: 'Geographic Rule',
    [RuleType.TIME_BASED]: 'Time-Based Rule',
    [RuleType.AMOUNT_LIMIT]: 'Amount Limit Rule',
    [RuleType.CUSTOM]: 'Custom Rule',
  };
  return labels[type] || type;
}

export function getConditionOperatorLabel(op: ConditionOperator | string): string {
  const labels: Record<string, string> = {
    'eq': 'equals',
    'neq': 'not equals',
    'gt': 'greater than',
    'gte': 'at least',
    'lt': 'less than',
    'lte': 'at most',
    'in': 'in',
    'not_in': 'not in',
    'contains': 'contains',
    'regex': 'matches pattern',
  };
  return labels[op] || op;
}

// ═══════════════════════════════════════════════════════════════════════════════
// RISK LEVEL & SIMULATION TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export enum RiskLevel {
  LOW = 'LOW',
  MEDIUM = 'MEDIUM',
  HIGH = 'HIGH',
  CRITICAL = 'CRITICAL',
}

export interface TransferContext {
  from: string;
  to: string;
  amount: number;
  currency: string;
  metadata?: Record<string, unknown>;
}

export interface SimulationResult {
  allowed: boolean;
  action: PolicyAction;
  riskLevel: RiskLevel;
  triggeredPolicies: string[];
  reasons: string[];
  estimatedDelay?: number;
  requiredApprovers?: string[];
}