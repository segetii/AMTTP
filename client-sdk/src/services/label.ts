/**
 * Label Service
 * Wraps /label endpoints for address labeling and categorization
 */

import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
import { BaseService } from './base';

export type LabelCategory = 
  | 'exchange'
  | 'defi'
  | 'bridge'
  | 'mixer'
  | 'gambling'
  | 'scam'
  | 'sanctions'
  | 'darknet'
  | 'ransomware'
  | 'theft'
  | 'phishing'
  | 'nft'
  | 'dao'
  | 'custodian'
  | 'payment_processor'
  | 'other';

export type LabelSeverity = 'info' | 'low' | 'medium' | 'high' | 'critical';

export interface AddressLabel {
  id: string;
  address: string;
  label: string;
  category: LabelCategory;
  severity: LabelSeverity;
  confidence: number;
  source: string;
  description?: string;
  metadata?: Record<string, any>;
  createdAt: string;
  updatedAt: string;
  expiresAt?: string;
  verified: boolean;
}

export interface LabelSearchResult {
  address: string;
  labels: AddressLabel[];
  riskImplication: 'safe' | 'caution' | 'warning' | 'danger';
  aggregatedSeverity: LabelSeverity;
}

export interface LabelStatistics {
  totalLabels: number;
  byCategory: Record<LabelCategory, number>;
  bySeverity: Record<LabelSeverity, number>;
  bySource: Record<string, number>;
  recentlyAdded: number;
  recentlyUpdated: number;
}

export class LabelService extends BaseService {
  constructor(http: AxiosInstance, events: EventEmitter) {
    super(http, events);
  }

  /**
   * Get labels for an address
   */
  async getLabels(address: string): Promise<LabelSearchResult> {
    const response = await this.http.get<LabelSearchResult>(`/label/${address}`);
    return response.data;
  }

  /**
   * Check if address has specific label categories
   */
  async hasLabels(address: string, categories?: LabelCategory[]): Promise<{
    hasLabels: boolean;
    matchedCategories: LabelCategory[];
    highestSeverity?: LabelSeverity;
  }> {
    const params = new URLSearchParams();
    if (categories) categories.forEach(c => params.append('categories', c));

    const response = await this.http.get(`/label/${address}/check?${params.toString()}`);
    return response.data;
  }

  /**
   * Batch check multiple addresses
   */
  async batchCheck(addresses: string[], options?: {
    categories?: LabelCategory[];
    minSeverity?: LabelSeverity;
  }): Promise<{
    results: {
      address: string;
      hasLabels: boolean;
      labels: AddressLabel[];
      riskImplication: string;
    }[];
    processedCount: number;
  }> {
    const response = await this.http.post('/label/batch', {
      addresses,
      ...options
    });
    return response.data;
  }

  /**
   * Add a label to an address
   */
  async addLabel(label: {
    address: string;
    label: string;
    category: LabelCategory;
    severity: LabelSeverity;
    confidence?: number;
    description?: string;
    metadata?: Record<string, any>;
    expiresAt?: string;
  }): Promise<AddressLabel> {
    const response = await this.http.post<AddressLabel>('/label', label);
    return response.data;
  }

  /**
   * Update a label
   */
  async updateLabel(id: string, updates: Partial<{
    label: string;
    category: LabelCategory;
    severity: LabelSeverity;
    confidence: number;
    description: string;
    metadata: Record<string, any>;
    expiresAt: string;
    verified: boolean;
  }>): Promise<AddressLabel> {
    const response = await this.http.put<AddressLabel>(`/label/${id}`, updates);
    return response.data;
  }

  /**
   * Remove a label
   */
  async removeLabel(id: string): Promise<void> {
    await this.http.delete(`/label/${id}`);
  }

  /**
   * Verify a label
   */
  async verifyLabel(id: string, verified: boolean, verifiedBy: string): Promise<AddressLabel> {
    const response = await this.http.post<AddressLabel>(`/label/${id}/verify`, {
      verified,
      verifiedBy
    });
    return response.data;
  }

  /**
   * Search labels
   */
  async search(options?: {
    query?: string;
    category?: LabelCategory;
    severity?: LabelSeverity;
    source?: string;
    verified?: boolean;
    limit?: number;
    offset?: number;
  }): Promise<{
    labels: AddressLabel[];
    total: number;
  }> {
    const params = new URLSearchParams();
    if (options?.query) params.append('query', options.query);
    if (options?.category) params.append('category', options.category);
    if (options?.severity) params.append('severity', options.severity);
    if (options?.source) params.append('source', options.source);
    if (options?.verified !== undefined) params.append('verified', options.verified.toString());
    if (options?.limit) params.append('limit', options.limit.toString());
    if (options?.offset) params.append('offset', options.offset.toString());

    const response = await this.http.get<{
      labels: AddressLabel[];
      total: number;
    }>(`/label/search?${params.toString()}`);

    return response.data;
  }

  /**
   * Get label categories with descriptions
   */
  async getCategories(): Promise<{
    categories: {
      id: LabelCategory;
      name: string;
      description: string;
      defaultSeverity: LabelSeverity;
      riskWeight: number;
    }[];
  }> {
    const response = await this.http.get('/label/categories');
    return response.data;
  }

  /**
   * Get label sources
   */
  async getSources(): Promise<{
    sources: {
      id: string;
      name: string;
      description: string;
      reliability: number;
      labelCount: number;
    }[];
  }> {
    const response = await this.http.get('/label/sources');
    return response.data;
  }

  /**
   * Get label statistics
   */
  async getStatistics(): Promise<LabelStatistics> {
    const response = await this.http.get<LabelStatistics>('/label/statistics');
    return response.data;
  }

  /**
   * Get label history for an address
   */
  async getHistory(address: string, options?: {
    limit?: number;
    offset?: number;
  }): Promise<{
    history: {
      action: 'added' | 'updated' | 'removed';
      label: AddressLabel;
      timestamp: string;
      actor?: string;
    }[];
    total: number;
  }> {
    const params = new URLSearchParams();
    if (options?.limit) params.append('limit', options.limit.toString());
    if (options?.offset) params.append('offset', options.offset.toString());

    const response = await this.http.get(`/label/${address}/history?${params.toString()}`);
    return response.data;
  }

  /**
   * Report a label (for moderation)
   */
  async reportLabel(id: string, report: {
    reason: string;
    details?: string;
    reportedBy: string;
  }): Promise<{ reported: boolean; reportId: string }> {
    const response = await this.http.post(`/label/${id}/report`, report);
    return response.data;
  }

  /**
   * Get risky label categories that should trigger blocking
   */
  async getBlockingCategories(): Promise<LabelCategory[]> {
    const response = await this.http.get<{ categories: LabelCategory[] }>('/label/blocking-categories');
    return response.data.categories;
  }
}
