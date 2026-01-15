/**
 * MEV Protection Service
 * Provides protection against Maximal Extractable Value attacks
 * Integrates with Flashbots and private mempool services
 */
import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
import { BaseService } from '../services/base';
export type MEVProtectionLevel = 'none' | 'basic' | 'enhanced' | 'maximum';
export interface MEVConfig {
    enabled: boolean;
    protectionLevel: MEVProtectionLevel;
    flashbotsEnabled: boolean;
    privateMempoolEnabled: boolean;
    maxSlippage: number;
    deadlineMinutes: number;
}
export interface MEVProtectedTransaction {
    id: string;
    originalTx: {
        to: string;
        data: string;
        value: string;
        gasLimit: string;
    };
    protectedTx?: {
        bundleHash?: string;
        privateTxHash?: string;
    };
    status: 'pending' | 'submitted' | 'included' | 'failed';
    protectionType: 'flashbots' | 'private_mempool' | 'none';
    submittedAt?: string;
    includedAt?: string;
    blockNumber?: number;
    savings?: {
        estimatedMEV: string;
        savedAmount: string;
        protectionCost: string;
    };
}
export interface FlashbotsBundle {
    bundleHash: string;
    transactions: string[];
    targetBlock: number;
    status: 'pending' | 'included' | 'failed';
    simulationResult?: {
        success: boolean;
        gasUsed: string;
        profit: string;
    };
}
export interface MEVAnalysis {
    transactionHash?: string;
    vulnerabilities: {
        type: 'sandwich' | 'frontrun' | 'backrun' | 'liquidation';
        risk: 'low' | 'medium' | 'high';
        estimatedLoss: string;
        description: string;
    }[];
    recommendedProtection: MEVProtectionLevel;
    estimatedSavings: string;
}
export declare class MEVProtection extends BaseService {
    private config;
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Get current MEV protection configuration
     */
    getConfig(): MEVConfig;
    /**
     * Update MEV protection configuration
     */
    setConfig(config: Partial<MEVConfig>): void;
    /**
     * Analyze transaction for MEV vulnerabilities
     */
    analyze(transaction: {
        to: string;
        data: string;
        value: string;
        from?: string;
    }): Promise<MEVAnalysis>;
    /**
     * Submit transaction with MEV protection
     */
    submitProtected(transaction: {
        to: string;
        data: string;
        value: string;
        gasLimit: string;
        maxFeePerGas?: string;
        maxPriorityFeePerGas?: string;
        signature: string;
    }): Promise<MEVProtectedTransaction>;
    /**
     * Submit Flashbots bundle
     */
    submitBundle(bundle: {
        signedTransactions: string[];
        targetBlockNumber?: number;
        minTimestamp?: number;
        maxTimestamp?: number;
    }): Promise<FlashbotsBundle>;
    /**
     * Get bundle status
     */
    getBundleStatus(bundleHash: string): Promise<FlashbotsBundle>;
    /**
     * Simulate transaction
     */
    simulate(transaction: {
        to: string;
        data: string;
        value: string;
        from: string;
        gasLimit?: string;
    }): Promise<{
        success: boolean;
        gasUsed: string;
        returnValue: string;
        error?: string;
        logs: any[];
    }>;
    /**
     * Get protected transaction status
     */
    getTransactionStatus(id: string): Promise<MEVProtectedTransaction>;
    /**
     * Get transaction history with MEV protection
     */
    getHistory(options?: {
        address?: string;
        status?: string;
        limit?: number;
        offset?: number;
    }): Promise<{
        transactions: MEVProtectedTransaction[];
        total: number;
        totalSavings: string;
    }>;
    /**
     * Cancel pending protected transaction
     */
    cancel(id: string): Promise<{
        cancelled: boolean;
        reason?: string;
    }>;
    /**
     * Get MEV statistics
     */
    getStatistics(): Promise<{
        totalProtectedTransactions: number;
        totalSavings: string;
        averageSavingsPerTx: string;
        byProtectionType: Record<string, number>;
        successRate: number;
    }>;
    /**
     * Check if Flashbots relay is available
     */
    checkFlashbotsStatus(): Promise<{
        available: boolean;
        relayUrl: string;
        latestBlock: number;
        bundlePendingCount: number;
    }>;
    /**
     * Get recommended gas settings for protected transaction
     */
    getGasRecommendation(): Promise<{
        baseFee: string;
        maxPriorityFee: string;
        maxFee: string;
        estimatedConfirmationTime: number;
    }>;
}
//# sourceMappingURL=protection.d.ts.map