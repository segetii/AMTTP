"use strict";
/**
 * Policy Service
 * Wraps /policy endpoints for policy management and evaluation
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.PolicyService = void 0;
const base_1 = require("./base");
class PolicyService extends base_1.BaseService {
    constructor(http, events) {
        super(http, events);
    }
    /**
     * Evaluate policies for a transaction
     */
    async evaluate(request) {
        const response = await this.http.post('/policy/evaluate', request);
        this.events.emit('policy:evaluated', {
            from: request.from,
            to: request.to,
            decision: response.data.decision,
            appliedPolicies: response.data.appliedPolicies.length
        });
        return response.data;
    }
    /**
     * Get all policies
     */
    async list(options) {
        const params = new URLSearchParams();
        if (options?.type)
            params.append('type', options.type);
        if (options?.enabled !== undefined)
            params.append('enabled', options.enabled.toString());
        if (options?.limit)
            params.append('limit', options.limit.toString());
        if (options?.offset)
            params.append('offset', options.offset.toString());
        const response = await this.http.get(`/policy?${params.toString()}`);
        return response.data;
    }
    /**
     * Get policy by ID
     */
    async get(id) {
        const response = await this.http.get(`/policy/${id}`);
        return response.data;
    }
    /**
     * Create a new policy
     */
    async create(request) {
        const response = await this.http.post('/policy', request);
        this.events.emit('policy:created', {
            id: response.data.id,
            name: response.data.name,
            type: response.data.type
        });
        return response.data;
    }
    /**
     * Update an existing policy
     */
    async update(id, updates) {
        const response = await this.http.put(`/policy/${id}`, updates);
        this.events.emit('policy:updated', { id });
        return response.data;
    }
    /**
     * Delete a policy
     */
    async delete(id) {
        await this.http.delete(`/policy/${id}`);
        this.events.emit('policy:deleted', { id });
    }
    /**
     * Enable a policy
     */
    async enable(id) {
        const response = await this.http.post(`/policy/${id}/enable`);
        return response.data;
    }
    /**
     * Disable a policy
     */
    async disable(id) {
        const response = await this.http.post(`/policy/${id}/disable`);
        return response.data;
    }
    /**
     * Test policy against sample data
     */
    async test(id, testData) {
        const response = await this.http.post(`/policy/${id}/test`, testData);
        return response.data;
    }
    /**
     * Get policy templates
     */
    async getTemplates() {
        const response = await this.http.get('/policy/templates');
        return response.data;
    }
    /**
     * Create policy from template
     */
    async createFromTemplate(templateId, overrides) {
        const response = await this.http.post(`/policy/templates/${templateId}/create`, overrides);
        return response.data;
    }
    /**
     * Get policy audit log
     */
    async getAuditLog(id, options) {
        const params = new URLSearchParams();
        if (options?.limit)
            params.append('limit', options.limit.toString());
        if (options?.offset)
            params.append('offset', options.offset.toString());
        const response = await this.http.get(`/policy/${id}/audit?${params.toString()}`);
        return response.data;
    }
    /**
     * Validate policy configuration
     */
    async validate(policy) {
        const response = await this.http.post('/policy/validate', policy);
        return response.data;
    }
}
exports.PolicyService = PolicyService;
//# sourceMappingURL=policy.js.map