/**
 * AMTTP Policy Engine
 * Cedar/OPA-style policy-as-code layer
 * Separates regulatory rules from ML models for FCA defensibility
 */

import { createHash } from 'crypto';

// ═══════════════════════════════════════════════════════════════════════════
// POLICY TYPES
// ═══════════════════════════════════════════════════════════════════════════

export interface PolicyContext {
  riskScore: number;
  amount: number;
  jurisdiction: string;
  senderAddress: string;
  receiverAddress: string;
  assetType: string;
  kycLevel: 'none' | 'basic' | 'enhanced' | 'full';
  sanctionsMatch: boolean;
  pepMatch: boolean;
  transactionVelocity: number; // tx count in last 24h
  cumulativeValue24h: number;
  isHighRiskCountry: boolean;
  timestamp: Date;
}

export interface PolicyDecision {
  action: 'ALLOW' | 'BLOCK' | 'REVIEW' | 'ESCALATE';
  reason: string;
  triggeredPolicies: string[];
  sarRequired: boolean;
  freezeRequired: boolean;
  explanationHash: string;
  timestamp: Date;
  policyVersion: string;
}

export interface Policy {
  id: string;
  name: string;
  description: string;
  priority: number; // Lower = higher priority
  condition: (ctx: PolicyContext) => boolean;
  action: PolicyDecision['action'];
  sarRequired: boolean;
  freezeRequired: boolean;
  enabled: boolean;
  jurisdiction: string[]; // Empty = all jurisdictions
  effectiveDate: Date;
  expiryDate?: Date;
}

// ═══════════════════════════════════════════════════════════════════════════
// REGULATORY POLICIES (FCA/AMLD6/FATF aligned)
// ═══════════════════════════════════════════════════════════════════════════

