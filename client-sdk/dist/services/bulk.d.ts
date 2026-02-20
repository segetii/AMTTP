/**
 * Bulk Scoring Service
 * Wraps /bulk endpoints for batch transaction scoring
 */
import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
import { BaseService } from './base';
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';
export interface BulkScoringRequest {
    transactions: BulkTransaction[];
    options?: {
        includeLabels?: boolean;
        includeFactors?: boolean;
        parallelism?: number;
        timeout?: number;
    };
}
export interface BulkTransaction {
    id: string;
    from: string;
    to: string;
    amount: string;
    tokenAddress?: string;
    chainId?: number;
    metadata?: Record<string, any>;
}
export interface BulkScoringResult {
    jobId: string;
    status: 'pending' | 'processing' | 'completed' | 'failed';
    results: TransactionScoreResult[];
    processedCount: number;
    failedCount: number;
    failures: {
        id: string;
        error: string;
    }[];
    startedAt: string;
    completedAt?: string;
    processingTimeMs?: number;
}
export interface TransactionScoreResult {
    id: string;
    from: string;
    to: string;
    riskScore: number;
    riskLevel: RiskLevel;
    fromRisk: {
        score: number;
        level: RiskLevel;
    };
    toRisk: {
        score: number;
        level: RiskLevel;
    };
    labels?: {
        address: string;
        labels: string[];
    }[];
    factors?: {
        name: string;
        weight: number;
        value: number;
    }[];
    allowed: boolean;
    reason?: string;
}
export interface BulkJobStatus {
    jobId: string;
    status: 'pending' | 'processing' | 'completed' | 'failed';
    progress: number;
    processedCount: number;
    totalCount: number;
    estimatedTimeRemaining?: number;
    startedAt: string;
    updatedAt: string;
}
export declare class BulkService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Submit bulk scoring request
     */
    submit(request: BulkScoringRequest): Promise<{
        jobId: string;
        status: string;
        estimatedCompletionTime: string;
    }>;
    /**
     * Submit and wait for results (synchronous for small batches)
     */
    score(request: BulkScoringRequest): Promise<BulkScoringResult>;
    /**
     * Get job status
     */
    getStatus(jobId: string): Promise<BulkJobStatus>;
    /**
     * Get job results
     */
    getResults(jobId: string, options?: {
        limit?: number;
        offset?: number;
        status?: 'success' | 'failed';
    }): Promise<{
        results: TransactionScoreResult[];
        total: number;
        hasMore: boolean;
    }>;
    /**
     * Cancel a bulk job
     */
    cancel(jobId: string): Promise<{
        cancelled: boolean;
        processedBeforeCancel: number;
    }>;
    /**
     * Get job history
     */
    getHistory(options?: {
        limit?: number;
        offset?: number;
        status?: string;
        startDate?: Date;
        endDate?: Date;
    }): Promise<{
        jobs: BulkJobStatus[];
        total: number;
    }>;
    /**
     * Get bulk scoring statistics
     */
    getStatistics(): Promise<{
        totalJobs: number;
        totalTransactionsProcessed: number;
        averageProcessingTime: number;
        successRate: number;
        byStatus: Record<string, number>;
    }>;
    /**
     * Download results as CSV
     */
    downloadResults(jobId: string): Promise<Blob>;
    /**
     * Retry failed transactions in a job
     */
    retryFailed(jobId: string): Promise<{
        newJobId: string;
        transactionsToRetry: number;
    }>;
}
//# sourceMappingURL=bulk.d.ts.map