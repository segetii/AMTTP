/**
 * Geographic Risk Service - Country and IP Risk Assessment
 * 
 * Provides geographic risk scoring based on FATF lists,
 * tax haven status, and country-specific regulations.
 */

import { AxiosInstance } from 'axios';
import { BaseService } from './base';
import { EventEmitter } from '../events';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export type RiskLevel = 'PROHIBITED' | 'VERY_HIGH' | 'HIGH' | 'MEDIUM' | 'LOW' | 'MINIMAL';
export type TransactionPolicy = 'BLOCK' | 'REVIEW' | 'ESCROW' | 'ALLOW' | 'ENHANCED_MONITORING';

export interface CountryRiskRequest {
  country_code: string;
}

export interface CountryRiskResponse {
  country_code: string;
  country_name?: string;
  risk_score: number;
  risk_level: RiskLevel;
  risk_factors: string[];
  is_fatf_black_list: boolean;
  is_fatf_grey_list: boolean;
  is_eu_high_risk: boolean;
  is_tax_haven: boolean;
  transaction_policy: TransactionPolicy;
}

export interface IPRiskRequest {
  ip_address: string;
}

export interface IPRiskResponse {
  ip_address: string;
  country_code: string;
  country_name: string;
  city?: string;
  region?: string;
  is_vpn: boolean;
  is_proxy: boolean;
  is_tor: boolean;
  is_datacenter: boolean;
  risk_score: number;
  risk_level: RiskLevel;
  risk_factors: string[];
}

export interface TransactionGeoRiskRequest {
  originator_country: string;
  beneficiary_country: string;
  originator_ip?: string;
  beneficiary_ip?: string;
  value_usd?: number;
}

export interface TransactionGeoRiskResponse {
  originator_country_risk: CountryRiskResponse;
  beneficiary_country_risk: CountryRiskResponse;
  originator_ip_risk?: IPRiskResponse;
  beneficiary_ip_risk?: IPRiskResponse;
  combined_risk_score: number;
  combined_risk_level: RiskLevel;
  transaction_policy: TransactionPolicy;
  requires_enhanced_due_diligence: boolean;
  requires_travel_rule: boolean;
  risk_factors: string[];
}

export interface FATFListCountry {
  code: string;
  name: string;
  list_type: 'black' | 'grey';
  added_date?: string;
  reason?: string;
}

export interface CountryInfo {
  code: string;
  name: string;
  region: string;
  risk_score: number;
  risk_level: RiskLevel;
  fatf_status?: 'black' | 'grey' | 'none';
  eu_high_risk: boolean;
  tax_haven: boolean;
  currency_code?: string;
  regulatory_framework?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SERVICE
// ═══════════════════════════════════════════════════════════════════════════════

export class GeographicRiskService extends BaseService {
  private readonly baseUrl: string;

  constructor(http: AxiosInstance, events: EventEmitter, baseUrl = 'http://localhost:8006') {
    super(http, events);
    this.baseUrl = baseUrl;
  }

  /**
   * Get risk assessment for a country
   */
  async getCountryRisk(countryCode: string): Promise<CountryRiskResponse> {
    const response = await this.http.post<CountryRiskResponse>(
      `${this.baseUrl}/geo/country-risk`,
      { country_code: countryCode.toUpperCase() }
    );
    this.events.emit('geo:risk_assessed', response.data);
    return response.data;
  }

  /**
   * Get risk assessment for an IP address
   */
  async getIPRisk(ipAddress: string): Promise<IPRiskResponse> {
    const response = await this.http.post<IPRiskResponse>(
      `${this.baseUrl}/geo/ip-risk`,
      { ip_address: ipAddress }
    );
    return response.data;
  }

  /**
   * Get comprehensive geographic risk for a transaction
   */
  async getTransactionRisk(request: TransactionGeoRiskRequest): Promise<TransactionGeoRiskResponse> {
    const response = await this.http.post<TransactionGeoRiskResponse>(
      `${this.baseUrl}/geo/transaction-risk`,
      request
    );
    return response.data;
  }

  /**
   * Get FATF Black List countries
   */
  async getFATFBlackList(): Promise<FATFListCountry[]> {
    const response = await this.http.get<{ countries: FATFListCountry[] }>(
      `${this.baseUrl}/geo/lists/fatf-black`
    );
    return response.data.countries;
  }

  /**
   * Get FATF Grey List countries
   */
  async getFATFGreyList(): Promise<FATFListCountry[]> {
    const response = await this.http.get<{ countries: FATFListCountry[] }>(
      `${this.baseUrl}/geo/lists/fatf-grey`
    );
    return response.data.countries;
  }

  /**
   * Get EU High Risk Third Countries
   */
  async getEUHighRiskList(): Promise<FATFListCountry[]> {
    const response = await this.http.get<{ countries: FATFListCountry[] }>(
      `${this.baseUrl}/geo/lists/eu-high-risk`
    );
    return response.data.countries;
  }

  /**
   * Get Tax Haven jurisdictions
   */
  async getTaxHavens(): Promise<FATFListCountry[]> {
    const response = await this.http.get<{ countries: FATFListCountry[] }>(
      `${this.baseUrl}/geo/lists/tax-havens`
    );
    return response.data.countries;
  }

  /**
   * Get detailed country information
   */
  async getCountryInfo(countryCode: string): Promise<CountryInfo> {
    const response = await this.http.get<CountryInfo>(
      `${this.baseUrl}/geo/country/${countryCode.toUpperCase()}`
    );
    return response.data;
  }

  /**
   * Check if a country is high risk (FATF Black/Grey or EU High Risk)
   */
  async isHighRiskCountry(countryCode: string): Promise<boolean> {
    const risk = await this.getCountryRisk(countryCode);
    return risk.risk_level === 'PROHIBITED' || risk.risk_level === 'VERY_HIGH' || risk.risk_level === 'HIGH';
  }

  /**
   * Check if transaction involves prohibited jurisdiction
   */
  async isProhibitedTransaction(
    originatorCountry: string,
    beneficiaryCountry: string
  ): Promise<boolean> {
    const transactionRisk = await this.getTransactionRisk({
      originator_country: originatorCountry,
      beneficiary_country: beneficiaryCountry,
    });
    return transactionRisk.transaction_policy === 'BLOCK';
  }

  /**
   * Check service health
   */
  async health(): Promise<{
    status: string;
    service: string;
    lists: { fatf_black: number; fatf_grey: number; eu_high_risk: number; tax_havens: number };
  }> {
    const response = await this.http.get(`${this.baseUrl}/health`);
    return response.data;
  }
}
