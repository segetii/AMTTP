/**
 * Reputation Service
 * Wraps /reputation endpoints for 5-tier reputation system
 */

import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
import { BaseService } from './base';

// Local type definitions
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

export class ReputationService extends BaseService {
  constructor(http: AxiosInstance, events: EventEmitter) {
    super(http, events);
  }

  /**
   * Get reputation profile for an address
   */
  async getProfile(address: string): Promise<ReputationProfile> {
    const response = await this.http.get<ReputationProfile>(`/reputation/${address}`);
    return response.data;
  }

  /**
   * Get reputation score
   */
  async getScore(address: string): Promise<ReputationScore> {
    const response = await this.http.get<ReputationScore>(`/reputation/${address}/score`);
    return response.data;
  }

  /**
   * Get reputation tier
   */
  async getTier(address: string): Promise<ReputationTier> {
    const profile = await this.getProfile(address);
    return profile.tier;
  }

  /**
   * Get tier requirements
   */
  async getTierRequirements(tier?: ReputationTier): Promise<TierRequirements[]> {
    const url = tier ? `/reputation/tiers?tier=${tier}` : '/reputation/tiers';
    const response = await this.http.get<{ tiers: TierRequirements[] }>(url);
    return response.data.tiers;
  }

  /**
   * Get progress to next tier
   */
  async getProgress(address: string): Promise<{
    currentTier: ReputationTier;
    nextTier?: ReputationTier;
    currentScore: number;
    requiredScore?: number;
    progress: number;
    missingRequirements: string[];
  }> {
    const response = await this.http.get(`/reputation/${address}/progress`);
    return response.data;
  }

  /**
   * Get reputation history
   */
  async getHistory(address: string, options?: {
    type?: string;
    limit?: number;
    offset?: number;
    startDate?: Date;
    endDate?: Date;
  }): Promise<{
    events: ReputationEvent[];
    total: number;
  }> {
    const params = new URLSearchParams();
    if (options?.type) params.append('type', options.type);
    if (options?.limit) params.append('limit', options.limit.toString());
    if (options?.offset) params.append('offset', options.offset.toString());
    if (options?.startDate) params.append('startDate', options.startDate.toISOString());
    if (options?.endDate) params.append('endDate', options.endDate.toISOString());

    const response = await this.http.get<{
      events: ReputationEvent[];
      total: number;
    }>(`/reputation/${address}/history?${params.toString()}`);

    return response.data;
  }

  /**
   * Get badges for an address
   */
  async getBadges(address: string): Promise<Badge[]> {
    const response = await this.http.get<{ badges: Badge[] }>(`/reputation/${address}/badges`);
    return response.data.badges;
  }

  /**
   * Get available badges
   */
  async getAvailableBadges(): Promise<{
    badges: {
      id: string;
      name: string;
      description: string;
      icon: string;
      category: string;
      requirements: string[];
    }[];
  }> {
    const response = await this.http.get('/reputation/badges');
    return response.data;
  }

  /**
   * Get leaderboard
   */
  async getLeaderboard(options?: {
    tier?: ReputationTier;
    limit?: number;
    offset?: number;
  }): Promise<{
    entries: LeaderboardEntry[];
    total: number;
  }> {
    const params = new URLSearchParams();
    if (options?.tier) params.append('tier', options.tier);
    if (options?.limit) params.append('limit', options.limit.toString());
    if (options?.offset) params.append('offset', options.offset.toString());

    const response = await this.http.get<{
      entries: LeaderboardEntry[];
      total: number;
    }>(`/reputation/leaderboard?${params.toString()}`);

    return response.data;
  }

  /**
   * Get reputation statistics
   */
  async getStatistics(): Promise<{
    totalUsers: number;
    byTier: Record<ReputationTier, number>;
    averageScore: number;
    topBadges: { badge: Badge; count: number }[];
  }> {
    const response = await this.http.get('/reputation/statistics');
    return response.data;
  }

  /**
   * Calculate reputation impact of a transaction
   */
  async calculateImpact(address: string, transaction: {
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
  }> {
    const response = await this.http.post(`/reputation/${address}/calculate-impact`, transaction);
    
    this.events.emit('reputation:impactCalculated', {
      address,
      scoreChange: response.data.scoreChange
    });

    return response.data;
  }

  /**
   * Get transaction limits based on reputation
   */
  async getLimits(address: string): Promise<{
    tier: ReputationTier;
    limits: {
      daily: { limit: string; used: string; remaining: string };
      weekly: { limit: string; used: string; remaining: string };
      monthly: { limit: string; used: string; remaining: string };
    };
  }> {
    const response = await this.http.get(`/reputation/${address}/limits`);
    return response.data;
  }

  /**
   * Compare reputation between two addresses
   */
  async compare(address1: string, address2: string): Promise<{
    address1: ReputationProfile;
    address2: ReputationProfile;
    comparison: {
      tierDifference: number;
      scoreDifference: number;
      transactionDifference: number;
    };
  }> {
    const response = await this.http.get(`/reputation/compare?address1=${address1}&address2=${address2}`);
    return response.data;
  }
}
