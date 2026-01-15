import { ethers } from 'ethers';
export interface AMTTPConfig {
    rpcUrl: string;
    contractAddress: string;
    oracleUrl: string;
    mlApiUrl?: string;
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
    velocity24h?: number;
    accountAgeDays?: number;
    countryRisk?: number;
}
export declare enum PolicyAction {
    APPROVE = 0,
    REVIEW = 1,
    ESCROW = 2,
    BLOCK = 3
}
export declare enum RiskLevel {
    MINIMAL = 0,
    LOW = 1,
    MEDIUM = 2,
    HIGH = 3
}
export interface RiskScore {
    riskScore: number;
    riskScoreInt: number;
    riskCategory: 'MINIMAL' | 'LOW' | 'MEDIUM' | 'HIGH';
    riskLevel: RiskLevel;
    action: PolicyAction;
    confidence: number;
    recommendations: string[];
    modelVersion: string;
    featuresHash?: string;
    f1Score?: number;
    modelMetrics?: {
        testAP: number;
        testAUC: number;
        testF1: number;
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
//# sourceMappingURL=types.d.ts.map