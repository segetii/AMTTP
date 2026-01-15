"use strict";
/**
 * Transaction Service
 * Wraps /tx endpoints for transaction management
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.TransactionService = void 0;
const base_1 = require("./base");
class TransactionService extends base_1.BaseService {
    constructor(http, events) {
        super(http, events);
    }
    /**
     * Validate a transaction before submission
     */
    async validate(request) {
        const response = await this.http.post('/tx/validate', request);
        this.events.emit('transaction:validated', {
            from: request.from,
            to: request.to,
            valid: response.data.valid,
            riskLevel: response.data.riskLevel
        });
        return response.data;
    }
    /**
     * Submit a transaction for processing
     */
    async submit(request) {
        const response = await this.http.post('/tx/submit', request);
        this.events.emit('transaction:submitted', {
            id: response.data.id,
            from: request.from,
            to: request.to,
            status: response.data.status
        });
        return response.data;
    }
    /**
     * Get transaction by ID
     */
    async get(id) {
        const response = await this.http.get(`/tx/${id}`);
        return response.data;
    }
    /**
     * Get transaction by hash
     */
    async getByHash(hash) {
        const response = await this.http.get(`/tx/hash/${hash}`);
        return response.data;
    }
    /**
     * Get transaction history
     */
    async getHistory(options) {
        const params = new URLSearchParams();
        if (options?.address)
            params.append('address', options.address);
        if (options?.status)
            params.append('status', options.status);
        if (options?.startDate)
            params.append('startDate', options.startDate.toISOString());
        if (options?.endDate)
            params.append('endDate', options.endDate.toISOString());
        if (options?.limit)
            params.append('limit', options.limit.toString());
        if (options?.offset)
            params.append('offset', options.offset.toString());
        if (options?.sortBy)
            params.append('sortBy', options.sortBy);
        if (options?.sortOrder)
            params.append('sortOrder', options.sortOrder);
        const response = await this.http.get(`/tx/history?${params.toString()}`);
        return response.data;
    }
    /**
     * Cancel a pending transaction
     */
    async cancel(id, reason) {
        const response = await this.http.post(`/tx/${id}/cancel`, { reason });
        this.events.emit('transaction:cancelled', { id, reason });
        return response.data;
    }
    /**
     * Retry a failed transaction
     */
    async retry(id) {
        const response = await this.http.post(`/tx/${id}/retry`);
        this.events.emit('transaction:retried', { id });
        return response.data;
    }
    /**
     * Get transaction status updates
     */
    async getStatusUpdates(id) {
        const response = await this.http.get(`/tx/${id}/status-updates`);
        return response.data;
    }
    /**
     * Request expedited processing
     */
    async expedite(id) {
        const response = await this.http.post(`/tx/${id}/expedite`);
        return response.data;
    }
    /**
     * Get transaction receipt
     */
    async getReceipt(id) {
        const response = await this.http.get(`/tx/${id}/receipt`);
        return response.data;
    }
    /**
     * Estimate transaction cost
     */
    async estimateCost(request) {
        const response = await this.http.post('/tx/estimate', request);
        return response.data;
    }
    /**
     * Get pending transactions for an address
     */
    async getPending(address) {
        const response = await this.http.get(`/tx/pending/${address}`);
        return response.data.transactions;
    }
}
exports.TransactionService = TransactionService;
//# sourceMappingURL=transaction.js.map