"use strict";
/**
 * EDD (Enhanced Due Diligence) Service
 * Wraps /edd endpoints for EDD case management
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.EDDService = void 0;
const base_1 = require("./base");
class EDDService extends base_1.BaseService {
    constructor(http, events) {
        super(http, events);
    }
    /**
     * Create an EDD case
     */
    async create(request) {
        const response = await this.http.post('/edd', request);
        return response.data;
    }
    /**
     * Get EDD case by ID
     */
    async get(id) {
        const response = await this.http.get(`/edd/${id}`);
        return response.data;
    }
    /**
     * Get EDD case for an address
     */
    async getByAddress(address) {
        try {
            const response = await this.http.get(`/edd/address/${address}`);
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
     * List EDD cases
     */
    async list(options) {
        const params = new URLSearchParams();
        if (options?.status)
            params.append('status', options.status);
        if (options?.trigger)
            params.append('trigger', options.trigger);
        if (options?.assignedTo)
            params.append('assignedTo', options.assignedTo);
        if (options?.priority)
            params.append('priority', options.priority);
        if (options?.limit)
            params.append('limit', options.limit.toString());
        if (options?.offset)
            params.append('offset', options.offset.toString());
        if (options?.sortBy)
            params.append('sortBy', options.sortBy);
        if (options?.sortOrder)
            params.append('sortOrder', options.sortOrder);
        const response = await this.http.get(`/edd?${params.toString()}`);
        return response.data;
    }
    /**
     * Assign EDD case to reviewer
     */
    async assign(id, assignee) {
        const response = await this.http.post(`/edd/${id}/assign`, { assignee });
        return response.data;
    }
    /**
     * Update EDD case status
     */
    async updateStatus(id, status, note) {
        const response = await this.http.put(`/edd/${id}/status`, { status, note });
        return response.data;
    }
    /**
     * Upload document for EDD case
     */
    async uploadDocument(id, document) {
        const response = await this.http.post(`/edd/${id}/documents`, document);
        return response.data;
    }
    /**
     * Get documents for EDD case
     */
    async getDocuments(id) {
        const response = await this.http.get(`/edd/${id}/documents`);
        return response.data.documents;
    }
    /**
     * Verify document
     */
    async verifyDocument(caseId, documentId, decision) {
        const response = await this.http.post(`/edd/${caseId}/documents/${documentId}/verify`, decision);
        return response.data;
    }
    /**
     * Add note to EDD case
     */
    async addNote(id, note) {
        const response = await this.http.post(`/edd/${id}/notes`, note);
        return response.data;
    }
    /**
     * Get notes for EDD case
     */
    async getNotes(id) {
        const response = await this.http.get(`/edd/${id}/notes`);
        return response.data.notes;
    }
    /**
     * Resolve EDD case
     */
    async resolve(id, resolution) {
        const response = await this.http.post(`/edd/${id}/resolve`, resolution);
        return response.data;
    }
    /**
     * Escalate EDD case
     */
    async escalate(id, reason, escalateTo) {
        const response = await this.http.post(`/edd/${id}/escalate`, { reason, escalateTo });
        return response.data;
    }
    /**
     * Get EDD case timeline
     */
    async getTimeline(id) {
        const response = await this.http.get(`/edd/${id}/timeline`);
        return response.data.timeline;
    }
    /**
     * Get EDD requirements for a trigger type
     */
    async getRequirements(trigger) {
        const response = await this.http.get(`/edd/requirements?trigger=${trigger}`);
        return response.data;
    }
    /**
     * Get EDD statistics
     */
    async getStatistics() {
        const response = await this.http.get('/edd/statistics');
        return response.data;
    }
    /**
     * Check if address requires EDD
     */
    async checkRequired(address) {
        const response = await this.http.get(`/edd/check/${address}`);
        return response.data;
    }
}
exports.EDDService = EDDService;
//# sourceMappingURL=edd.js.map