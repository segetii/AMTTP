import { ethers } from 'ethers';
export interface AMTTPConfig {
    rpcUrl: string;
    contractAddress: string;
    oracleUrl: string;
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
}
export interface RiskScore {
    riskScore: number;
    riskCategory: 'MINIMAL' | 'LOW' | 'MEDIUM' | 'HIGH';
    confidence: number;
    recommendations: string[];
    modelVersion: string;
    f1Score?: number;
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