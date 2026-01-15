/**
 * Label Service
 * Wraps /label endpoints for address labeling and categorization
 */
import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
import { BaseService } from './base';
export type LabelCategory = 'exchange' | 'defi' | 'bridge' | 'mixer' | 'gambling' | 'scam' | 'sanctions' | 'darknet' | 'ransomware' | 'theft' | 'phishing' | 'nft' | 'dao' | 'custodian' | 'payment_processor' | 'other';
export type LabelSeverity = 'info' | 'low' | 'medium' | 'high' | 'critical';
export interface AddressLabel {
    id: string;
    address: string;
    label: string;
    category: LabelCategory;
    severity: LabelSeverity;
    confidence: number;
    source: string;
    description?: string;
    metadata?: Record<string, any>;
    createdAt: string;
    updatedAt: string;
    expiresAt?: string;
    verified: boolean;
}
export interface LabelSearchResult {
    address: string;
    labels: AddressLabel[];
    riskImplication: 'safe' | 'caution' | 'warning' | 'danger';
    aggregatedSeverity: LabelSeverity;
}
export interface LabelStatistics {
    totalLabels: number;
    byCategory: Record<LabelCategory, number>;
    bySeverity: Record<LabelSeverity, number>;
    bySource: Record<string, number>;
    recentlyAdded: number;
    recentlyUpdated: number;
}
export declare class LabelService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Get labels for an address
     */
    getLabels(address: string): Promise<LabelSearchResult>;
    /**
     * Check if address has specific label categories
     */
    hasLabels(address: string, categories?: LabelCategory[]): Promise<{
        hasLabels: boolean;
        matchedCategories: LabelCategory[];
        highestSeverity?: LabelSeverity;
    }>;
    /**
     * Batch check multiple addresses
     */
    batchCheck(addresses: string[], options?: {
        categories?: LabelCategory[];
        minSeverity?: LabelSeverity;
    }): Promise<{
        results: {
            address: string;
            hasLabels: boolean;
            labels: AddressLabel[];
            riskImplication: string;
        }[];
        processedCount: number;
    }>;
    /**
     * Add a label to an address
     */
    addLabel(label: {
        address: string;
        label: string;
        category: LabelCategory;
        severity: LabelSeverity;
        confidence?: number;
        description?: string;
        metadata?: Record<string, any>;
        expiresAt?: string;
    }): Promise<AddressLabel>;
    /**
     * Update a label
     */
    updateLabel(id: string, updates: Partial<{
        label: string;
        category: LabelCategory;
        severity: LabelSeverity;
        confidence: number;
        description: string;
        metadata: Record<string, any>;
        expiresAt: string;
        verified: boolean;
    }>): Promise<AddressLabel>;
    /**
     * Remove a label
     */
    removeLabel(id: string): Promise<void>;
    /**
     * Verify a label
     */
    verifyLabel(id: string, verified: boolean, verifiedBy: string): Promise<AddressLabel>;
    /**
     * Search labels
     */
    search(options?: {
        query?: string;
        category?: LabelCategory;
        severity?: LabelSeverity;
        source?: string;
        verified?: boolean;
        limit?: number;
        offset?: number;
    }): Promise<{
        labels: AddressLabel[];
        total: number;
    }>;
    /**
     * Get label categories with descriptions
     */
    getCategories(): Promise<{
        categories: {
            id: LabelCategory;
            name: string;
            description: string;
            defaultSeverity: LabelSeverity;
            riskWeight: number;
        }[];
    }>;
    /**
     * Get label sources
     */
    getSources(): Promise<{
        sources: {
            id: string;
            name: string;
            description: string;
            reliability: number;
            labelCount: number;
        }[];
    }>;
    /**
     * Get label statistics
     */
    getStatistics(): Promise<LabelStatistics>;
    /**
     * Get label history for an address
     */
    getHistory(address: string, options?: {
        limit?: number;
        offset?: number;
    }): Promise<{
        history: {
            action: 'added' | 'updated' | 'removed';
            label: AddressLabel;
            timestamp: string;
            actor?: string;
        }[];
        total: number;
    }>;
    /**
     * Report a label (for moderation)
     */
    reportLabel(id: string, report: {
        reason: string;
        details?: string;
        reportedBy: string;
    }): Promise<{
        reported: boolean;
        reportId: string;
    }>;
    /**
     * Get risky label categories that should trigger blocking
     */
    getBlockingCategories(): Promise<LabelCategory[]>;
}
//# sourceMappingURL=label.d.ts.map