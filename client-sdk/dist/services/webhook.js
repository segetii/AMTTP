"use strict";
/**
 * Webhook Service
 * Wraps /webhook endpoints for webhook management
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.WebhookService = void 0;
const base_1 = require("./base");
class WebhookService extends base_1.BaseService {
    constructor(http, events) {
        super(http, events);
    }
    /**
     * Create a new webhook
     */
    async create(request) {
        const response = await this.http.post('/webhook', request);
        return response.data;
    }
    /**
     * List all webhooks
     */
    async list(options) {
        const params = new URLSearchParams();
        if (options?.enabled !== undefined)
            params.append('enabled', options.enabled.toString());
        if (options?.limit)
            params.append('limit', options.limit.toString());
        if (options?.offset)
            params.append('offset', options.offset.toString());
        const response = await this.http.get(`/webhook?${params.toString()}`);
        return response.data;
    }
    /**
     * Get webhook by ID
     */
    async get(id) {
        const response = await this.http.get(`/webhook/${id}`);
        return response.data;
    }
    /**
     * Update a webhook
     */
    async update(id, updates) {
        const response = await this.http.put(`/webhook/${id}`, updates);
        return response.data;
    }
    /**
     * Delete a webhook
     */
    async delete(id) {
        await this.http.delete(`/webhook/${id}`);
    }
    /**
     * Enable a webhook
     */
    async enable(id) {
        const response = await this.http.post(`/webhook/${id}/enable`);
        return response.data;
    }
    /**
     * Disable a webhook
     */
    async disable(id) {
        const response = await this.http.post(`/webhook/${id}/disable`);
        return response.data;
    }
    /**
     * Rotate webhook secret
     */
    async rotateSecret(id) {
        const response = await this.http.post(`/webhook/${id}/rotate-secret`);
        return response.data;
    }
    /**
     * Test a webhook
     */
    async test(id, event) {
        const response = await this.http.post(`/webhook/${id}/test`, { event });
        return response.data;
    }
    /**
     * Get webhook deliveries
     */
    async getDeliveries(webhookId, options) {
        const params = new URLSearchParams();
        if (options?.status)
            params.append('status', options.status);
        if (options?.event)
            params.append('event', options.event);
        if (options?.limit)
            params.append('limit', options.limit.toString());
        if (options?.offset)
            params.append('offset', options.offset.toString());
        if (options?.startDate)
            params.append('startDate', options.startDate.toISOString());
        if (options?.endDate)
            params.append('endDate', options.endDate.toISOString());
        const response = await this.http.get(`/webhook/${webhookId}/deliveries?${params.toString()}`);
        return response.data;
    }
    /**
     * Retry a failed delivery
     */
    async retryDelivery(webhookId, deliveryId) {
        const response = await this.http.post(`/webhook/${webhookId}/deliveries/${deliveryId}/retry`);
        return response.data;
    }
    /**
     * Get available event types
     */
    async getEventTypes() {
        const response = await this.http.get('/webhook/events');
        return response.data;
    }
    /**
     * Get webhook statistics
     */
    async getStatistics(webhookId) {
        const url = webhookId ? `/webhook/${webhookId}/statistics` : '/webhook/statistics';
        const response = await this.http.get(url);
        return response.data;
    }
    /**
     * Verify webhook signature
     */
    verifySignature(payload, signature, secret) {
        // HMAC-SHA256 verification
        const crypto = require('crypto');
        const expectedSignature = crypto
            .createHmac('sha256', secret)
            .update(payload)
            .digest('hex');
        return `sha256=${expectedSignature}` === signature;
    }
}
exports.WebhookService = WebhookService;
//# sourceMappingURL=webhook.js.map