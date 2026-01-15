/**
 * PEP Screening Service
 * Wraps /pep endpoints for Politically Exposed Person screening
 */

import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
import { BaseService } from './base';

export interface PEPScreeningRequest {
  address: string;
  fullName?: string;
  dateOfBirth?: string;
  nationality?: string;
  includeRelatives?: boolean;
  includeAssociates?: boolean;
  providers?: string[];
}

export interface PEPMatch {
  id: string;
  name: string;
  matchScore: number;
  matchType: 'exact' | 'fuzzy' | 'partial';
  pepType: 'pep' | 'relative' | 'associate';
  position?: string;
  country?: string;
  dateOfBirth?: string;
  source: string;
  listType: 'sanction' | 'pep' | 'watchlist' | 'adverse_media';
  lastUpdated: string;
  details?: Record<string, any>;
}

export interface PEPScreeningResult {
  address: string;
  screened: boolean;
  matches: PEPMatch[];
  highestMatchScore: number;
  riskLevel: 'clear' | 'low' | 'medium' | 'high' | 'critical';
  requiresEDD: boolean;
  screenedAt: string;
  expiresAt: string;
  providers: string[];
}

export interface PEPHistoryEntry {
  id: string;
  address: string;
  result: PEPScreeningResult;
  triggeredBy: 'manual' | 'automated' | 'transaction';
  performedAt: string;
  performedBy?: string;
}

export class PEPService extends BaseService {
  constructor(http: AxiosInstance, events: EventEmitter) {
    super(http, events);
  }

  /**
   * Screen an address for PEP matches
   */
  async screen(request: PEPScreeningRequest): Promise<PEPScreeningResult> {
    const response = await this.http.post<PEPScreeningResult>('/pep/screen', request);
    return response.data;
  }

  /**
   * Get cached screening result
   */
  async getResult(address: string): Promise<PEPScreeningResult | null> {
    try {
      const response = await this.http.get<PEPScreeningResult>(`/pep/result/${address}`);
      return response.data;
    } catch (error: any) {
      if (error.response?.status === 404) {
        return null;
      }
      throw error;
    }
  }

  /**
   * Check if address has PEP matches
   */
  async hasPEPMatches(address: string): Promise<{
    hasMatches: boolean;
    matchCount: number;
    highestRisk: string;
  }> {
    const response = await this.http.get(`/pep/check/${address}`);
    return response.data;
  }

  /**
   * Get screening history for an address
   */
  async getHistory(address: string, options?: {
    limit?: number;
    offset?: number;
    startDate?: Date;
    endDate?: Date;
  }): Promise<{
    history: PEPHistoryEntry[];
    total: number;
  }> {
    const params = new URLSearchParams();
    if (options?.limit) params.append('limit', options.limit.toString());
    if (options?.offset) params.append('offset', options.offset.toString());
    if (options?.startDate) params.append('startDate', options.startDate.toISOString());
    if (options?.endDate) params.append('endDate', options.endDate.toISOString());

    const response = await this.http.get<{
      history: PEPHistoryEntry[];
      total: number;
    }>(`/pep/history/${address}?${params.toString()}`);

    return response.data;
  }

  /**
   * Batch screen multiple addresses
   */
  async batchScreen(addresses: string[]): Promise<{
    results: PEPScreeningResult[];
    processedCount: number;
    failedCount: number;
  }> {
    const response = await this.http.post<{
      results: PEPScreeningResult[];
      processedCount: number;
      failedCount: number;
    }>('/pep/batch', { addresses });

    return response.data;
  }

  /**
   * Acknowledge a PEP match (mark as reviewed)
   */
  async acknowledgeMatch(address: string, matchId: string, decision: {
    approved: boolean;
    reason: string;
    reviewedBy: string;
  }): Promise<{ acknowledged: boolean }> {
    const response = await this.http.post(`/pep/${address}/matches/${matchId}/acknowledge`, decision);
    return response.data;
  }

  /**
   * Get match details
   */
  async getMatchDetails(address: string, matchId: string): Promise<PEPMatch & {
    fullProfile?: Record<string, any>;
    relatedEntities?: { name: string; relationship: string }[];
  }> {
    const response = await this.http.get(`/pep/${address}/matches/${matchId}`);
    return response.data;
  }

  /**
   * Get available screening providers
   */
  async getProviders(): Promise<{
    providers: {
      id: string;
      name: string;
      description: string;
      coverage: string[];
      enabled: boolean;
    }[];
  }> {
    const response = await this.http.get('/pep/providers');
    return response.data;
  }

  /**
   * Invalidate cached screening result
   */
  async invalidateCache(address: string): Promise<void> {
    await this.http.delete(`/pep/cache/${address}`);
  }

  /**
   * Get PEP screening statistics
   */
  async getStatistics(): Promise<{
    totalScreenings: number;
    matchesFound: number;
    byRiskLevel: Record<string, number>;
    byListType: Record<string, number>;
    averageMatchScore: number;
  }> {
    const response = await this.http.get('/pep/statistics');
    return response.data;
  }

  /**
   * Schedule periodic rescreening
   */
  async scheduleRescreening(address: string, intervalDays: number): Promise<{
    scheduled: boolean;
    nextScreeningAt: string;
  }> {
    const response = await this.http.post(`/pep/${address}/schedule`, { intervalDays });
    return response.data;
  }
}
