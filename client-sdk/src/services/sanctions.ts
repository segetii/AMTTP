/**
 * Sanctions Service - OFAC/EU/UN Sanctions Screening
 * 
 * Provides comprehensive sanctions screening against multiple lists
 * including OFAC SDN, EU Consolidated, UN Security Council, and
 * HMT (UK Treasury) sanctions lists.
 */

import { AxiosInstance } from 'axios';
import { BaseService } from './base';
import { EventEmitter } from '../events';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export type MatchType = 'address' | 'name' | 'fuzzy_name' | 'alias';

export interface SanctionedEntity {
  id: string;
  name: string;
  aliases?: string[];
  source_list: string;
  sanctions_type: string;
  country?: string;
  listed_date?: string;
  addresses?: string[];
  programs?: string[];
}

export interface SanctionsMatch {
  match_type: MatchType;
  confidence: number;
  entity?: SanctionedEntity;
  matched_field?: string;
  matched_value?: string;
}

export interface SanctionsCheckRequest {
  address?: string;
  name?: string;
  country?: string;
  include_fuzzy?: boolean;
  threshold?: number;
}

export interface SanctionsCheckResponse {
  query: SanctionsCheckRequest;
  is_sanctioned: boolean;
  matches: SanctionsMatch[];
  check_timestamp: string;
  lists_checked: string[];
  processing_time_ms: number;
}

export interface BatchCheckRequest {
  addresses: string[];
  include_fuzzy?: boolean;
}

export interface BatchCheckResult {
  address: string;
  is_sanctioned: boolean;
  matches: SanctionsMatch[];
}

export interface BatchCheckResponse {
  results: BatchCheckResult[];
  total_checked: number;
  total_sanctioned: number;
  check_timestamp: string;
}

export interface SanctionsStats {
  total_entities: number;
  indexed_names: number;
  indexed_addresses: number;
  indexed_countries: number;
  hardcoded_crypto_addresses: number;
  last_refresh: Record<string, string>;
  load_timestamp: string;
}

export interface SanctionsList {
  id: string;
  name: string;
  source: string;
  entity_count: number;
  last_updated: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SERVICE
// ═══════════════════════════════════════════════════════════════════════════════

export class SanctionsService extends BaseService {
  private readonly baseUrl: string;

  constructor(http: AxiosInstance, events: EventEmitter, baseUrl = 'http://localhost:8004') {
    super(http, events);
    this.baseUrl = baseUrl;
  }

  /**
   * Check an address or name against sanctions lists
   */
  async check(request: SanctionsCheckRequest): Promise<SanctionsCheckResponse> {
    const response = await this.http.post<SanctionsCheckResponse>(
      `${this.baseUrl}/sanctions/check`,
      request
    );
    
    this.events.emit('sanctions:checked', response.data);
    
    if (response.data.is_sanctioned && response.data.matches.length > 0) {
      const entity = response.data.matches[0].entity;
      if (entity) {
        this.events.emit('sanctions:match', request.address || '', entity.source_list);
      }
    }
    
    return response.data;
  }

  /**
   * Check multiple addresses in batch
   */
  async batchCheck(request: BatchCheckRequest): Promise<BatchCheckResponse> {
    const response = await this.http.post<BatchCheckResponse>(
      `${this.baseUrl}/sanctions/batch-check`,
      request
    );
    return response.data;
  }

  /**
   * Check if an address is on any crypto-specific sanctions list
   * (e.g., Tornado Cash, Lazarus Group addresses)
   */
  async checkCryptoAddress(address: string): Promise<SanctionsCheckResponse> {
    return this.check({
      address: address.toLowerCase(),
      include_fuzzy: false,
    });
  }

  /**
   * Check a name with fuzzy matching for PEP/sanctions
   */
  async checkName(name: string, threshold = 0.85): Promise<SanctionsCheckResponse> {
    return this.check({
      name,
      include_fuzzy: true,
      threshold,
    });
  }

  /**
   * Refresh sanctions lists from sources
   */
  async refresh(): Promise<{ status: string; message: string }> {
    const response = await this.http.post(`${this.baseUrl}/sanctions/refresh`);
    return response.data;
  }

  /**
   * Get sanctions database statistics
   */
  async getStats(): Promise<SanctionsStats> {
    const response = await this.http.get<SanctionsStats>(`${this.baseUrl}/sanctions/stats`);
    return response.data;
  }

  /**
   * Get list of available sanctions lists
   */
  async getLists(): Promise<SanctionsList[]> {
    const response = await this.http.get<{ lists: SanctionsList[] }>(
      `${this.baseUrl}/sanctions/lists`
    );
    return response.data.lists;
  }

  /**
   * Check service health
   */
  async health(): Promise<{ status: string; service: string; database_stats: SanctionsStats }> {
    const response = await this.http.get(`${this.baseUrl}/health`);
    return response.data;
  }
}
