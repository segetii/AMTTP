/**
 * Policy Engine Service
 * 
 * Ground Truth Reference:
 * - Policies are rules, not suggestions
 * - Every transfer evaluated against active policy set
 * - Version control for compliance audit
 */

'use client';

import { useState, useCallback, useEffect } from 'react';
import {
  Policy,
  PolicyStatus,
  PolicyType,
  PolicyAction,
  PolicyScope,
  PolicyRule,
  PolicyCondition,
  PolicyEvaluationContext,
  PolicyEvaluationResult,
  PolicyEvaluationSummary,
  PolicyChangeRequest,
  PolicySet,
  POLICY_TEMPLATES,
} from '@/types/policy-engine';
import { Role } from '@/types/rbac';
import { sha256 } from './ui-snapshot-chain';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8007';

// ═══════════════════════════════════════════════════════════════════════════════
// SERVICE RESULT TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface PolicyServiceResult<T = void> {
  success: boolean;
  data?: T;
  error?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// MOCK DATA - Would come from backend in production
// ═══════════════════════════════════════════════════════════════════════════════

const MOCK_POLICIES: Policy[] = [
  {
    id: 'policy_001',
    name: 'High Value Transfer Escrow',
    description: 'Require escrow for transfers above $10,000 USD',
    type: PolicyType.ESCROW_TRIGGER,
    status: PolicyStatus.ACTIVE,
    scope: PolicyScope.GLOBAL,
    version: '1.2.0',
    rules: [
      {
        id: 'rule_001',
        name: 'Large Transfer Check',
        description: 'Trigger escrow for high-value transfers',
        priority: 1,
        enabled: true,
        conditions: [
          {
            id: 'cond_001',
            field: 'transferAmountUSD',
            operator: 'gte',
            value: 10000,
            description: 'Transfer >= $10,000',
          },
        ],
        action: PolicyAction.REQUIRE_ESCROW,
        actionParams: {
          escrowDuration: 48,
          message: 'High-value transfers require 48-hour escrow.',
        },
      },
    ],
    createdBy: 'admin_001',
    createdAt: '2024-01-15T10:00:00Z',
    approvedBy: 'compliance_001',
    approvedAt: '2024-01-16T14:30:00Z',
    stats: {
      evaluations: 15420,
      triggers: 342,
      lastTriggered: '2024-03-20T08:15:00Z',
    },
  },
  {
    id: 'policy_002',
    name: 'Velocity Anomaly Detection',
    description: 'Flag accounts with unusual transaction velocity',
    type: PolicyType.VELOCITY_CHECK,
    status: PolicyStatus.ACTIVE,
    scope: PolicyScope.GLOBAL,
    version: '2.0.1',
    rules: [
      {
        id: 'rule_002',
        name: 'Velocity Spike Detection',
        description: 'Detect 3x velocity increase from baseline',
        priority: 1,
        enabled: true,
        conditions: [
          {
            id: 'cond_002',
            field: 'velocityDeviation',
            operator: 'gte',
            value: 3,
            description: 'Velocity 3x above 30-day baseline',
          },
        ],
        action: PolicyAction.FLAG_FOR_REVIEW,
        actionParams: {
          notifyRoles: [Role.R4_INSTITUTION_COMPLIANCE],
        },
      },
    ],
    createdBy: 'admin_001',
    createdAt: '2024-02-01T09:00:00Z',
    approvedBy: 'compliance_001',
    approvedAt: '2024-02-02T11:00:00Z',
    stats: {
      evaluations: 12800,
      triggers: 89,
      lastTriggered: '2024-03-19T22:45:00Z',
    },
  },
  {
    id: 'policy_003',
    name: 'New Counterparty Protection',
    description: 'Additional verification for first-time counterparties',
    type: PolicyType.COUNTERPARTY_RISK,
    status: PolicyStatus.ACTIVE,
    scope: PolicyScope.GLOBAL,
    version: '1.0.0',
    rules: [
      {
        id: 'rule_003',
        name: 'First Transaction Escrow',
        description: 'Hold first transaction with new counterparty',
        priority: 2,
        enabled: true,
        conditions: [
          {
            id: 'cond_003',
            field: 'isNewCounterparty',
            operator: 'eq',
            value: true,
            description: 'Never transacted before',
          },
        ],
        action: PolicyAction.REQUIRE_ESCROW,
        actionParams: {
          escrowDuration: 24,
        },
      },
    ],
    createdBy: 'admin_002',
    createdAt: '2024-02-15T14:00:00Z',
    approvedBy: 'compliance_002',
    approvedAt: '2024-02-16T10:00:00Z',
    stats: {
      evaluations: 8500,
      triggers: 1250,
      lastTriggered: '2024-03-20T09:30:00Z',
    },
  },
  {
    id: 'policy_004',
    name: 'High Risk Score Block',
    description: 'Block transfers involving high-risk addresses',
    type: PolicyType.COUNTERPARTY_RISK,
    status: PolicyStatus.ACTIVE,
    scope: PolicyScope.GLOBAL,
    version: '1.1.0',
    rules: [
      {
        id: 'rule_004',
        name: 'Risk Score Threshold',
        description: 'Block if either party has risk score > 85',
        priority: 0,
        enabled: true,
        conditions: [
          {
            id: 'cond_004a',
            field: 'senderRiskScore',
            operator: 'gt',
            value: 85,
            description: 'Sender risk > 85',
          },
        ],
        action: PolicyAction.BLOCK,
        actionParams: {
          message: 'Transfer blocked due to high-risk counterparty.',
        },
      },
      {
        id: 'rule_005',
        name: 'Recipient Risk Check',
        description: 'Block if recipient has high risk',
        priority: 0,
        enabled: true,
        conditions: [
          {
            id: 'cond_004b',
            field: 'recipientRiskScore',
            operator: 'gt',
            value: 85,
            description: 'Recipient risk > 85',
          },
        ],
        action: PolicyAction.BLOCK,
        actionParams: {
          message: 'Transfer blocked due to high-risk recipient.',
        },
      },
    ],
    createdBy: 'admin_001',
    createdAt: '2024-01-20T08:00:00Z',
    approvedBy: 'compliance_001',
    approvedAt: '2024-01-21T09:00:00Z',
    stats: {
      evaluations: 15420,
      triggers: 23,
      lastTriggered: '2024-03-18T16:20:00Z',
    },
  },
  {
    id: 'policy_005',
    name: 'Weekend Transfer Delay',
    description: 'Delay large transfers initiated on weekends',
    type: PolicyType.TIME_RESTRICTION,
    status: PolicyStatus.SUSPENDED,
    scope: PolicyScope.GLOBAL,
    version: '1.0.0',
    rules: [
      {
        id: 'rule_006',
        name: 'Weekend Large Transfer',
        description: 'Delay weekend transfers > $5000',
        priority: 3,
        enabled: true,
        conditions: [
          {
            id: 'cond_005a',
            field: 'dayOfWeek',
            operator: 'in',
            value: ['Saturday', 'Sunday'],
            description: 'Weekend day',
          },
          {
            id: 'cond_005b',
            field: 'transferAmountUSD',
            operator: 'gte',
            value: 5000,
            description: 'Amount >= $5,000',
          },
        ],
        action: PolicyAction.DELAY,
        actionParams: {
          delayMinutes: 120,
          message: 'Weekend transfers over $5,000 are delayed by 2 hours.',
        },
      },
    ],
    createdBy: 'admin_002',
    createdAt: '2024-03-01T10:00:00Z',
    stats: {
      evaluations: 0,
      triggers: 0,
    },
  },
];

