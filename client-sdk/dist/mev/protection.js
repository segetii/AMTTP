"use strict";
/**
 * MEV Protection Service
 * Provides protection against Maximal Extractable Value attacks
 * Integrates with Flashbots and private mempool services
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.MEVProtection = void 0;
const base_1 = require("../services/base");
class MEVProtection extends base_1.BaseService {
    constructor(http, events) {
        super(http, events);
        this.config = {
            enabled: true,
            protectionLevel: 'enhanced',
            flashbotsEnabled: true,
            privateMempoolEnabled: true,
            maxSlippage: 0.5,
            deadlineMinutes: 20
        };
    }
    /**
     * Get current MEV protection configuration
     */
    getConfig() {
        return { ...this.config };
    }
    /**
     * Update MEV protection configuration
     */
    setConfig(config) {
        this.config = { ...this.config, ...config };
    }
    /**
     * Analyze transaction for MEV vulnerabilities
     */
    async analyze(transaction) {
        const response = await this.http.post('/mev/analyze', transaction);
        return response.data;
    }
    /**
     * Submit transaction with MEV protection
     */
    async submitProtected(transaction) {
        const response = await this.http.post('/mev/submit', {
            transaction,
            config: this.config
        });
        return response.data;
    }
    /**
     * Submit Flashbots bundle
     */
    async submitBundle(bundle) {
        const response = await this.http.post('/mev/bundle', bundle);
        return response.data;
    }
    /**
     * Get bundle status
     */
    async getBundleStatus(bundleHash) {
        const response = await this.http.get(`/mev/bundle/${bundleHash}`);
        return response.data;
    }
    /**
     * Simulate transaction
     */
    async simulate(transaction) {
        const response = await this.http.post('/mev/simulate', transaction);
        return response.data;
    }
    /**
     * Get protected transaction status
     */
    async getTransactionStatus(id) {
        const response = await this.http.get(`/mev/transaction/${id}`);
        return response.data;
    }
    /**
     * Get transaction history with MEV protection
     */
    async getHistory(options) {
        const params = new URLSearchParams();
        if (options?.address)
            params.append('address', options.address);
        if (options?.status)
            params.append('status', options.status);
        if (options?.limit)
            params.append('limit', options.limit.toString());
        if (options?.offset)
            params.append('offset', options.offset.toString());
        const response = await this.http.get(`/mev/history?${params.toString()}`);
        return response.data;
    }
    /**
     * Cancel pending protected transaction
     */
    async cancel(id) {
        const response = await this.http.post(`/mev/transaction/${id}/cancel`);
        return response.data;
    }
    /**
     * Get MEV statistics
     */
    async getStatistics() {
        const response = await this.http.get('/mev/statistics');
        return response.data;
    }
    /**
     * Check if Flashbots relay is available
     */
    async checkFlashbotsStatus() {
        const response = await this.http.get('/mev/flashbots/status');
        return response.data;
    }
    /**
     * Get recommended gas settings for protected transaction
     */
    async getGasRecommendation() {
        const response = await this.http.get('/mev/gas-recommendation');
        return response.data;
    }
}
exports.MEVProtection = MEVProtection;
//# sourceMappingURL=protection.js.map