"use strict";
/**
 * Dispute Service
 * Wraps /dispute endpoints for Kleros-based dispute resolution
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.DisputeService = void 0;
const base_1 = require("./base");
class DisputeService extends base_1.BaseService {
    constructor(http, events) {
        super(http, events);
    }
    /**
     * Create a new dispute
     */
    async create(request) {
        const response = await this.http.post('/dispute', request);
        this.events.emit('dispute:created', {
            id: response.data.id,
            transactionId: request.transactionId,
            category: request.category
        });
        return response.data;
    }
    /**
     * Get dispute by ID
     */
    async get(id) {
        const response = await this.http.get(`/dispute/${id}`);
        return response.data;
    }
    /**
     * Get dispute by Kleros dispute ID
     */
    async getByKlerosId(klerosDisputeId) {
        const response = await this.http.get(`/dispute/kleros/${klerosDisputeId}`);
        return response.data;
    }
    /**
     * List disputes
     */
    async list(options) {
        const params = new URLSearchParams();
        if (options?.status)
            params.append('status', options.status);
        if (options?.claimant)
            params.append('claimant', options.claimant);
        if (options?.respondent)
            params.append('respondent', options.respondent);
        if (options?.category)
            params.append('category', options.category);
        if (options?.limit)
            params.append('limit', options.limit.toString());
        if (options?.offset)
            params.append('offset', options.offset.toString());
        if (options?.sortBy)
            params.append('sortBy', options.sortBy);
        if (options?.sortOrder)
            params.append('sortOrder', options.sortOrder);
        const response = await this.http.get(`/dispute?${params.toString()}`);
        return response.data;
    }
    /**
     * Submit evidence for a dispute
     */
    async submitEvidence(disputeId, evidence) {
        const response = await this.http.post(`/dispute/${disputeId}/evidence`, evidence);
        this.events.emit('dispute:evidenceSubmitted', {
            disputeId,
            evidenceId: response.data.id,
            type: evidence.type
        });
        return response.data;
    }
    /**
     * Get evidence for a dispute
     */
    async getEvidence(disputeId) {
        const response = await this.http.get(`/dispute/${disputeId}/evidence`);
        return response.data.evidence;
    }
    /**
     * Escalate dispute to Kleros
     */
    async escalateToKleros(disputeId) {
        const response = await this.http.post(`/dispute/${disputeId}/escalate`);
        this.events.emit('dispute:escalated', {
            disputeId,
            klerosDisputeId: response.data.klerosDisputeId
        });
        return response.data;
    }
    /**
     * Get arbitration cost estimate
     */
    async getArbitrationCost(category) {
        const response = await this.http.get(`/dispute/arbitration-cost?category=${category}`);
        return response.data;
    }
    /**
     * Accept dispute resolution
     */
    async acceptResolution(disputeId) {
        const response = await this.http.post(`/dispute/${disputeId}/accept`);
        this.events.emit('dispute:resolutionAccepted', { disputeId });
        return response.data;
    }
    /**
     * Appeal dispute ruling
     */
    async appeal(disputeId, reason) {
        const response = await this.http.post(`/dispute/${disputeId}/appeal`, { reason });
        this.events.emit('dispute:appealed', {
            disputeId,
            appealId: response.data.appealId
        });
        return response.data;
    }
    /**
     * Withdraw dispute
     */
    async withdraw(disputeId, reason) {
        const response = await this.http.post(`/dispute/${disputeId}/withdraw`, { reason });
        this.events.emit('dispute:withdrawn', { disputeId });
        return response.data;
    }
    /**
     * Get dispute statistics
     */
    async getStatistics(address) {
        const url = address ? `/dispute/statistics?address=${address}` : '/dispute/statistics';
        const response = await this.http.get(url);
        return response.data;
    }
    /**
     * Get dispute timeline
     */
    async getTimeline(disputeId) {
        const response = await this.http.get(`/dispute/${disputeId}/timeline`);
        return response.data.timeline;
    }
    /**
     * Check if dispute is eligible for arbitration
     */
    async checkEligibility(disputeId) {
        const response = await this.http.get(`/dispute/${disputeId}/eligibility`);
        return response.data;
    }
}
exports.DisputeService = DisputeService;
//# sourceMappingURL=dispute.js.map