const POLICIES: Policy[] = [
  // ── SANCTIONS (Highest Priority) ──────────────────────────────────────────
  {
    id: 'POL-001',
    name: 'Sanctions Block',
    description: 'Block transactions involving sanctioned entities (OFAC/UK/EU)',
    priority: 1,
    condition: (ctx) => ctx.sanctionsMatch === true,
    action: 'BLOCK',
    sarRequired: true,
    freezeRequired: true,
    enabled: true,
    jurisdiction: [],
    effectiveDate: new Date('2024-01-01'),
  },

  // ── PEP CONTROLS ──────────────────────────────────────────────────────────
  {
    id: 'POL-002',
    name: 'PEP High Value',
    description: 'Escalate PEP transactions over £10,000',
    priority: 2,
    condition: (ctx) => ctx.pepMatch && ctx.amount > 10000,
    action: 'ESCALATE',
    sarRequired: false,
    freezeRequired: false,
    enabled: true,
    jurisdiction: ['UK', 'EU'],
    effectiveDate: new Date('2024-01-01'),
  },

  // ── HIGH RISK COUNTRY ─────────────────────────────────────────────────────
  {
    id: 'POL-003',
    name: 'High Risk Country Block',
    description: 'Block transactions from FATF high-risk jurisdictions over threshold',
    priority: 3,
    condition: (ctx) => ctx.isHighRiskCountry && ctx.amount > 1000,
    action: 'BLOCK',
    sarRequired: true,
    freezeRequired: false,
    enabled: true,
    jurisdiction: [],
    effectiveDate: new Date('2024-01-01'),
  },

  // ── ML RISK SCORE THRESHOLDS ──────────────────────────────────────────────
  {
    id: 'POL-010',
    name: 'Critical Risk Block',
    description: 'Block transactions with risk score > 0.95',
    priority: 10,
    condition: (ctx) => ctx.riskScore > 0.95,
    action: 'BLOCK',
    sarRequired: true,
    freezeRequired: true,
    enabled: true,
    jurisdiction: [],
    effectiveDate: new Date('2024-01-01'),
  },
  {
    id: 'POL-011',
    name: 'High Risk UK SAR',
    description: 'Trigger SAR for UK transactions with risk > 0.85',
    priority: 11,
    condition: (ctx) => ctx.riskScore > 0.85 && ctx.jurisdiction === 'UK',
    action: 'REVIEW',
    sarRequired: true,
    freezeRequired: false,
    enabled: true,
    jurisdiction: ['UK'],
    effectiveDate: new Date('2024-01-01'),
  },
  {
    id: 'POL-012',
    name: 'Medium-High Risk Review',
    description: 'Manual review for risk scores 0.7-0.85',
    priority: 12,
    condition: (ctx) => ctx.riskScore > 0.7 && ctx.riskScore <= 0.85,
    action: 'REVIEW',
    sarRequired: false,
    freezeRequired: false,
    enabled: true,
    jurisdiction: [],
    effectiveDate: new Date('2024-01-01'),
  },

  // ── VALUE THRESHOLDS (FCA/AMLD6) ──────────────────────────────────────────
  {
    id: 'POL-020',
    name: 'Large Value Review',
    description: 'Review transactions over £15,000 (FCA threshold)',
    priority: 20,
    condition: (ctx) => ctx.amount > 15000,
    action: 'REVIEW',
    sarRequired: false,
    freezeRequired: false,
    enabled: true,
    jurisdiction: ['UK'],
    effectiveDate: new Date('2024-01-01'),
  },
  {
    id: 'POL-021',
    name: 'Very Large Value Escalate',
    description: 'Escalate transactions over £50,000',
    priority: 21,
    condition: (ctx) => ctx.amount > 50000,
    action: 'ESCALATE',
    sarRequired: false,
    freezeRequired: false,
    enabled: true,
    jurisdiction: ['UK', 'EU'],
    effectiveDate: new Date('2024-01-01'),
  },

  // ── KYC CONTROLS ──────────────────────────────────────────────────────────
  {
    id: 'POL-030',
    name: 'No KYC Block',
    description: 'Block transactions over £1000 without KYC',
    priority: 30,
    condition: (ctx) => ctx.kycLevel === 'none' && ctx.amount > 1000,
    action: 'BLOCK',
    sarRequired: false,
    freezeRequired: false,
    enabled: true,
    jurisdiction: ['UK', 'EU'],
    effectiveDate: new Date('2024-01-01'),
  },
  {
    id: 'POL-031',
    name: 'Basic KYC High Value',
    description: 'Require enhanced KYC for transactions over £10,000',
    priority: 31,
    condition: (ctx) => ctx.kycLevel === 'basic' && ctx.amount > 10000,
    action: 'REVIEW',
    sarRequired: false,
    freezeRequired: false,
    enabled: true,
    jurisdiction: ['UK', 'EU'],
    effectiveDate: new Date('2024-01-01'),
  },

  // ── VELOCITY CONTROLS ─────────────────────────────────────────────────────
  {
    id: 'POL-040',
    name: 'High Velocity Alert',
    description: 'Review accounts with >20 transactions in 24h',
    priority: 40,
    condition: (ctx) => ctx.transactionVelocity > 20,
    action: 'REVIEW',
    sarRequired: false,
    freezeRequired: false,
    enabled: true,
    jurisdiction: [],
    effectiveDate: new Date('2024-01-01'),
  },
  {
    id: 'POL-041',
    name: 'Cumulative Value Alert',
    description: 'Review if 24h cumulative value exceeds £100,000',
    priority: 41,
    condition: (ctx) => ctx.cumulativeValue24h > 100000,
    action: 'REVIEW',
    sarRequired: false,
    freezeRequired: false,
    enabled: true,
    jurisdiction: ['UK', 'EU'],
    effectiveDate: new Date('2024-01-01'),
  },
];

// ═══════════════════════════════════════════════════════════════════════════
// POLICY ENGINE CLASS
// ═══════════════════════════════════════════════════════════════════════════

export class PolicyEngine {
  private policies: Policy[];
  private policyVersion: string;

  constructor() {
    this.policies = [...POLICIES];
    this.policyVersion = this.computePolicyVersion();
  }

  private computePolicyVersion(): string {
    const policyData = JSON.stringify(this.policies.map(p => ({
      id: p.id,
      name: p.name,
      priority: p.priority,
      enabled: p.enabled,
      effectiveDate: p.effectiveDate.toISOString(),
    })));
    return createHash('sha256').update(policyData).digest('hex').substring(0, 16);
  }