// ═══════════════════════════════════════════════════════════════════════════════
// API FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

export async function getPolicies(status?: PolicyStatus): Promise<Policy[]> {
  // In production, would fetch from backend
  await new Promise(resolve => setTimeout(resolve, 300));
  
  if (status) {
    return MOCK_POLICIES.filter(p => p.status === status);
  }
  return [...MOCK_POLICIES];
}

export async function getPolicy(policyId: string): Promise<Policy | null> {
  await new Promise(resolve => setTimeout(resolve, 200));
  return MOCK_POLICIES.find(p => p.id === policyId) || null;
}

export async function createPolicy(
  policy: Omit<Policy, 'id' | 'createdAt' | 'version' | 'stats'>,
  creatorId: string
): Promise<PolicyServiceResult<Policy>> {
  try {
    const newPolicy: Policy = {
      ...policy,
      id: `policy_${Date.now()}`,
      version: '1.0.0',
      createdAt: new Date().toISOString(),
      createdBy: creatorId,
      status: PolicyStatus.DRAFT,
      stats: {
        evaluations: 0,
        triggers: 0,
      },
    };
    
    // Would save to backend
    MOCK_POLICIES.push(newPolicy);
    
    return { success: true, data: newPolicy };
  } catch (error: any) {
    return { success: false, error: error.message };
  }
}

