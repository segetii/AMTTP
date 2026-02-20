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
  failures: { id: string; error: string }[];
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
  fromRisk: { score: number; level: RiskLevel };
  toRisk: { score: number; level: RiskLevel };
  labels?: { address: string; labels: string[] }[];
  factors?: { name: string; weight: number; value: number }[];
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

export class BulkService extends BaseService {
  constructor(http: AxiosInstance, events: EventEmitter) {
    super(http, events);
  }

  /**
   * Submit bulk scoring request
   */
  async submit(request: BulkScoringRequest): Promise<{
    jobId: string;
    status: string;
    estimatedCompletionTime: string;
  }> {
    const response = await this.http.post<{
      jobId: string;
      status: string;
      estimatedCompletionTime: string;
    }>('/bulk/submit', request);

    return response.data;
  }

  /**
   * Submit and wait for results (synchronous for small batches)
   */
  async score(request: BulkScoringRequest): Promise<BulkScoringResult> {
    const response = await this.http.post<BulkScoringResult>('/bulk/score', request);
    return response.data;
  }

  /**
   * Get job status
   */
  async getStatus(jobId: string): Promise<BulkJobStatus> {
    const response = await this.http.get<BulkJobStatus>(`/bulk/status/${jobId}`);
    return response.data;
  }

  /**
   * Get job results
   */
  async getResults(jobId: string, options?: {
    limit?: number;
    offset?: number;
    status?: 'success' | 'failed';
  }): Promise<{
    results: TransactionScoreResult[];
    total: number;
    hasMore: boolean;
  }> {
    const params = new URLSearchParams();
    if (options?.limit) params.append('limit', options.limit.toString());
    if (options?.offset) params.append('offset', options.offset.toString());
    if (options?.status) params.append('status', options.status);

    const response = await this.http.get<{
      results: TransactionScoreResult[];
      total: number;
      hasMore: boolean;
    }>(`/bulk/results/${jobId}?${params.toString()}`);

    return response.data;
  }

  /**
   * Cancel a bulk job
   */
  async cancel(jobId: string): Promise<{ cancelled: boolean; processedBeforeCancel: number }> {
    const response = await this.http.post(`/bulk/cancel/${jobId}`);
    return response.data;
  }

  /**
   * Get job history
   */
  async getHistory(options?: {
    limit?: number;
    offset?: number;
    status?: string;
    startDate?: Date;
    endDate?: Date;
  }): Promise<{
    jobs: BulkJobStatus[];
    total: number;
  }> {
    const params = new URLSearchParams();
    if (options?.limit) params.append('limit', options.limit.toString());
    if (options?.offset) params.append('offset', options.offset.toString());
    if (options?.status) params.append('status', options.status);
    if (options?.startDate) params.append('startDate', options.startDate.toISOString());
    if (options?.endDate) params.append('endDate', options.endDate.toISOString());

    const response = await this.http.get<{
      jobs: BulkJobStatus[];
      total: number;
    }>(`/bulk/history?${params.toString()}`);

    return response.data;
  }

  /**
   * Get bulk scoring statistics
   */
  async getStatistics(): Promise<{
    totalJobs: number;
    totalTransactionsProcessed: number;
    averageProcessingTime: number;
    successRate: number;
    byStatus: Record<string, number>;
  }> {
    const response = await this.http.get('/bulk/statistics');
    return response.data;
  }

  /**
   * Download results as CSV
   */
  async downloadResults(jobId: string): Promise<Blob> {
    const response = await this.http.get(`/bulk/download/${jobId}`, {
      responseType: 'blob'
    });
    return response.data;
  }

  /**
   * Retry failed transactions in a job
   */
  async retryFailed(jobId: string): Promise<{
    newJobId: string;
    transactionsToRetry: number;
  }> {
    const response = await this.http.post(`/bulk/retry/${jobId}`);
    return response.data;
  }
}
