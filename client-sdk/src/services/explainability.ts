/**
 * Explainability Service - ML Decision Explanations
 * 
 * Provides human-readable explanations for risk scores and decisions
 * using SHAP-based analysis and rule-based reasoning.
 */

import { AxiosInstance } from 'axios';
import { BaseService } from './base';
import { EventEmitter } from '../events';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export type ImpactLevel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'NEUTRAL';
export type RecommendedAction = 'BLOCK' | 'ESCROW' | 'REVIEW' | 'ALLOW';

export interface ExplanationFactor {
  feature: string;
  reason: string;
  detail: string;
  impact: ImpactLevel;
  contribution: number;
}

export interface TypologyMatch {
  typology_id: string;
  typology_name: string;
  confidence: number;
  indicators: string[];
}

export interface RiskExplanation {
  risk_score: number;
  action: RecommendedAction;
  confidence: number;
  summary: string;
  top_reasons: string[];
  factors: ExplanationFactor[];
  typologies_detected: TypologyMatch[];
  degraded_mode?: boolean;
}

export interface ExplainRequest {
  risk_score: number;
  features: Record<string, unknown>;
  graph_context?: Record<string, unknown>;
}

export interface TransactionExplainRequest {
  transaction_hash: string;
  risk_score: number;
  sender: string;
  receiver: string;
  amount: number;
  features: Record<string, unknown>;
}

export interface TransactionExplanation extends RiskExplanation {
  transaction: {
    hash: string;
    sender: string;
    receiver: string;
    amount: number;
  };
}

export interface Typology {
  id: string;
  name: string;
  description: string;
  indicators?: string[];
  risk_weight?: number;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SERVICE
// ═══════════════════════════════════════════════════════════════════════════════

export class ExplainabilityService extends BaseService {
  private readonly baseUrl: string;

  constructor(http: AxiosInstance, events: EventEmitter, baseUrl = 'http://localhost:8009') {
    super(http, events);
    this.baseUrl = baseUrl;
  }

  /**
   * Get explanation for a risk score
   */
  async explain(request: ExplainRequest): Promise<RiskExplanation> {
    const response = await this.http.post<RiskExplanation>(
      `${this.baseUrl}/explain`,
      request
    );
    this.events.emit('explainability:explained', response.data);
    return response.data;
  }

  /**
   * Get explanation for a specific transaction
   */
  async explainTransaction(request: TransactionExplainRequest): Promise<TransactionExplanation> {
    const response = await this.http.post<TransactionExplanation>(
      `${this.baseUrl}/explain/transaction`,
      request
    );
    return response.data;
  }

  /**
   * Get all known fraud typologies
   */
  async getTypologies(): Promise<Typology[]> {
    const response = await this.http.get<{ typologies: Typology[] }>(
      `${this.baseUrl}/typologies`
    );
    return response.data.typologies;
  }

  /**
   * Get explanation for an address based on its features
   */
  async explainAddress(
    address: string,
    features: Record<string, unknown>
  ): Promise<RiskExplanation> {
    return this.explain({
      risk_score: (features.risk_score as number) || 50,
      features: {
        ...features,
        address,
      },
    });
  }

  /**
   * Get a human-readable summary for a risk level
   */
  static getRiskSummary(riskScore: number): string {
    if (riskScore >= 90) {
      return 'Critical risk - Immediate action required';
    } else if (riskScore >= 75) {
      return 'High risk - Enhanced review recommended';
    } else if (riskScore >= 50) {
      return 'Medium risk - Standard monitoring applies';
    } else if (riskScore >= 25) {
      return 'Low risk - Continue normal processing';
    } else {
      return 'Minimal risk - Routine transaction';
    }
  }

  /**
   * Get recommended action based on risk score
   */
  static getRecommendedAction(riskScore: number): RecommendedAction {
    if (riskScore >= 90) return 'BLOCK';
    if (riskScore >= 75) return 'ESCROW';
    if (riskScore >= 50) return 'REVIEW';
    return 'ALLOW';
  }

  /**
   * Check service health
   */
  async health(): Promise<{ status: string; service: string; version: string }> {
    const response = await this.http.get(`${this.baseUrl}/health`);
    return response.data;
  }
}