export async function updatePolicy(
  policyId: string,
  updates: Partial<Policy>,
  updaterId: string
): Promise<PolicyServiceResult<Policy>> {
  try {
    const index = MOCK_POLICIES.findIndex(p => p.id === policyId);
    if (index === -1) {
      return { success: false, error: 'Policy not found' };
    }
    
    const policy = MOCK_POLICIES[index];
    const versionParts = policy.version.split('.').map(Number);
    versionParts[2]++; // Increment patch version
    
    const updatedPolicy: Policy = {
      ...policy,
      ...updates,
      version: versionParts.join('.'),
      updatedBy: updaterId,
      updatedAt: new Date().toISOString(),
    };
    
    MOCK_POLICIES[index] = updatedPolicy;
    
    return { success: true, data: updatedPolicy };
  } catch (error: any) {
    return { success: false, error: error.message };
  }
}

export async function activatePolicy(
  policyId: string,
  approverId: string
): Promise<PolicyServiceResult<Policy>> {
  return updatePolicy(policyId, {
    status: PolicyStatus.ACTIVE,
    approvedBy: approverId,
    approvedAt: new Date().toISOString(),
  }, approverId);
}

export async function suspendPolicy(
  policyId: string,
  reason: string,
  suspenderId: string
): Promise<PolicyServiceResult<Policy>> {
  return updatePolicy(policyId, {
    status: PolicyStatus.SUSPENDED,
  }, suspenderId);
}

