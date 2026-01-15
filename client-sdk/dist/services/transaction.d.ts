/**
 * Transaction Service
 * Wraps /tx endpoints for transaction management
 */
import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
import { BaseService } from './base';
export type TransactionStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled';
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';
export interface TransactionRequest {
    from: string;
    to: string;
    amount: string;
    tokenAddress?: string;
    chainId: number;
    memo?: string;
    metadata?: Record<string, any>;
}
export interface TransactionRecord {
    id: string;
    hash?: string;
    from: string;
    to: string;
    amount: string;
    tokenAddress?: string;
    chainId: number;
    status: TransactionStatus;
    riskScore?: number;
    riskLevel?: RiskLevel;
    policyResult?: {
        allowed: boolean;
        reason?: string;
        appliedPolicies: string[];
    };
    createdAt: string;
    updatedAt: string;
    completedAt?: string;
    memo?: string;
}
export interface TransactionValidation {
    valid: boolean;
    riskScore: number;
    riskLevel: RiskLevel;
    policyResult: {
        allowed: boolean;
        reason?: string;
        appliedPolicies: string[];
        requiredApprovals?: number;
    };
    labelWarnings: {
        address: string;
        labels: string[];
        severity: 'low' | 'medium' | 'high' | 'critical';
    }[];
    estimatedGas?: string;
    estimatedFee?: string;
}
export interface TransactionHistoryOptions {
    address?: string;
    status?: TransactionStatus;
    startDate?: Date;
    endDate?: Date;
    limit?: number;
    offset?: number;
    sortBy?: 'createdAt' | 'amount' | 'riskScore';
    sortOrder?: 'asc' | 'desc';
}
export declare class TransactionService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Validate a transaction before submission
     */
    validate(request: TransactionRequest): Promise<TransactionValidation>;
    /**
     * Submit a transaction for processing
     */
    submit(request: TransactionRequest): Promise<TransactionRecord>;
    /**
     * Get transaction by ID
     */
    get(id: string): Promise<TransactionRecord>;
    /**
     * Get transaction by hash
     */
    getByHash(hash: string): Promise<TransactionRecord>;
    /**
     * Get transaction history
     */
    getHistory(options?: TransactionHistoryOptions): Promise<{
        transactions: TransactionRecord[];
        total: number;
        hasMore: boolean;
    }>;
    /**
     * Cancel a pending transaction
     */
    cancel(id: string, reason?: string): Promise<TransactionRecord>;
    /**
     * Retry a failed transaction
     */
    retry(id: string): Promise<TransactionRecord>;
    /**
     * Get transaction status updates
     */
    getStatusUpdates(id: string): Promise<{
        updates: {
            status: TransactionStatus;
            timestamp: string;
            message?: string;
        }[];
    }>;
    /**
     * Request expedited processing
     */
    expedite(id: string): Promise<{
        success: boolean;
        estimatedCompletionTime?: string;
        additionalFee?: string;
    }>;
    /**
     * Get transaction receipt
     */
    getReceipt(id: string): Promise<{
        transactionHash: string;
        blockNumber: number;
        blockHash: string;
        gasUsed: string;
        effectiveGasPrice: string;
        status: boolean;
        logs: any[];
    }>;
    /**
     * Estimate transaction cost
     */
    estimateCost(request: TransactionRequest): Promise<{
        gasEstimate: string;
        gasPriceWei: string;
        totalCostWei: string;
        totalCostEth: string;
        totalCostUsd?: string;
    }>;
    /**
     * Get pending transactions for an address
     */
    getPending(address: string): Promise<TransactionRecord[]>;
}
//# sourceMappingURL=transaction.d.ts.map