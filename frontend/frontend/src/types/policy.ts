// Types for Policy Management

export type RiskAction = 'APPROVE' | 'REVIEW' | 'ESCROW' | 'BLOCK';

export interface PolicyThresholds {
  lowRiskMax: number;      // 0-100, scores below this are low risk
  mediumRiskMax: number;   // scores below this are medium risk
  highRiskMax: number;     // scores below this are high risk, above is critical
}

export interface PolicyLimits {
  maxTransactionAmount: string;     // in wei or token units
  dailyLimit: string;               // daily transaction limit
  monthlyLimit: string;             // monthly transaction limit
  maxCounterparties: number;        // max unique addresses per day
}

export interface PolicyRules {
  blockSanctionedAddresses: boolean;
  requireKYCAboveThreshold: boolean;
  kycThresholdAmount: string;
  autoEscrowHighRisk: boolean;
  escrowDurationHours: number;
  allowedChainIds: number[];
  blockedCountries: string[];
}

export interface PolicyActions {
  onLowRisk: RiskAction;
  onMediumRisk: RiskAction;
  onHighRisk: RiskAction;
  onCriticalRisk: RiskAction;
  onSanctionedAddress: RiskAction;
  onUnknownAddress: RiskAction;
}

export interface Policy {
  id: string;
  name: string;
  description: string;
  isActive: boolean;
  isDefault: boolean;
  createdAt: string;
  updatedAt: string;
  createdBy: string;
  
  // Policy configuration
  thresholds: PolicyThresholds;
  limits: PolicyLimits;
  rules: PolicyRules;
  actions: PolicyActions;
  
  // Whitelist/Blacklist
  whitelist: string[];
  blacklist: string[];
  
  // Statistics
  stats: {
    totalTransactions: number;
    approvedCount: number;
    reviewedCount: number;
    escrowedCount: number;
    blockedCount: number;
    lastTriggered?: string;
  };
}

export interface PolicyFormData {
  name: string;
  description: string;
  isActive: boolean;
  thresholds: PolicyThresholds;
  limits: PolicyLimits;
  rules: PolicyRules;
  actions: PolicyActions;
  whitelist: string[];
  blacklist: string[];
}

export interface PolicyValidationResult {
  isValid: boolean;
  errors: Record<string, string>;
}

// Default values for new policies
export const DEFAULT_POLICY: PolicyFormData = {
  name: '',
  description: '',
  isActive: true,
  thresholds: {
    lowRiskMax: 25,
    mediumRiskMax: 50,
    highRiskMax: 75,
  },
  limits: {
    maxTransactionAmount: '1000000000000000000000', // 1000 ETH
    dailyLimit: '10000000000000000000000',          // 10000 ETH
    monthlyLimit: '100000000000000000000000',       // 100000 ETH
    maxCounterparties: 100,
  },
  rules: {
    blockSanctionedAddresses: true,
    requireKYCAboveThreshold: true,
    kycThresholdAmount: '10000000000000000000', // 10 ETH
    autoEscrowHighRisk: true,
    escrowDurationHours: 24,
    allowedChainIds: [1, 137, 42161], // Ethereum, Polygon, Arbitrum
    blockedCountries: [],
  },
  actions: {
    onLowRisk: 'APPROVE',
    onMediumRisk: 'REVIEW',
    onHighRisk: 'ESCROW',
    onCriticalRisk: 'BLOCK',
    onSanctionedAddress: 'BLOCK',
    onUnknownAddress: 'REVIEW',
  },
  whitelist: [],
  blacklist: [],
};
