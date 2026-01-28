// src/types.ts
import { ethers } from 'ethers';

export interface AMTTPConfig {
  rpcUrl: string;
  contractAddress: string;
  oracleUrl: string;
  mlApiUrl?: string;  // ML inference API URL
  policyEngineContract?: string;
  policyManagerContract?: string;
  privateKey?: string;
  provider?: ethers.Provider;
  signer?: ethers.Signer;
}

export interface TransactionRequest {
  to: string;
  value: bigint;
  data?: string;
  metadata?: TransactionMetadata;
}

export interface TransactionMetadata {
  purpose: string;
  counterparty?: string;
  category?: string;
  description?: string;
  riskOverride?: boolean;
  // ML feature hints
  velocity24h?: number;
  accountAgeDays?: number;
  countryRisk?: number;
}

// Policy action enum matching smart contract
export enum PolicyAction {
  APPROVE = 0,
  REVIEW = 1,
  ESCROW = 2,
  BLOCK = 3
}

// Risk level enum matching smart contract
export enum RiskLevel {
  MINIMAL = 0,
  LOW = 1,
  MEDIUM = 2,
  HIGH = 3
}

export interface RiskScore {
  riskScore: number;          // 0-1 normalized
  riskScoreInt: number;       // 0-1000 for contract
  riskCategory: 'MINIMAL' | 'LOW' | 'MEDIUM' | 'HIGH';
  riskLevel: RiskLevel;
  action: PolicyAction;
  confidence: number;
  recommendations: string[];
  modelVersion: string;
  featuresHash?: string;
  f1Score?: number;
  // Model metrics from validation (time-based test split, days 27-30)
  modelMetrics?: {
    rocAUC: number;      // ~0.94 - Overall discriminative ability
    prAUC: number;       // ~0.87 - Primary metric for imbalanced fraud detection
    f1: number;          // ~0.87 - Balanced precision/recall at default threshold
    architecture: string; // Stacked Ensemble (GraphSAGE + LGBM + XGBoost + Linear Meta-Learner)
  };
}

export interface KYCStatus {
  status: 'approved' | 'pending' | 'rejected' | 'init';
  kycHash: string;
  provider?: string;
}

export interface SwapParams {
  seller: string;
  hashlock: string;
  timelock: number;
  assetType: 'ETH' | 'ERC20' | 'ERC721';
  token?: string;
  tokenId?: string;
  amount: bigint;
}

export interface PolicySettings {
  maxAmount: bigint;
  dailyLimit: bigint;
  allowedCounterparties: string[];
  riskThreshold: number;
  autoApprove: boolean;
}

export interface AMTTPResult {
  success: boolean;
  transactionHash?: string;
  riskScore?: RiskScore;
  swapId?: string;
  error?: string;
  approvalRequired?: boolean;
  estimatedConfirmation?: number;
}