"use strict";
/**
 * Bulk Scoring Service
 * Wraps /bulk endpoints for batch transaction scoring
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.BulkService = void 0;
const base_1 = require("./base");
class BulkService extends base_1.BaseService {
    constructor(http, events) {
        super(http, events);
    }
    /**
     * Submit bulk scoring request
     */
    async submit(request) {
        const response = await this.http.post('/bulk/submit', request);
        return response.data;
    }
    /**
     * Submit and wait for results (synchronous for small batches)
     */
    async score(request) {
        const response = await this.http.post('/bulk/score', request);
        return response.data;
    }
    /**
     * Get job status
     */
    async getStatus(jobId) {
        const response = await this.http.get(`/bulk/status/${jobId}`);
        return response.data;
    }
    /**
     * Get job results
     */
    async getResults(jobId, options) {
        const params = new URLSearchParams();
        if (options?.limit)
            params.append('limit', options.limit.toString());
        if (options?.offset)
            params.append('offset', options.offset.toString());
        if (options?.status)
            params.append('status', options.status);
        const response = await this.http.get(`/bulk/results/${jobId}?${params.toString()}`);
        return response.data;
    }
    /**
     * Cancel a bulk job
     */
    async cancel(jobId) {
        const response = await this.http.post(`/bulk/cancel/${jobId}`);
        return response.data;
    }
    /**
     * Get job history
     */
    async getHistory(options) {
        const params = new URLSearchParams();
        if (options?.limit)
            params.append('limit', options.limit.toString());
        if (options?.offset)
            params.append('offset', options.offset.toString());
        if (options?.status)
            params.append('status', options.status);
        if (options?.startDate)
            params.append('startDate', options.startDate.toISOString());
        if (options?.endDate)
            params.append('endDate', options.endDate.toISOString());
        const response = await this.http.get(`/bulk/history?${params.toString()}`);
        return response.data;
    }
    /**
     * Get bulk scoring statistics
     */
    async getStatistics() {
        const response = await this.http.get('/bulk/statistics');
        return response.data;
    }
    /**
     * Download results as CSV
     */
    async downloadResults(jobId) {
        const response = await this.http.get(`/bulk/download/${jobId}`, {
            responseType: 'blob'
        });
        return response.data;
    }
    /**
     * Retry failed transactions in a job
     */
    async retryFailed(jobId) {
        const response = await this.http.post(`/bulk/retry/${jobId}`);
        return response.data;
    }
}
exports.BulkService = BulkService;
//# sourceMappingURL=bulk.js.map