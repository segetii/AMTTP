"use strict";
/**
 * PEP Screening Service
 * Wraps /pep endpoints for Politically Exposed Person screening
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.PEPService = void 0;
const base_1 = require("./base");
class PEPService extends base_1.BaseService {
    constructor(http, events) {
        super(http, events);
    }
    /**
     * Screen an address for PEP matches
     */
    async screen(request) {
        const response = await this.http.post('/pep/screen', request);
        return response.data;
    }
    /**
     * Get cached screening result
     */
    async getResult(address) {
        try {
            const response = await this.http.get(`/pep/result/${address}`);
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
     * Check if address has PEP matches
     */
    async hasPEPMatches(address) {
        const response = await this.http.get(`/pep/check/${address}`);
        return response.data;
    }
    /**
     * Get screening history for an address
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
        const response = await this.http.get(`/pep/history/${address}?${params.toString()}`);
        return response.data;
    }
    /**
     * Batch screen multiple addresses
     */
    async batchScreen(addresses) {
        const response = await this.http.post('/pep/batch', { addresses });
        return response.data;
    }
    /**
     * Acknowledge a PEP match (mark as reviewed)
     */
    async acknowledgeMatch(address, matchId, decision) {
        const response = await this.http.post(`/pep/${address}/matches/${matchId}/acknowledge`, decision);
        return response.data;
    }
    /**
     * Get match details
     */
    async getMatchDetails(address, matchId) {
        const response = await this.http.get(`/pep/${address}/matches/${matchId}`);
        return response.data;
    }
    /**
     * Get available screening providers
     */
    async getProviders() {
        const response = await this.http.get('/pep/providers');
        return response.data;
    }
    /**
     * Invalidate cached screening result
     */
    async invalidateCache(address) {
        await this.http.delete(`/pep/cache/${address}`);
    }
    /**
     * Get PEP screening statistics
     */
    async getStatistics() {
        const response = await this.http.get('/pep/statistics');
        return response.data;
    }
    /**
     * Schedule periodic rescreening
     */
    async scheduleRescreening(address, intervalDays) {
        const response = await this.http.post(`/pep/${address}/schedule`, { intervalDays });
        return response.data;
    }
}
exports.PEPService = PEPService;
//# sourceMappingURL=pep.js.map