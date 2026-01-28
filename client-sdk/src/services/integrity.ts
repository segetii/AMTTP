/**
 * Integrity Service - UI Snapshot and Audit Trail
 * 
 * Provides UI integrity verification using cryptographic hashes
 * to ensure What-You-See-Is-What-You-Sign (WYSIWYS) compliance.
 */

import { AxiosInstance } from 'axios';
import { BaseService } from './base';
import { EventEmitter } from '../events';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface SnapshotData {
  component_id: string;
  component_type: string;
  state: Record<string, unknown>;
  timestamp: string;
  user_id?: string;
  session_id?: string;
}

export interface RegisterHashRequest {
  snapshot_hash: string;
  snapshot_data: SnapshotData;
  signature?: string;
}

export interface RegisterHashResponse {
  hash_id: string;
  snapshot_hash: string;
  registered_at: string;
  expires_at: string;
}

export interface VerifyIntegrityRequest {
  snapshot_hash: string;
  expected_state?: Record<string, unknown>;
}

export interface VerifyIntegrityResponse {
  is_valid: boolean;
  snapshot_hash: string;
  registered_at?: string;
  mismatch_fields?: string[];
  reason?: string;
}

export interface PaymentSubmission {
  payment_id: string;
  snapshot_hash: string;
  from_address: string;
  to_address: string;
  amount: number;
  asset: string;
  ui_state: Record<string, unknown>;
}

export interface PaymentSubmissionResponse {
  submission_id: string;
  payment_id: string;
  integrity_verified: boolean;
  snapshot_hash: string;
  submitted_at: string;
  compliance_decision?: {
    action: string;
    risk_score: number;
    reasons: string[];
  };
}

export interface IntegrityViolation {
  id: string;
  violation_type: string;
  expected_hash: string;
  actual_hash: string;
  detected_at: string;
  user_id?: string;
  session_id?: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  resolved: boolean;
}

export interface ViolationListOptions {
  limit?: number;
  offset?: number;
  severity?: string;
  resolved?: boolean;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SERVICE
// ═══════════════════════════════════════════════════════════════════════════════

export class IntegrityService extends BaseService {
  private readonly baseUrl: string;

  constructor(http: AxiosInstance, events: EventEmitter, baseUrl = 'http://localhost:8008') {
    super(http, events);
    this.baseUrl = baseUrl;
  }

  /**
   * Register a UI snapshot hash for later verification
   */
  async registerHash(request: RegisterHashRequest): Promise<RegisterHashResponse> {
    const response = await this.http.post<RegisterHashResponse>(
      `${this.baseUrl}/register-hash`,
      request
    );
    return response.data;
  }

  /**
   * Verify the integrity of a UI snapshot
   */
  async verifyIntegrity(request: VerifyIntegrityRequest): Promise<VerifyIntegrityResponse> {
    const response = await this.http.post<VerifyIntegrityResponse>(
      `${this.baseUrl}/verify-integrity`,
      request
    );
    
    this.events.emit('integrity:verified', response.data);
    
    if (!response.data.is_valid) {
      this.events.emit('integrity:violation', response.data);
    }
    
    return response.data;
  }

  /**
   * Submit a payment with integrity verification
   */
  async submitPayment(submission: PaymentSubmission): Promise<PaymentSubmissionResponse> {
    const response = await this.http.post<PaymentSubmissionResponse>(
      `${this.baseUrl}/submit-payment`,
      submission
    );
    return response.data;
  }

  /**
   * Get list of integrity violations
   */
  async getViolations(options?: ViolationListOptions): Promise<IntegrityViolation[]> {
    const response = await this.http.get<{ violations: IntegrityViolation[] }>(
      `${this.baseUrl}/violations`,
      { params: options }
    );
    return response.data.violations;
  }

  /**
   * Generate a snapshot hash from UI state
   */
  static async generateSnapshotHash(state: Record<string, unknown>): Promise<string> {
    const encoder = new TextEncoder();
    const data = encoder.encode(JSON.stringify(state, Object.keys(state).sort()));
    const hashBuffer = await crypto.subtle.digest('SHA-256', data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  }

  /**
   * Create a snapshot data object
   */
  static createSnapshotData(
    componentId: string,
    componentType: string,
    state: Record<string, unknown>,
    userId?: string,
    sessionId?: string
  ): SnapshotData {
    return {
      component_id: componentId,
      component_type: componentType,
      state,
      timestamp: new Date().toISOString(),
      user_id: userId,
      session_id: sessionId,
    };
  }

  /**
   * Check service health
   */
  async health(): Promise<{ status: string; service: string }> {
    const response = await this.http.get(`${this.baseUrl}/health`);
    return response.data;
  }
}
