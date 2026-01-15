/**
 * Risk Assessment Service
 * Wraps /risk endpoints for transaction risk scoring
 */
import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
import { BaseService } from './base';
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';
export interface LabelInfo {
    label: string;
    category: string;
    severity: string;
    source: string;
}
export interface RiskScore {
    address: string;
    score: number;
    level: RiskLevel;
    timestamp: string;
    expiresAt: string;
}
export interface RiskAssessmentRequest {
    address: string;
    transactionHash?: string;
    amount?: string;
    counterparty?: string;
    metadata?: Record<string, any>;
}
export interface RiskAssessmentResponse {
    address: string;
    riskScore: number;
    riskLevel: RiskLevel;
    factors: RiskFactor[];
    labels: LabelInfo[];
    timestamp: string;
    expiresAt: string;
    cached: boolean;
}
export interface RiskFactor {
    name: string;
    weight: number;
    value: number;
    description: string;
}
export interface BatchRiskRequest {
    addresses: string[];
    includeLabels?: boolean;
    includeFactors?: boolean;
}
export interface BatchRiskResponse {
    results: RiskAssessmentResponse[];
    processedCount: number;
    failedCount: number;
    failures: {
        address: string;
        error: string;
    }[];
}
export interface RiskThreshold {
    level: RiskLevel;
    minScore: number;
    maxScore: number;
    action: 'allow' | 'review' | 'block';
}
export declare class RiskService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Assess risk for a single address
     */
    assess(request: RiskAssessmentRequest): Promise<RiskAssessmentResponse>;
    /**
     * Get cached risk score for an address
     */
    getScore(address: string): Promise<RiskScore | null>;
    /**
     * Batch assess multiple addresses
     */
    batchAssess(request: BatchRiskRequest): Promise<BatchRiskResponse>;
    /**
     * Get risk thresholds configuration
     */
    getThresholds(): Promise<RiskThreshold[]>;
    /**
     * Check if address passes risk threshold
     */
    checkThreshold(address: string, maxRiskLevel?: RiskLevel): Promise<{
        passed: boolean;
        riskScore: number;
        riskLevel: RiskLevel;
        action: 'allow' | 'review' | 'block';
    }>;
    /**
     * Get risk history for an address
     */
    getHistory(address: string, options?: {
        limit?: number;
        offset?: number;
        startDate?: Date;
        endDate?: Date;
    }): Promise<{
        history: RiskAssessmentResponse[];
        total: number;
    }>;
    /**
     * Invalidate cached risk score
     */
    invalidateCache(address: string): Promise<void>;
    /**
     * Get risk factors configuration
     */
    getFactors(): Promise<{
        factors: {
            name: string;
            weight: number;
            description: string;
            enabled: boolean;
        }[];
    }>;
}
//# sourceMappingURL=risk.d.ts.map