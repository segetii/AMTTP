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

export class MEVProtection extends BaseService {
  private config: MEVConfig = {
    enabled: true,
    protectionLevel: 'enhanced',
    flashbotsEnabled: true,
    privateMempoolEnabled: true,
    maxSlippage: 0.5,
    deadlineMinutes: 20
  };

  constructor(http: AxiosInstance, events: EventEmitter) {
    super(http, events);
  }

  /**
   * Get current MEV protection configuration
   */
  getConfig(): MEVConfig {
    return { ...this.config };
  }

  /**
   * Update MEV protection configuration
   */
  setConfig(config: Partial<MEVConfig>): void {
    this.config = { ...this.config, ...config };
  }

  /**
   * Analyze transaction for MEV vulnerabilities
   */
  async analyze(transaction: {
    to: string;
    data: string;
    value: string;
    from?: string;
  }): Promise<MEVAnalysis> {
    const response = await this.http.post<MEVAnalysis>('/mev/analyze', transaction);
    return response.data;
  }

  /**
   * Submit transaction with MEV protection
   */
  async submitProtected(transaction: {
    to: string;
    data: string;
    value: string;
    gasLimit: string;
    maxFeePerGas?: string;
    maxPriorityFeePerGas?: string;
    signature: string;
  }): Promise<MEVProtectedTransaction> {
    const response = await this.http.post<MEVProtectedTransaction>('/mev/submit', {
      transaction,
      config: this.config
    });
    return response.data;
  }

  /**
   * Submit Flashbots bundle
   */
  async submitBundle(bundle: {
    signedTransactions: string[];
    targetBlockNumber?: number;
    minTimestamp?: number;
    maxTimestamp?: number;
  }): Promise<FlashbotsBundle> {
    const response = await this.http.post<FlashbotsBundle>('/mev/bundle', bundle);
    return response.data;
  }

  /**
   * Get bundle status
   */
  async getBundleStatus(bundleHash: string): Promise<FlashbotsBundle> {
    const response = await this.http.get<FlashbotsBundle>(`/mev/bundle/${bundleHash}`);
    return response.data;
  }

  /**
   * Simulate transaction
   */
  async simulate(transaction: {
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
  }> {
    const response = await this.http.post('/mev/simulate', transaction);
    return response.data;
  }

  /**
   * Get protected transaction status
   */
  async getTransactionStatus(id: string): Promise<MEVProtectedTransaction> {
    const response = await this.http.get<MEVProtectedTransaction>(`/mev/transaction/${id}`);
    return response.data;
  }

  /**
   * Get transaction history with MEV protection
   */
  async getHistory(options?: {
    address?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<{
    transactions: MEVProtectedTransaction[];
    total: number;
    totalSavings: string;
  }> {
    const params = new URLSearchParams();
    if (options?.address) params.append('address', options.address);
    if (options?.status) params.append('status', options.status);
    if (options?.limit) params.append('limit', options.limit.toString());
    if (options?.offset) params.append('offset', options.offset.toString());

    const response = await this.http.get(`/mev/history?${params.toString()}`);
    return response.data;
  }

  /**
   * Cancel pending protected transaction
   */
  async cancel(id: string): Promise<{
    cancelled: boolean;
    reason?: string;
  }> {
    const response = await this.http.post(`/mev/transaction/${id}/cancel`);
    return response.data;
  }

  /**
   * Get MEV statistics
   */
  async getStatistics(): Promise<{
    totalProtectedTransactions: number;
    totalSavings: string;
    averageSavingsPerTx: string;
    byProtectionType: Record<string, number>;
    successRate: number;
  }> {
    const response = await this.http.get('/mev/statistics');
    return response.data;
  }

  /**
   * Check if Flashbots relay is available
   */
  async checkFlashbotsStatus(): Promise<{
    available: boolean;
    relayUrl: string;
    latestBlock: number;
    bundlePendingCount: number;
  }> {
    const response = await this.http.get('/mev/flashbots/status');
    return response.data;
  }

  /**
   * Get recommended gas settings for protected transaction
   */
  async getGasRecommendation(): Promise<{
    baseFee: string;
    maxPriorityFee: string;
    maxFee: string;
    estimatedConfirmationTime: number;
  }> {
    const response = await this.http.get('/mev/gas-recommendation');
    return response.data;
  }
}
