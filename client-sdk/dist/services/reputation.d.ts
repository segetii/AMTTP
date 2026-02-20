/**
 * Reputation Service
 * Wraps /reputation endpoints for 5-tier reputation system
 */
import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
import { BaseService } from './base';
export type ReputationTier = 'bronze' | 'silver' | 'gold' | 'platinum' | 'diamond';
export interface ReputationScore {
    address: string;
    tier: ReputationTier;
    score: number;
    totalTransactions: number;
}
export interface ReputationProfile {
    address: string;
    tier: ReputationTier;
    score: number;
    totalTransactions: number;
    successfulTransactions: number;
    disputesInitiated: number;
    disputesLost: number;
    averageTransactionValue: string;
    memberSince: string;
    lastActivityAt: string;
    badges: Badge[];
    history: ReputationEvent[];
}
export interface Badge {
    id: string;
    name: string;
    description: string;
    icon: string;
    earnedAt: string;
    category: 'transaction' | 'community' | 'compliance' | 'special';
}
export interface ReputationEvent {
    id: string;
    type: 'transaction' | 'dispute' | 'upgrade' | 'downgrade' | 'badge' | 'penalty';
    description: string;
    scoreChange: number;
    timestamp: string;
    metadata?: Record<string, any>;
}
export interface TierRequirements {
    tier: ReputationTier;
    minScore: number;
    minTransactions: number;
    maxDisputeRate: number;
    benefits: string[];
    transactionLimits: {
        daily: string;
        weekly: string;
        monthly: string;
    };
}
export interface LeaderboardEntry {
    rank: number;
    address: string;
    tier: ReputationTier;
    score: number;
    totalTransactions: number;
    badges: number;
}
export declare class ReputationService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Get reputation profile for an address
     */
    getProfile(address: string): Promise<ReputationProfile>;
    /**
     * Get reputation score
     */
    getScore(address: string): Promise<ReputationScore>;
    /**
     * Get reputation tier
     */
    getTier(address: string): Promise<ReputationTier>;
    /**
     * Get tier requirements
     */
    getTierRequirements(tier?: ReputationTier): Promise<TierRequirements[]>;
    /**
     * Get progress to next tier
     */
    getProgress(address: string): Promise<{
        currentTier: ReputationTier;
        nextTier?: ReputationTier;
        currentScore: number;
        requiredScore?: number;
        progress: number;
        missingRequirements: string[];
    }>;
    /**
     * Get reputation history
     */
    getHistory(address: string, options?: {
        type?: string;
        limit?: number;
        offset?: number;
        startDate?: Date;
        endDate?: Date;
    }): Promise<{
        events: ReputationEvent[];
        total: number;
    }>;
    /**
     * Get badges for an address
     */
    getBadges(address: string): Promise<Badge[]>;
    /**
     * Get available badges
     */
    getAvailableBadges(): Promise<{
        badges: {
            id: string;
            name: string;
            description: string;
            icon: string;
            category: string;
            requirements: string[];
        }[];
    }>;
    /**
     * Get leaderboard
     */
    getLeaderboard(options?: {
        tier?: ReputationTier;
        limit?: number;
        offset?: number;
    }): Promise<{
        entries: LeaderboardEntry[];
        total: number;
    }>;
    /**
     * Get reputation statistics
     */
    getStatistics(): Promise<{
        totalUsers: number;
        byTier: Record<ReputationTier, number>;
        averageScore: number;
        topBadges: {
            badge: Badge;
            count: number;
        }[];
    }>;
    /**
     * Calculate reputation impact of a transaction
     */
    calculateImpact(address: string, transaction: {
        amount: string;
        successful: boolean;
        counterpartyTier?: ReputationTier;
    }): Promise<{
        scoreChange: number;
        newScore: number;
        tierChange?: {
            from: ReputationTier;
            to: ReputationTier;
        };
        badgesEarned?: Badge[];
    }>;
    /**
     * Get transaction limits based on reputation
     */
    getLimits(address: string): Promise<{
        tier: ReputationTier;
        limits: {
            daily: {
                limit: string;
                used: string;
                remaining: string;
            };
            weekly: {
                limit: string;
                used: string;
                remaining: string;
            };
            monthly: {
                limit: string;
                used: string;
                remaining: string;
            };
        };
    }>;
    /**
     * Compare reputation between two addresses
     */
    compare(address1: string, address2: string): Promise<{
        address1: ReputationProfile;
        address2: ReputationProfile;
        comparison: {
            tierDifference: number;
            scoreDifference: number;
            transactionDifference: number;
        };
    }>;
}
//# sourceMappingURL=reputation.d.ts.map