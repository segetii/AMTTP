"use strict";
/**
 * Label Service
 * Wraps /label endpoints for address labeling and categorization
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.LabelService = void 0;
const base_1 = require("./base");
class LabelService extends base_1.BaseService {
    constructor(http, events) {
        super(http, events);
    }
    /**
     * Get labels for an address
     */
    async getLabels(address) {
        const response = await this.http.get(`/label/${address}`);
        return response.data;
    }
    /**
     * Check if address has specific label categories
     */
    async hasLabels(address, categories) {
        const params = new URLSearchParams();
        if (categories)
            categories.forEach(c => params.append('categories', c));
        const response = await this.http.get(`/label/${address}/check?${params.toString()}`);
        return response.data;
    }
    /**
     * Batch check multiple addresses
     */
    async batchCheck(addresses, options) {
        const response = await this.http.post('/label/batch', {
            addresses,
            ...options
        });
        return response.data;
    }
    /**
     * Add a label to an address
     */
    async addLabel(label) {
        const response = await this.http.post('/label', label);
        return response.data;
    }
    /**
     * Update a label
     */
    async updateLabel(id, updates) {
        const response = await this.http.put(`/label/${id}`, updates);
        return response.data;
    }
    /**
     * Remove a label
     */
    async removeLabel(id) {
        await this.http.delete(`/label/${id}`);
    }
    /**
     * Verify a label
     */
    async verifyLabel(id, verified, verifiedBy) {
        const response = await this.http.post(`/label/${id}/verify`, {
            verified,
            verifiedBy
        });
        return response.data;
    }
    /**
     * Search labels
     */
    async search(options) {
        const params = new URLSearchParams();
        if (options?.query)
            params.append('query', options.query);
        if (options?.category)
            params.append('category', options.category);
        if (options?.severity)
            params.append('severity', options.severity);
        if (options?.source)
            params.append('source', options.source);
        if (options?.verified !== undefined)
            params.append('verified', options.verified.toString());
        if (options?.limit)
            params.append('limit', options.limit.toString());
        if (options?.offset)
            params.append('offset', options.offset.toString());
        const response = await this.http.get(`/label/search?${params.toString()}`);
        return response.data;
    }
    /**
     * Get label categories with descriptions
     */
    async getCategories() {
        const response = await this.http.get('/label/categories');
        return response.data;
    }
    /**
     * Get label sources
     */
    async getSources() {
        const response = await this.http.get('/label/sources');
        return response.data;
    }
    /**
     * Get label statistics
     */
    async getStatistics() {
        const response = await this.http.get('/label/statistics');
        return response.data;
    }
    /**
     * Get label history for an address
     */
    async getHistory(address, options) {
        const params = new URLSearchParams();
        if (options?.limit)
            params.append('limit', options.limit.toString());
        if (options?.offset)
            params.append('offset', options.offset.toString());
        const response = await this.http.get(`/label/${address}/history?${params.toString()}`);
        return response.data;
    }
    /**
     * Report a label (for moderation)
     */
    async reportLabel(id, report) {
        const response = await this.http.post(`/label/${id}/report`, report);
        return response.data;
    }
    /**
     * Get risky label categories that should trigger blocking
     */
    async getBlockingCategories() {
        const response = await this.http.get('/label/blocking-categories');
        return response.data.categories;
    }
}
exports.LabelService = LabelService;
//# sourceMappingURL=label.js.map