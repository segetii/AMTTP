/**
 * Transaction Service
 * Wraps /tx endpoints for transaction management
 */

import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
import { BaseService } from './base';

// Local type definitions
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

export class TransactionService extends BaseService {
  constructor(http: AxiosInstance, events: EventEmitter) {
    super(http, events);
  }

  /**
   * Validate a transaction before submission
   */
  async validate(request: TransactionRequest): Promise<TransactionValidation> {
    const response = await this.http.post<TransactionValidation>('/tx/validate', request);
    
    this.events.emit('transaction:validated', {
      from: request.from,
      to: request.to,
      valid: response.data.valid,
      riskLevel: response.data.riskLevel
    });

    return response.data;
  }

  /**
   * Submit a transaction for processing
   */
  async submit(request: TransactionRequest): Promise<TransactionRecord> {
    const response = await this.http.post<TransactionRecord>('/tx/submit', request);
    
    this.events.emit('transaction:submitted', {
      id: response.data.id,
      from: request.from,
      to: request.to,
      status: response.data.status
    });

    return response.data;
  }

  /**
   * Get transaction by ID
   */
  async get(id: string): Promise<TransactionRecord> {
    const response = await this.http.get<TransactionRecord>(`/tx/${id}`);
    return response.data;
  }

  /**
   * Get transaction by hash
   */
  async getByHash(hash: string): Promise<TransactionRecord> {
    const response = await this.http.get<TransactionRecord>(`/tx/hash/${hash}`);
    return response.data;
  }

  /**
   * Get transaction history
   */
  async getHistory(options?: TransactionHistoryOptions): Promise<{
    transactions: TransactionRecord[];
    total: number;
    hasMore: boolean;
  }> {
    const params = new URLSearchParams();
    if (options?.address) params.append('address', options.address);
    if (options?.status) params.append('status', options.status);
    if (options?.startDate) params.append('startDate', options.startDate.toISOString());
    if (options?.endDate) params.append('endDate', options.endDate.toISOString());
    if (options?.limit) params.append('limit', options.limit.toString());
    if (options?.offset) params.append('offset', options.offset.toString());
    if (options?.sortBy) params.append('sortBy', options.sortBy);
    if (options?.sortOrder) params.append('sortOrder', options.sortOrder);

    const response = await this.http.get<{
      transactions: TransactionRecord[];
      total: number;
      hasMore: boolean;
    }>(`/tx/history?${params.toString()}`);

    return response.data;
  }

  /**
   * Cancel a pending transaction
   */
  async cancel(id: string, reason?: string): Promise<TransactionRecord> {
    const response = await this.http.post<TransactionRecord>(`/tx/${id}/cancel`, { reason });
    
    this.events.emit('transaction:cancelled', { id, reason });

    return response.data;
  }

  /**
   * Retry a failed transaction
   */
  async retry(id: string): Promise<TransactionRecord> {
    const response = await this.http.post<TransactionRecord>(`/tx/${id}/retry`);
    
    this.events.emit('transaction:retried', { id });

    return response.data;
  }

  /**
   * Get transaction status updates
   */
  async getStatusUpdates(id: string): Promise<{
    updates: {
      status: TransactionStatus;
      timestamp: string;
      message?: string;
    }[];
  }> {
    const response = await this.http.get(`/tx/${id}/status-updates`);
    return response.data;
  }

  /**
   * Request expedited processing
   */
  async expedite(id: string): Promise<{
    success: boolean;
    estimatedCompletionTime?: string;
    additionalFee?: string;
  }> {
    const response = await this.http.post(`/tx/${id}/expedite`);
    return response.data;
  }

  /**
   * Get transaction receipt
   */
  async getReceipt(id: string): Promise<{
    transactionHash: string;
    blockNumber: number;
    blockHash: string;
    gasUsed: string;
    effectiveGasPrice: string;
    status: boolean;
    logs: any[];
  }> {
    const response = await this.http.get(`/tx/${id}/receipt`);
    return response.data;
  }

  /**
   * Estimate transaction cost
   */
  async estimateCost(request: TransactionRequest): Promise<{
    gasEstimate: string;
    gasPriceWei: string;
    totalCostWei: string;
    totalCostEth: string;
    totalCostUsd?: string;
  }> {
    const response = await this.http.post('/tx/estimate', request);
    return response.data;
  }

  /**
   * Get pending transactions for an address
   */
  async getPending(address: string): Promise<TransactionRecord[]> {
    const response = await this.http.get<{ transactions: TransactionRecord[] }>(
      `/tx/pending/${address}`
    );
    return response.data.transactions;
  }
}
