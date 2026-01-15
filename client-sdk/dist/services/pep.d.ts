/**
 * PEP Screening Service
 * Wraps /pep endpoints for Politically Exposed Person screening
 */
import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
import { BaseService } from './base';
export interface PEPScreeningRequest {
    address: string;
    fullName?: string;
    dateOfBirth?: string;
    nationality?: string;
    includeRelatives?: boolean;
    includeAssociates?: boolean;
    providers?: string[];
}
export interface PEPMatch {
    id: string;
    name: string;
    matchScore: number;
    matchType: 'exact' | 'fuzzy' | 'partial';
    pepType: 'pep' | 'relative' | 'associate';
    position?: string;
    country?: string;
    dateOfBirth?: string;
    source: string;
    listType: 'sanction' | 'pep' | 'watchlist' | 'adverse_media';
    lastUpdated: string;
    details?: Record<string, any>;
}
export interface PEPScreeningResult {
    address: string;
    screened: boolean;
    matches: PEPMatch[];
    highestMatchScore: number;
    riskLevel: 'clear' | 'low' | 'medium' | 'high' | 'critical';
    requiresEDD: boolean;
    screenedAt: string;
    expiresAt: string;
    providers: string[];
}
export interface PEPHistoryEntry {
    id: string;
    address: string;
    result: PEPScreeningResult;
    triggeredBy: 'manual' | 'automated' | 'transaction';
    performedAt: string;
    performedBy?: string;
}
export declare class PEPService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Screen an address for PEP matches
     */
    screen(request: PEPScreeningRequest): Promise<PEPScreeningResult>;
    /**
     * Get cached screening result
     */
    getResult(address: string): Promise<PEPScreeningResult | null>;
    /**
     * Check if address has PEP matches
     */
    hasPEPMatches(address: string): Promise<{
        hasMatches: boolean;
        matchCount: number;
        highestRisk: string;
    }>;
    /**
     * Get screening history for an address
     */
    getHistory(address: string, options?: {
        limit?: number;
        offset?: number;
        startDate?: Date;
        endDate?: Date;
    }): Promise<{
        history: PEPHistoryEntry[];
        total: number;
    }>;
    /**
     * Batch screen multiple addresses
     */
    batchScreen(addresses: string[]): Promise<{
        results: PEPScreeningResult[];
        processedCount: number;
        failedCount: number;
    }>;
    /**
     * Acknowledge a PEP match (mark as reviewed)
     */
    acknowledgeMatch(address: string, matchId: string, decision: {
        approved: boolean;
        reason: string;
        reviewedBy: string;
    }): Promise<{
        acknowledged: boolean;
    }>;
    /**
     * Get match details
     */
    getMatchDetails(address: string, matchId: string): Promise<PEPMatch & {
        fullProfile?: Record<string, any>;
        relatedEntities?: {
            name: string;
            relationship: string;
        }[];
    }>;
    /**
     * Get available screening providers
     */
    getProviders(): Promise<{
        providers: {
            id: string;
            name: string;
            description: string;
            coverage: string[];
            enabled: boolean;
        }[];
    }>;
    /**
     * Invalidate cached screening result
     */
    invalidateCache(address: string): Promise<void>;
    /**
     * Get PEP screening statistics
     */
    getStatistics(): Promise<{
        totalScreenings: number;
        matchesFound: number;
        byRiskLevel: Record<string, number>;
        byListType: Record<string, number>;
        averageMatchScore: number;
    }>;
    /**
     * Schedule periodic rescreening
     */
    scheduleRescreening(address: string, intervalDays: number): Promise<{
        scheduled: boolean;
        nextScreeningAt: string;
    }>;
}
//# sourceMappingURL=pep.d.ts.map