/**
 * Compliance Service - Unified Compliance Evaluation
 * 
 * Provides access to the AMTTP Orchestrator's compliance evaluation
 * which combines ML risk scoring, sanctions screening, AML monitoring,
 * and geographic risk assessment.
 */

import { AxiosInstance } from 'axios';
import { BaseService } from './base';
import { EventEmitter } from '../events';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export type ComplianceAction = 'ALLOW' | 'REQUIRE_INFO' | 'REQUIRE_ESCROW' | 'BLOCK' | 'REVIEW';
export type EntityType = 'RETAIL' | 'INSTITUTIONAL' | 'VASP' | 'HIGH_NET_WORTH' | 'PEP' | 'UNVERIFIED';
export type KYCLevel = 'NONE' | 'BASIC' | 'STANDARD' | 'ENHANCED';
export type RiskTolerance = 'STRICT' | 'MODERATE' | 'RELAXED';

export interface EntityProfile {
  address: string;
  entity_type: EntityType;
  kyc_level: KYCLevel;
  risk_tolerance: RiskTolerance;
  jurisdiction: string;
  daily_limit_eth: number;
  monthly_limit_eth: number;
  single_tx_limit_eth: number;
  sanctions_checked: boolean;
  pep_checked: boolean;
  source_of_funds_verified: boolean;
  travel_rule_threshold_eth: number;
  total_transactions: number;
  daily_volume_eth: number;
  monthly_volume_eth: number;
  risk_score_cache?: number;
  last_activity?: string;
  created_at: string;
  updated_at: string;
}

export interface ComplianceCheck {
  service: string;
  check_type: string;
  passed: boolean;
  score?: number;
  details?: Record<string, unknown>;
  action_required?: string;
  reason?: string;
}

export interface EvaluateRequest {
  from_address: string;
  to_address: string;
  value_eth: number;
  asset?: string;
  chain_id?: number;
  metadata?: Record<string, unknown>;
}

export interface EvaluateResponse {
  decision_id: string;
  timestamp: string;
  from_address: string;
  to_address: string;
  value_eth: number;
  originator_profile: EntityProfile;
  beneficiary_profile: EntityProfile;
  checks: ComplianceCheck[];
  action: ComplianceAction;
  risk_score: number;
  reasons: string[];
  requires_travel_rule: boolean;
  requires_sar: boolean;
  requires_escrow: boolean;
  escrow_duration_hours: number;
  processing_time_ms: number;
}

export interface DashboardStats {
  total_transactions: number;
  transactions_today: number;
  high_risk_count: number;
  blocked_count: number;
  pending_review: number;
  total_value_eth: number;
  avg_risk_score: number;
  compliance_rate: number;
}

export interface DashboardAlert {
  id: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  type: string;
  message: string;
  address: string;
  timestamp: string;
  acknowledged: boolean;
}

export interface TimelineDataPoint {
  timestamp: string;
  transactions: number;
  volume: number;
  risk_score: number;
  blocked: number;
}

export interface DecisionRecord {
  decision_id: string;
  timestamp: string;
  from_address: string;
  to_address: string;
  value_eth: number;
  action: ComplianceAction;
  risk_score: number;
}

export interface DecisionListOptions {
  limit?: number;
  offset?: number;
  action?: ComplianceAction;
  from_date?: string;
  to_date?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SERVICE
// ═══════════════════════════════════════════════════════════════════════════════

export class ComplianceService extends BaseService {
  constructor(http: AxiosInstance, events: EventEmitter) {
    super(http, events);
  }

  /**
   * Evaluate a transaction for compliance
   * This is the main entry point for transaction evaluation
   */
  async evaluate(request: EvaluateRequest): Promise<EvaluateResponse> {
    const response = await this.http.post<EvaluateResponse>('/evaluate', request);
    this.events.emit('compliance:evaluated', response.data);
    return response.data;
  }

  /**
   * Evaluate with UI integrity verification
   * Binds the evaluation to a UI snapshot hash for audit trail
   */
  async evaluateWithIntegrity(
    request: EvaluateRequest,
    snapshotHash: string
  ): Promise<EvaluateResponse & { integrity_verified: boolean }> {
    const response = await this.http.post('/evaluate-with-integrity', {
      ...request,
      ui_snapshot_hash: snapshotHash,
    });
    return response.data;
  }

  /**
   * Get dashboard statistics
   */
  async getDashboardStats(): Promise<DashboardStats> {
    const response = await this.http.get<DashboardStats>('/dashboard/stats');
    return response.data;
  }

  /**
   * Get dashboard alerts
   */
  async getDashboardAlerts(
    options?: { limit?: number; severity?: string }
  ): Promise<DashboardAlert[]> {
    const response = await this.http.get<{ alerts: DashboardAlert[] }>('/dashboard/alerts', {
      params: options,
    });
    return response.data.alerts;
  }

  /**
   * Get timeline data for charts
   */
  async getTimelineData(
    options?: { hours?: number; interval?: string }
  ): Promise<TimelineDataPoint[]> {
    const response = await this.http.get<{ data: TimelineDataPoint[] }>('/dashboard/timeline', {
      params: options,
    });
    return response.data.data;
  }

  /**
   * Get Sankey flow data for value visualization
   */
  async getSankeyFlow(options?: { limit?: number }): Promise<{
    nodes: Array<{ id: string; name: string; category: string }>;
    links: Array<{ source: string; target: string; value: number }>;
  }> {
    const response = await this.http.get('/sankey-flow', { params: options });
    return response.data;
  }

  /**
   * Get entity profile by address
   */
  async getProfile(address: string): Promise<EntityProfile> {
    const response = await this.http.get<EntityProfile>(`/profiles/${address}`);
    return response.data;
  }

  /**
   * Update entity profile
   */
  async updateProfile(
    address: string,
    updates: Partial<EntityProfile>
  ): Promise<EntityProfile> {
    const response = await this.http.put<EntityProfile>(`/profiles/${address}`, updates);
    this.events.emit('profile:updated', response.data);
    return response.data;
  }

  /**
   * Set entity type for an address
   */
  async setEntityType(address: string, entityType: EntityType): Promise<EntityProfile> {
    const response = await this.http.post<EntityProfile>(
      `/profiles/${address}/set-type/${entityType}`
    );
    return response.data;
  }

  /**
   * List all profiles
   */
  async listProfiles(options?: { limit?: number; offset?: number }): Promise<EntityProfile[]> {
    const response = await this.http.get<{ profiles: EntityProfile[] }>('/profiles', {
      params: options,
    });
    return response.data.profiles;
  }

  /**
   * Get decision history
   */
  async listDecisions(options?: DecisionListOptions): Promise<DecisionRecord[]> {
    const response = await this.http.get<{ decisions: DecisionRecord[] }>('/decisions', {
      params: options,
    });
    return response.data.decisions;
  }

  /**
   * Get available entity types
   */
  async getEntityTypes(): Promise<Array<{ type: EntityType; description: string }>> {
    const response = await this.http.get('/entity-types');
    return response.data.entity_types;
  }

  /**
   * Check service health
   */
  async health(): Promise<{
    status: string;
    service: string;
    connected_services: Record<string, string>;
    profiles_loaded: number;
  }> {
    const response = await this.http.get('/health');
    return response.data;
  }
}