export async function evaluateTransfer(
  context: PolicyEvaluationContext
): Promise<PolicyEvaluationSummary> {
  const activePolicies = await getPolicies(PolicyStatus.ACTIVE);
  const results: PolicyEvaluationResult[] = [];
  let finalAction = PolicyAction.ALLOW;
  let escrowRequired = false;
  let escrowDuration = 0;
  let approvalRequired = false;
  const approvalRoles: Role[] = [];
  const warnings: string[] = [];
  
  // Evaluate each active policy
  for (const policy of activePolicies) {
    for (const rule of policy.rules) {
      if (!rule.enabled) continue;
      
      let matched = true;
      
      // Check all conditions (AND logic)
      for (const condition of rule.conditions) {
        const fieldValue = (context as any)[condition.field];
        
        switch (condition.operator) {
          case 'eq':
            matched = matched && fieldValue === condition.value;
            break;
          case 'neq':
            matched = matched && fieldValue !== condition.value;
            break;
          case 'gt':
            matched = matched && fieldValue > condition.value;
            break;
          case 'gte':
            matched = matched && fieldValue >= condition.value;
            break;
          case 'lt':
            matched = matched && fieldValue < condition.value;
            break;
          case 'lte':
            matched = matched && fieldValue <= condition.value;
            break;
          case 'in':
            matched = matched && (condition.value as string[]).includes(fieldValue);
            break;
          case 'not_in':
            matched = matched && !(condition.value as string[]).includes(fieldValue);
            break;
          case 'contains':
            matched = matched && String(fieldValue).includes(String(condition.value));
            break;
          case 'regex':
            matched = matched && new RegExp(String(condition.value)).test(String(fieldValue));
            break;
        }
      }
      
      if (matched) {
        results.push({
          policyId: policy.id,
          policyName: policy.name,
          ruleId: rule.id,
          ruleName: rule.name,
          matched: true,
          action: rule.action,
          actionParams: rule.actionParams,
          evaluatedAt: new Date().toISOString(),
        });
        
        // Determine final action (most restrictive wins)
        if (rule.action === PolicyAction.BLOCK) {
          finalAction = PolicyAction.BLOCK;
        } else if (rule.action === PolicyAction.REQUIRE_ESCROW && finalAction !== PolicyAction.BLOCK) {
          escrowRequired = true;
          escrowDuration = Math.max(escrowDuration, rule.actionParams?.escrowDuration || 24);
          finalAction = PolicyAction.REQUIRE_ESCROW;
        } else if (rule.action === PolicyAction.REQUIRE_APPROVAL && finalAction === PolicyAction.ALLOW) {
          approvalRequired = true;
          if (rule.actionParams?.approvalRequired) {
            approvalRoles.push(...rule.actionParams.approvalRequired);
          }
          finalAction = PolicyAction.REQUIRE_APPROVAL;
        }
        
        // Collect warnings
        if (rule.action === PolicyAction.FLAG_FOR_REVIEW) {
          warnings.push(rule.actionParams?.message || `Policy "${policy.name}" flagged this transfer for review.`);
        }
      }
    }
  }
  
  return {
    allowed: finalAction !== PolicyAction.BLOCK,
    finalAction,
    triggeredPolicies: results,
    escrowRequired,
    escrowDuration: escrowRequired ? escrowDuration : undefined,
    approvalRequired,
    approvalRoles: approvalRequired ? [...new Set(approvalRoles)] : undefined,
    warnings,
    evaluatedAt: new Date().toISOString(),
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// REACT HOOK
// ═══════════════════════════════════════════════════════════════════════════════

export interface UsePolicyEngineReturn {
  policies: Policy[];
  activePolicies: Policy[];
  isLoading: boolean;
  error: string | null;
  
  // Actions
  create: (policy: Omit<Policy, 'id' | 'createdAt' | 'version' | 'stats'>) => Promise<PolicyServiceResult<Policy>>;
  update: (policyId: string, updates: Partial<Policy>) => Promise<PolicyServiceResult<Policy>>;
  activate: (policyId: string) => Promise<PolicyServiceResult<Policy>>;
  suspend: (policyId: string, reason: string) => Promise<PolicyServiceResult<Policy>>;
  evaluate: (context: PolicyEvaluationContext) => Promise<PolicyEvaluationSummary>;
  
  // Refresh
  refresh: () => Promise<void>;
}

export function usePolicyEngine(userId: string | null): UsePolicyEngineReturn {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Fetch policies
  const refresh = useCallback(async () => {
    setIsLoading(true);
    try {
      const allPolicies = await getPolicies();
      setPolicies(allPolicies);
      setError(null);
    } catch (e: any) {
      setError(e.message || 'Failed to fetch policies');
    } finally {
      setIsLoading(false);
    }
  }, []);
  
  useEffect(() => {
    refresh();
  }, [refresh]);
  
  // Derived state
  const activePolicies = policies.filter(p => p.status === PolicyStatus.ACTIVE);
  
  // Actions
  const create = useCallback(async (policy: Omit<Policy, 'id' | 'createdAt' | 'version' | 'stats'>) => {
    if (!userId) return { success: false, error: 'Not authenticated' };
    const result = await createPolicy(policy, userId);
    if (result.success) await refresh();
    return result;
  }, [userId, refresh]);
  
  const update = useCallback(async (policyId: string, updates: Partial<Policy>) => {
    if (!userId) return { success: false, error: 'Not authenticated' };
    const result = await updatePolicy(policyId, updates, userId);
    if (result.success) await refresh();
    return result;
  }, [userId, refresh]);
  
  const activate = useCallback(async (policyId: string) => {
    if (!userId) return { success: false, error: 'Not authenticated' };
    const result = await activatePolicy(policyId, userId);
    if (result.success) await refresh();
    return result;
  }, [userId, refresh]);
  
  const suspend = useCallback(async (policyId: string, reason: string) => {
    if (!userId) return { success: false, error: 'Not authenticated' };
    const result = await suspendPolicy(policyId, reason, userId);
    if (result.success) await refresh();
    return result;
  }, [userId, refresh]);
  
  const evaluate = useCallback(async (context: PolicyEvaluationContext) => {
    return evaluateTransfer(context);
  }, []);
  
  return {
    policies,
    activePolicies,
    isLoading,
    error,
    create,
    update,
    activate,
    suspend,
    evaluate,
    refresh,
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// SIMPLE usePolicy HOOK (alias for common use)
// ═══════════════════════════════════════════════════════════════════════════════

import {
  SimulationResult,
  TransferContext,
  RiskLevel,
} from '@/types/policy-engine';

export interface UsePolicyReturn {
  // Data
  policies: Policy[];
  isLoading: boolean;
  
  // Simulation
  simulateTransfer: (context: TransferContext) => Promise<SimulationResult>;
  isSimulating: boolean;
  
  // CRUD Operations
  createPolicy: (policy: Omit<Policy, 'id' | 'createdAt' | 'updatedAt' | 'createdBy' | 'version'>) => Promise<void>;
  updatePolicy: (id: string, updates: Partial<Policy>) => Promise<void>;
  togglePolicy: (id: string, active: boolean) => Promise<void>;
  deletePolicy: (id: string) => Promise<void>;
}

export function usePolicy(): UsePolicyReturn {
  const [policies, setPolicies] = useState<Policy[]>(MOCK_POLICIES);
  const [isLoading, setIsLoading] = useState(false);
  const [isSimulating, setIsSimulating] = useState(false);

  const simulateTransfer = useCallback(async (context: TransferContext): Promise<SimulationResult> => {
    setIsSimulating(true);
    try {
      // Simulate delay for API call
      await new Promise(resolve => setTimeout(resolve, 500));
      
      // Mock simulation logic
      const amount = context.amount;
      let riskLevel = RiskLevel.LOW;
      let action = PolicyAction.ALLOW;
      const triggeredPolicies: string[] = [];
      const reasons: string[] = [];
      
      if (amount > 100000) {
        riskLevel = RiskLevel.CRITICAL;
        action = PolicyAction.BLOCK;
        triggeredPolicies.push('High Value Transfer Limit');
        reasons.push('Transfer exceeds maximum allowed amount');
      } else if (amount > 50000) {
        riskLevel = RiskLevel.HIGH;
        action = PolicyAction.REQUIRE_APPROVAL;
        triggeredPolicies.push('High Value Transfer Escrow');
        reasons.push('Transfer requires multi-sig approval');
      } else if (amount > 10000) {
        riskLevel = RiskLevel.MEDIUM;
        action = PolicyAction.FLAG;
        triggeredPolicies.push('Velocity Check');
        reasons.push('Transfer flagged for review');
      }
      
      return {
        allowed: action === PolicyAction.ALLOW || action === PolicyAction.FLAG,
        action,
        riskLevel,
        triggeredPolicies,
        reasons,
        estimatedDelay: action === PolicyAction.REQUIRE_APPROVAL ? 24 : 0,
        requiredApprovers: action === PolicyAction.REQUIRE_APPROVAL ? ['R5 Admin', 'R6 Super Admin'] : undefined,
      };
    } finally {
      setIsSimulating(false);
    }
  }, []);

  const createPolicy = useCallback(async (policy: Omit<Policy, 'id' | 'createdAt' | 'updatedAt' | 'createdBy' | 'version'>) => {
    setIsLoading(true);
    try {
      await new Promise(resolve => setTimeout(resolve, 300));
      const newPolicy: Policy = {
        ...policy,
        id: `policy_${Date.now()}`,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        createdBy: 'current_user',
        version: '1.0.0',
      };
      setPolicies(prev => [...prev, newPolicy]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const updatePolicy = useCallback(async (id: string, updates: Partial<Policy>) => {
    setIsLoading(true);
    try {
      await new Promise(resolve => setTimeout(resolve, 300));
      setPolicies(prev => prev.map(p => {
        if (p.id === id) {
          const currentVersion = p.version || '1.0.0';
          const versionParts = currentVersion.split('.').map(Number);
          versionParts[2] = (versionParts[2] || 0) + 1;
          const newVersion = versionParts.join('.');
          return { ...p, ...updates, updatedAt: new Date().toISOString(), version: newVersion };
        }
        return p;
      }));
    } finally {
      setIsLoading(false);
    }
  }, []);

  const togglePolicy = useCallback(async (id: string, active: boolean) => {
    setIsLoading(true);
    try {
      await new Promise(resolve => setTimeout(resolve, 300));
      setPolicies(prev => prev.map(p => 
        p.id === id 
          ? { ...p, status: active ? PolicyStatus.ACTIVE : PolicyStatus.SUSPENDED, updatedAt: new Date().toISOString() }
          : p
      ));
    } finally {
      setIsLoading(false);
    }
  }, []);

  const deletePolicy = useCallback(async (id: string) => {
    setIsLoading(true);
    try {
      await new Promise(resolve => setTimeout(resolve, 300));
      setPolicies(prev => prev.filter(p => p.id !== id));
    } finally {
      setIsLoading(false);
    }
  }, []);

  return {
    policies,
    isLoading,
    simulateTransfer,
    isSimulating,
    createPolicy,
    updatePolicy,
    togglePolicy,
    deletePolicy,
  };
}