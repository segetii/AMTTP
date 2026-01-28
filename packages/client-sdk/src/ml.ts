// src/ml.ts
// ML API integration for AMTTP Client SDK

import axios, { AxiosInstance } from 'axios';
import { RiskScore, RiskLevel, PolicyAction } from './types.js';

export interface MLPredictRequest {
  transactionId: string;
  features: Record<string, number>;
}

export interface MLPredictResponse {
  transaction_id: string;
  risk_score: number;
  prediction: number;
  action: string;
  confidence: string;
  processing_time_ms: number;
  model_version: string;
}

export interface MLBatchRequest {
  transactions: MLPredictRequest[];
}

export interface MLBatchResponse {
  predictions: MLPredictResponse[];
  total_processed: number;
  total_flagged: number;
  avg_processing_time_ms: number;
}

export interface MLModelInfo {
  primary_model: string;
  threshold: number;
  calibration_enabled: boolean;
  expected_metrics: {
    test_ap?: number;
    test_auc?: number;
  };
}

/**
 * ML Service client for fraud detection inference
 */
export class MLService {
  private client: AxiosInstance;
  private baseUrl: string;

  constructor(baseUrl: string = 'http://localhost:8000') {
    this.baseUrl = baseUrl;
    this.client = axios.create({
      baseURL: baseUrl,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });
  }

  /**
   * Score a single transaction
   */
  async scoreTransaction(
    transactionId: string,
    features: Record<string, number>
  ): Promise<RiskScore> {
    try {
      const response = await this.client.post<MLPredictResponse>('/predict', {
        transaction_id: transactionId,
        features,
      });

      return this.mapResponseToRiskScore(response.data);
    } catch (error) {
      console.error('ML scoring error:', error);
      return this.getFallbackScore();
    }
  }

  /**
   * Score multiple transactions in batch
   */
  async scoreBatch(
    transactions: Array<{ id: string; features: Record<string, number> }>
  ): Promise<RiskScore[]> {
    try {
      const response = await this.client.post<MLBatchResponse>('/predict/batch', {
        transactions: transactions.map(tx => ({
          transaction_id: tx.id,
          features: tx.features,
        })),
      });

      return response.data.predictions.map(pred => this.mapResponseToRiskScore(pred));
    } catch (error) {
      console.error('ML batch scoring error:', error);
      return transactions.map(() => this.getFallbackScore());
    }
  }

  /**
   * Get model information
   */
  async getModelInfo(): Promise<MLModelInfo | null> {
    try {
      const response = await this.client.get<MLModelInfo>('/model/info');
      return response.data;
    } catch (error) {
      console.error('Failed to get model info:', error);
      return null;
    }
  }

  /**
   * Check service health
   */
  async healthCheck(): Promise<{ status: string; model_loaded: boolean }> {
    try {
      const response = await this.client.get('/health');
      return response.data;
    } catch (error) {
      return { status: 'unreachable', model_loaded: false };
    }
  }

  /**
   * Map API response to RiskScore type
   */
  private mapResponseToRiskScore(data: MLPredictResponse): RiskScore {
    const riskScore = data.risk_score;
    const riskScoreInt = Math.round(riskScore * 1000);
    
    // Determine risk level
    let riskLevel: RiskLevel;
    let riskCategory: 'MINIMAL' | 'LOW' | 'MEDIUM' | 'HIGH';
    
    if (riskScoreInt < 250) {
      riskLevel = RiskLevel.MINIMAL;
      riskCategory = 'MINIMAL';
    } else if (riskScoreInt < 400) {
      riskLevel = RiskLevel.LOW;
      riskCategory = 'LOW';
    } else if (riskScoreInt < 700) {
      riskLevel = RiskLevel.MEDIUM;
      riskCategory = 'MEDIUM';
    } else {
      riskLevel = RiskLevel.HIGH;
      riskCategory = 'HIGH';
    }

    // Map action string to enum
    let action: PolicyAction;
    switch (data.action.toUpperCase()) {
      case 'APPROVE':
        action = PolicyAction.APPROVE;
        break;
      case 'MONITOR':
      case 'REVIEW':
        action = PolicyAction.REVIEW;
        break;
      case 'ESCROW':
        action = PolicyAction.ESCROW;
        break;
      case 'BLOCK':
        action = PolicyAction.BLOCK;
        break;
      default:
        action = PolicyAction.REVIEW;
    }

    return {
      riskScore,
      riskScoreInt,
      riskCategory,
      riskLevel,
      action,
      confidence: data.confidence === 'HIGH' ? 0.9 : data.confidence === 'MEDIUM' ? 0.7 : 0.5,
      recommendations: this.generateRecommendations(riskLevel, action),
      modelVersion: data.model_version,
      modelMetrics: {
        rocAUC: 0.94,
        prAUC: 0.87,
        f1: 0.87,
        architecture: 'Stacked Ensemble (GraphSAGE + LGBM + XGBoost + Linear Meta-Learner)',
      },
    };
  }

  /**
   * Generate recommendations based on risk assessment
   */
  private generateRecommendations(riskLevel: RiskLevel, action: PolicyAction): string[] {
    const recommendations: string[] = [];

    switch (action) {
      case PolicyAction.APPROVE:
        recommendations.push('✅ Transaction approved - low risk profile');
        break;
      case PolicyAction.REVIEW:
        recommendations.push('⚠️ Manual review recommended before processing');
        recommendations.push('📞 Consider additional verification');
        break;
      case PolicyAction.ESCROW:
        recommendations.push('🔒 High risk - use escrow protection');
        recommendations.push('⏱️ Funds will be held until conditions met');
        recommendations.push('🔍 Verify counterparty relationship');
        break;
      case PolicyAction.BLOCK:
        recommendations.push('🚫 Transaction blocked due to excessive risk');
        recommendations.push('📧 Contact support for manual review');
        break;
    }

    return recommendations;
  }

  /**
   * Return fallback score when service is unavailable
   */
  private getFallbackScore(): RiskScore {
    return {
      riskScore: 0.8,
      riskScoreInt: 800,
      riskCategory: 'HIGH',
      riskLevel: RiskLevel.HIGH,
      action: PolicyAction.ESCROW,
      confidence: 0.5,
      recommendations: ['⚠️ ML service unavailable - using safe fallback'],
      modelVersion: 'fallback-v1.0',
    };
  }
}

/**
 * Create ML service with default or custom URL
 */
export function createMLService(baseUrl?: string): MLService {
  return new MLService(baseUrl);
}