  /**
   * Evaluate all policies against a transaction context
   * Returns the highest-priority matching decision
   */
  evaluate(context: PolicyContext): PolicyDecision {
    const now = new Date();
    const triggeredPolicies: string[] = [];
    let finalAction: PolicyDecision['action'] = 'ALLOW';
    let finalReason = 'No policy triggered - transaction allowed';
    let sarRequired = false;
    let freezeRequired = false;

    // Sort by priority (lower = higher priority)
    const activePolicies = this.policies
      .filter(p => p.enabled)
      .filter(p => p.effectiveDate <= now)
      .filter(p => !p.expiryDate || p.expiryDate > now)
      .filter(p => p.jurisdiction.length === 0 || p.jurisdiction.includes(context.jurisdiction))
      .sort((a, b) => a.priority - b.priority);

    for (const policy of activePolicies) {
      try {
        if (policy.condition(context)) {
          triggeredPolicies.push(policy.id);
          
          // Take the most restrictive action
          const actionPriority: Record<PolicyDecision['action'], number> = {
            'BLOCK': 1,
            'ESCALATE': 2,
            'REVIEW': 3,
            'ALLOW': 4,
          };

          if (actionPriority[policy.action] < actionPriority[finalAction]) {
            finalAction = policy.action;
            finalReason = `${policy.name}: ${policy.description}`;
          }

          if (policy.sarRequired) sarRequired = true;
          if (policy.freezeRequired) freezeRequired = true;
        }
      } catch (error) {
        console.error(`Policy ${policy.id} evaluation error:`, error);
      }
    }

    const decision: PolicyDecision = {
      action: finalAction,
      reason: finalReason,
      triggeredPolicies,
      sarRequired,
      freezeRequired,
      explanationHash: this.computeExplanationHash(context, triggeredPolicies),
      timestamp: now,
      policyVersion: this.policyVersion,
    };

    return decision;
  }

  private computeExplanationHash(context: PolicyContext, triggeredPolicies: string[]): string {
    const data = JSON.stringify({
      context: {
        riskScore: context.riskScore,
        amount: context.amount,
        jurisdiction: context.jurisdiction,
        kycLevel: context.kycLevel,
        sanctionsMatch: context.sanctionsMatch,
        pepMatch: context.pepMatch,
      },
      triggeredPolicies,
      timestamp: new Date().toISOString(),
    });
    return createHash('sha256').update(data).digest('hex');
  }

  /**
   * Get all policies for audit/display
   */
  getPolicies(): Policy[] {
    return [...this.policies];
  }

  /**
   * Add a custom policy at runtime
   */
  addPolicy(policy: Policy): void {
    this.policies.push(policy);
    this.policyVersion = this.computePolicyVersion();
  }

  /**
   * Enable/disable a policy
   */
  setEnabled(policyId: string, enabled: boolean): boolean {
    const policy = this.policies.find(p => p.id === policyId);
    if (policy) {
      policy.enabled = enabled;
      this.policyVersion = this.computePolicyVersion();
      return true;
    }
    return false;
  }

  /**
   * Get current policy version hash
   */
  getVersion(): string {
    return this.policyVersion;
  }

  /**
   * Export policies for XAI/audit purposes
   */
  exportForAudit(): object {
    return {
      version: this.policyVersion,
      exportedAt: new Date().toISOString(),
      policies: this.policies.map(p => ({
        id: p.id,
        name: p.name,
        description: p.description,
        priority: p.priority,
        action: p.action,
        sarRequired: p.sarRequired,
        freezeRequired: p.freezeRequired,
        enabled: p.enabled,
        jurisdiction: p.jurisdiction,
        effectiveDate: p.effectiveDate.toISOString(),
        expiryDate: p.expiryDate?.toISOString(),
      })),
    };
  }
}

// Singleton instance
let policyEngineInstance: PolicyEngine | null = null;

export function getPolicyEngine(): PolicyEngine {
  if (!policyEngineInstance) {
    policyEngineInstance = new PolicyEngine();
  }
  return policyEngineInstance;
}

export default PolicyEngine;
