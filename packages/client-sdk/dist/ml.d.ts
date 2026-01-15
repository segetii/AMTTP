import { RiskScore } from './types.js';
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
export declare class MLService {
    private client;
    private baseUrl;
    constructor(baseUrl?: string);
    /**
     * Score a single transaction
     */
    scoreTransaction(transactionId: string, features: Record<string, number>): Promise<RiskScore>;
    /**
     * Score multiple transactions in batch
     */
    scoreBatch(transactions: Array<{
        id: string;
        features: Record<string, number>;
    }>): Promise<RiskScore[]>;
    /**
     * Get model information
     */
    getModelInfo(): Promise<MLModelInfo | null>;
    /**
     * Check service health
     */
    healthCheck(): Promise<{
        status: string;
        model_loaded: boolean;
    }>;
    /**
     * Map API response to RiskScore type
     */
    private mapResponseToRiskScore;
    /**
     * Generate recommendations based on risk assessment
     */
    private generateRecommendations;
    /**
     * Return fallback score when service is unavailable
     */
    private getFallbackScore;
}
/**
 * Create ML service with default or custom URL
 */
export declare function createMLService(baseUrl?: string): MLService;
//# sourceMappingURL=ml.d.ts.map