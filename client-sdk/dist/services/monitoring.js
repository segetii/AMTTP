"use strict";
/**
 * Ongoing Monitoring Service
 * Wraps /monitoring endpoints for continuous compliance monitoring
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.MonitoringService = void 0;
const base_1 = require("./base");
class MonitoringService extends base_1.BaseService {
    constructor(http, events) {
        super(http, events);
    }
    /**
     * Add address to monitoring
     */
    async addAddress(address, options) {
        const response = await this.http.post('/monitoring/addresses', {
            address,
            ...options
        });
        return response.data;
    }
    /**
     * Remove address from monitoring
     */
    async removeAddress(address) {
        await this.http.delete(`/monitoring/addresses/${address}`);
    }
    /**
     * Get monitored addresses
     */
    async getAddresses(options) {
        const params = new URLSearchParams();
        if (options?.enabled !== undefined)
            params.append('enabled', options.enabled.toString());
        if (options?.hasAlerts !== undefined)
            params.append('hasAlerts', options.hasAlerts.toString());
        if (options?.tags)
            options.tags.forEach(t => params.append('tags', t));
        if (options?.limit)
            params.append('limit', options.limit.toString());
        if (options?.offset)
            params.append('offset', options.offset.toString());
        const response = await this.http.get(`/monitoring/addresses?${params.toString()}`);
        return response.data;
    }
    /**
     * Get address monitoring status
     */
    async getAddressStatus(address) {
        const response = await this.http.get(`/monitoring/addresses/${address}`);
        return response.data;
    }
    /**
     * Get alerts
     */
    async getAlerts(options) {
        const params = new URLSearchParams();
        if (options?.address)
            params.append('address', options.address);
        if (options?.type)
            params.append('type', options.type);
        if (options?.severity)
            params.append('severity', options.severity);
        if (options?.status)
            params.append('status', options.status);
        if (options?.limit)
            params.append('limit', options.limit.toString());
        if (options?.offset)
            params.append('offset', options.offset.toString());
        if (options?.startDate)
            params.append('startDate', options.startDate.toISOString());
        if (options?.endDate)
            params.append('endDate', options.endDate.toISOString());
        const response = await this.http.get(`/monitoring/alerts?${params.toString()}`);
        return response.data;
    }
    /**
     * Get alert by ID
     */
    async getAlert(id) {
        const response = await this.http.get(`/monitoring/alerts/${id}`);
        return response.data;
    }
    /**
     * Acknowledge an alert
     */
    async acknowledgeAlert(id, acknowledgedBy) {
        const response = await this.http.post(`/monitoring/alerts/${id}/acknowledge`, {
            acknowledgedBy
        });
        return response.data;
    }
    /**
     * Resolve an alert
     */
    async resolveAlert(id, resolution) {
        const response = await this.http.post(`/monitoring/alerts/${id}/resolve`, resolution);
        return response.data;
    }
    /**
     * Dismiss an alert
     */
    async dismissAlert(id, reason, dismissedBy) {
        const response = await this.http.post(`/monitoring/alerts/${id}/dismiss`, {
            reason,
            dismissedBy
        });
        return response.data;
    }
    /**
     * Get monitoring rules
     */
    async getRules() {
        const response = await this.http.get('/monitoring/rules');
        return response.data.rules;
    }
    /**
     * Create a monitoring rule
     */
    async createRule(rule) {
        const response = await this.http.post('/monitoring/rules', rule);
        return response.data;
    }
    /**
     * Update a monitoring rule
     */
    async updateRule(id, updates) {
        const response = await this.http.put(`/monitoring/rules/${id}`, updates);
        return response.data;
    }
    /**
     * Delete a monitoring rule
     */
    async deleteRule(id) {
        await this.http.delete(`/monitoring/rules/${id}`);
    }
    /**
     * Enable/disable a rule
     */
    async toggleRule(id, enabled) {
        const response = await this.http.post(`/monitoring/rules/${id}/toggle`, { enabled });
        return response.data;
    }
    /**
     * Get monitoring configuration
     */
    async getConfig() {
        const response = await this.http.get('/monitoring/config');
        return response.data;
    }
    /**
     * Update monitoring configuration
     */
    async updateConfig(config) {
        const response = await this.http.put('/monitoring/config', config);
        return response.data;
    }
    /**
     * Trigger manual check for an address
     */
    async triggerCheck(address) {
        const response = await this.http.post(`/monitoring/check/${address}`);
        return response.data;
    }
    /**
     * Get monitoring statistics
     */
    async getStatistics() {
        const response = await this.http.get('/monitoring/statistics');
        return response.data;
    }
    /**
     * Get risk trend for an address
     */
    async getRiskTrend(address, options) {
        const params = new URLSearchParams();
        if (options?.days)
            params.append('days', options.days.toString());
        const response = await this.http.get(`/monitoring/trend/${address}?${params.toString()}`);
        return response.data;
    }
}
exports.MonitoringService = MonitoringService;
//# sourceMappingURL=monitoring.js.map