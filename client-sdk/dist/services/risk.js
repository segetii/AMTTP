"use strict";
/**
 * Risk Assessment Service
 * Wraps /risk endpoints for transaction risk scoring
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.RiskService = void 0;
const base_1 = require("./base");
class RiskService extends base_1.BaseService {
    constructor(http, events) {
        super(http, events);
    }
    /**
     * Assess risk for a single address
     */
    async assess(request) {
        const response = await this.http.post('/risk/assess', request);
        this.events.emit('risk:assessed', {
            address: request.address,
            riskLevel: response.data.riskLevel,
            riskScore: response.data.riskScore
        });
        return response.data;
    }
    /**
     * Get cached risk score for an address
     */
    async getScore(address) {
        try {
            const response = await this.http.get(`/risk/score/${address}`);
            return response.data;
        }
        catch (error) {
            if (error.response?.status === 404) {
                return null;
            }
            throw error;
        }
    }
    /**
     * Batch assess multiple addresses
     */
    async batchAssess(request) {
        const response = await this.http.post('/risk/batch', request);
        this.events.emit('risk:batchCompleted', {
            processedCount: response.data.processedCount,
            failedCount: response.data.failedCount
        });
        return response.data;
    }
    /**
     * Get risk thresholds configuration
     */
    async getThresholds() {
        const response = await this.http.get('/risk/thresholds');
        return response.data.thresholds;
    }
    /**
     * Check if address passes risk threshold
     */
    async checkThreshold(address, maxRiskLevel = 'medium') {
        const response = await this.http.post('/risk/check-threshold', { address, maxRiskLevel });
        return response.data;
    }
    /**
     * Get risk history for an address
     */
    async getHistory(address, options) {
        const params = new URLSearchParams();
        if (options?.limit)
            params.append('limit', options.limit.toString());
        if (options?.offset)
            params.append('offset', options.offset.toString());
        if (options?.startDate)
            params.append('startDate', options.startDate.toISOString());
        if (options?.endDate)
            params.append('endDate', options.endDate.toISOString());
        const response = await this.http.get(`/risk/history/${address}?${params.toString()}`);
        return response.data;
    }
    /**
     * Invalidate cached risk score
     */
    async invalidateCache(address) {
        await this.http.delete(`/risk/cache/${address}`);
        this.events.emit('risk:cacheInvalidated', { address });
    }
    /**
     * Get risk factors configuration
     */
    async getFactors() {
        const response = await this.http.get('/risk/factors');
        return response.data;
    }
}
exports.RiskService = RiskService;
//# sourceMappingURL=risk.js.map