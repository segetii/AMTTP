"use strict";
/**
 * Reputation Service
 * Wraps /reputation endpoints for 5-tier reputation system
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.ReputationService = void 0;
const base_1 = require("./base");
class ReputationService extends base_1.BaseService {
    constructor(http, events) {
        super(http, events);
    }
    /**
     * Get reputation profile for an address
     */
    async getProfile(address) {
        const response = await this.http.get(`/reputation/${address}`);
        return response.data;
    }
    /**
     * Get reputation score
     */
    async getScore(address) {
        const response = await this.http.get(`/reputation/${address}/score`);
        return response.data;
    }
    /**
     * Get reputation tier
     */
    async getTier(address) {
        const profile = await this.getProfile(address);
        return profile.tier;
    }
    /**
     * Get tier requirements
     */
    async getTierRequirements(tier) {
        const url = tier ? `/reputation/tiers?tier=${tier}` : '/reputation/tiers';
        const response = await this.http.get(url);
        return response.data.tiers;
    }
    /**
     * Get progress to next tier
     */
    async getProgress(address) {
        const response = await this.http.get(`/reputation/${address}/progress`);
        return response.data;
    }
    /**
     * Get reputation history
     */
    async getHistory(address, options) {
        const params = new URLSearchParams();
        if (options?.type)
            params.append('type', options.type);
        if (options?.limit)
            params.append('limit', options.limit.toString());
        if (options?.offset)
            params.append('offset', options.offset.toString());
        if (options?.startDate)
            params.append('startDate', options.startDate.toISOString());
        if (options?.endDate)
            params.append('endDate', options.endDate.toISOString());
        const response = await this.http.get(`/reputation/${address}/history?${params.toString()}`);
        return response.data;
    }
    /**
     * Get badges for an address
     */
    async getBadges(address) {
        const response = await this.http.get(`/reputation/${address}/badges`);
        return response.data.badges;
    }
    /**
     * Get available badges
     */
    async getAvailableBadges() {
        const response = await this.http.get('/reputation/badges');
        return response.data;
    }
    /**
     * Get leaderboard
     */
    async getLeaderboard(options) {
        const params = new URLSearchParams();
        if (options?.tier)
            params.append('tier', options.tier);
        if (options?.limit)
            params.append('limit', options.limit.toString());
        if (options?.offset)
            params.append('offset', options.offset.toString());
        const response = await this.http.get(`/reputation/leaderboard?${params.toString()}`);
        return response.data;
    }
    /**
     * Get reputation statistics
     */
    async getStatistics() {
        const response = await this.http.get('/reputation/statistics');
        return response.data;
    }
    /**
     * Calculate reputation impact of a transaction
     */
    async calculateImpact(address, transaction) {
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
    async getLimits(address) {
        const response = await this.http.get(`/reputation/${address}/limits`);
        return response.data;
    }
    /**
     * Compare reputation between two addresses
     */
    async compare(address1, address2) {
        const response = await this.http.get(`/reputation/compare?address1=${address1}&address2=${address2}`);
        return response.data;
    }
}
exports.ReputationService = ReputationService;
//# sourceMappingURL=reputation.js.map