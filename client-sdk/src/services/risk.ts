/**
 * Risk Assessment Service
 * Wraps /risk endpoints for transaction risk scoring
 */

import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
import { BaseService } from './base';

// Local type definitions to avoid circular imports
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

export interface LabelInfo {
  label: string;
  category: string;
  severity: string;
  source: string;
}

export interface RiskScore {
  address: string;
  score: number;
  level: RiskLevel;
  timestamp: string;
  expiresAt: string;
}

export interface RiskAssessmentRequest {
  address: string;
  transactionHash?: string;
  amount?: string;
  counterparty?: string;
  metadata?: Record<string, any>;
}

export interface RiskAssessmentResponse {
  address: string;
  riskScore: number;
  riskLevel: RiskLevel;
  factors: RiskFactor[];
  labels: LabelInfo[];
  timestamp: string;
  expiresAt: string;
  cached: boolean;
}

export interface RiskFactor {
  name: string;
  weight: number;
  value: number;
  description: string;
}

export interface BatchRiskRequest {
  addresses: string[];
  includeLabels?: boolean;
  includeFactors?: boolean;
}

export interface BatchRiskResponse {
  results: RiskAssessmentResponse[];
  processedCount: number;
  failedCount: number;
  failures: { address: string; error: string }[];
}

export interface RiskThreshold {
  level: RiskLevel;
  minScore: number;
  maxScore: number;
  action: 'allow' | 'review' | 'block';
}

export class RiskService extends BaseService {
  constructor(http: AxiosInstance, events: EventEmitter) {
    super(http, events);
  }

  /**
   * Assess risk for a single address
   */
  async assess(request: RiskAssessmentRequest): Promise<RiskAssessmentResponse> {
    const response = await this.http.post<RiskAssessmentResponse>('/risk/assess', request);
    
    this.events.emit('risk:assessed', {
      address: request.address,
      riskLevel: response.data.riskLevel,
      riskScore: response.data.riskScore
    });

    return response.data;
  }

  /**
   * Get cached risk score for an address
   */
  async getScore(address: string): Promise<RiskScore | null> {
    try {
      const response = await this.http.get<RiskScore>(`/risk/score/${address}`);
      return response.data;
    } catch (error: any) {
      if (error.response?.status === 404) {
        return null;
      }
      throw error;
    }
  }

  /**
   * Batch assess multiple addresses
   */
  async batchAssess(request: BatchRiskRequest): Promise<BatchRiskResponse> {
    const response = await this.http.post<BatchRiskResponse>('/risk/batch', request);
    
    this.events.emit('risk:batchCompleted', {
      processedCount: response.data.processedCount,
      failedCount: response.data.failedCount
    });

    return response.data;
  }

  /**
   * Get risk thresholds configuration
   */
  async getThresholds(): Promise<RiskThreshold[]> {
    const response = await this.http.get<{ thresholds: RiskThreshold[] }>('/risk/thresholds');
    return response.data.thresholds;
  }

  /**
   * Check if address passes risk threshold
   */
  async checkThreshold(address: string, maxRiskLevel: RiskLevel = 'medium'): Promise<{
    passed: boolean;
    riskScore: number;
    riskLevel: RiskLevel;
    action: 'allow' | 'review' | 'block';
  }> {
    const response = await this.http.post<{
      passed: boolean;
      riskScore: number;
      riskLevel: RiskLevel;
      action: 'allow' | 'review' | 'block';
    }>('/risk/check-threshold', { address, maxRiskLevel });
    
    return response.data;
  }

  /**
   * Get risk history for an address
   */
  async getHistory(address: string, options?: {
    limit?: number;
    offset?: number;
    startDate?: Date;
    endDate?: Date;
  }): Promise<{
    history: RiskAssessmentResponse[];
    total: number;
  }> {
    const params = new URLSearchParams();
    if (options?.limit) params.append('limit', options.limit.toString());
    if (options?.offset) params.append('offset', options.offset.toString());
    if (options?.startDate) params.append('startDate', options.startDate.toISOString());
    if (options?.endDate) params.append('endDate', options.endDate.toISOString());

    const response = await this.http.get<{
      history: RiskAssessmentResponse[];
      total: number;
    }>(`/risk/history/${address}?${params.toString()}`);

    return response.data;
  }

  /**
   * Invalidate cached risk score
   */
  async invalidateCache(address: string): Promise<void> {
    await this.http.delete(`/risk/cache/${address}`);
    this.events.emit('risk:cacheInvalidated', { address });
  }

  /**
   * Get risk factors configuration
   */
  async getFactors(): Promise<{
    factors: {
      name: string;
      weight: number;
      description: string;
      enabled: boolean;
    }[];
  }> {
    const response = await this.http.get('/risk/factors');
    return response.data;
  }
}
