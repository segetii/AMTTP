// src/ml.ts
// ML API integration for AMTTP Client SDK
import axios from 'axios';
import { RiskLevel, PolicyAction } from './types.js';
/**
 * ML Service client for fraud detection inference
 */
export class MLService {
    constructor(baseUrl = 'http://localhost:8000') {
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
    async scoreTransaction(transactionId, features) {
        try {
            const response = await this.client.post('/predict', {
                transaction_id: transactionId,
                features,
            });
            return this.mapResponseToRiskScore(response.data);
        }
        catch (error) {
            console.error('ML scoring error:', error);
            return this.getFallbackScore();
        }
    }
    /**
     * Score multiple transactions in batch
     */
    async scoreBatch(transactions) {
        try {
            const response = await this.client.post('/predict/batch', {
                transactions: transactions.map(tx => ({
                    transaction_id: tx.id,
                    features: tx.features,
                })),
            });
            return response.data.predictions.map(pred => this.mapResponseToRiskScore(pred));
        }
        catch (error) {
            console.error('ML batch scoring error:', error);
            return transactions.map(() => this.getFallbackScore());
        }
    }
    /**
     * Get model information
     */
    async getModelInfo() {
        try {
            const response = await this.client.get('/model/info');
            return response.data;
        }
        catch (error) {
            console.error('Failed to get model info:', error);
            return null;
        }
    }
    /**
     * Check service health
     */
    async healthCheck() {
        try {
            const response = await this.client.get('/health');
            return response.data;
        }
        catch (error) {
            return { status: 'unreachable', model_loaded: false };
        }
    }
    /**
     * Map API response to RiskScore type
     */
    mapResponseToRiskScore(data) {
        const riskScore = data.risk_score;
        const riskScoreInt = Math.round(riskScore * 1000);
        // Determine risk level
        let riskLevel;
        let riskCategory;
        if (riskScoreInt < 250) {
            riskLevel = RiskLevel.MINIMAL;
            riskCategory = 'MINIMAL';
        }
        else if (riskScoreInt < 400) {
            riskLevel = RiskLevel.LOW;
            riskCategory = 'LOW';
        }
        else if (riskScoreInt < 700) {
            riskLevel = RiskLevel.MEDIUM;
            riskCategory = 'MEDIUM';
        }
        else {
            riskLevel = RiskLevel.HIGH;
            riskCategory = 'HIGH';
        }
        // Map action string to enum
        let action;
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
    generateRecommendations(riskLevel, action) {
        const recommendations = [];
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
    getFallbackScore() {
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
export function createMLService(baseUrl) {
    return new MLService(baseUrl);
}
//# sourceMappingURL=ml.js.map