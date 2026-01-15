"use strict";
/**
 * KYC Service
 * Wraps /kyc endpoints for Know Your Customer verification
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.KYCService = void 0;
const base_1 = require("./base");
class KYCService extends base_1.BaseService {
    constructor(http, events) {
        super(http, events);
    }
    /**
     * Submit KYC documents for verification
     */
    async submit(submission) {
        const response = await this.http.post('/kyc/submit', submission);
        this.events.emit('kyc:submitted', {
            address: submission.address,
            documentType: submission.documentType
        });
        return response.data;
    }
    /**
     * Get KYC status for an address
     */
    async getStatus(address) {
        const response = await this.http.get(`/kyc/status/${address}`);
        return response.data;
    }
    /**
     * Check if address is KYC verified
     */
    async isVerified(address) {
        const status = await this.getStatus(address);
        return status.status === 'verified';
    }
    /**
     * Get KYC level for an address
     */
    async getLevel(address) {
        const status = await this.getStatus(address);
        return status.level;
    }
    /**
     * Upload document for KYC verification
     */
    async uploadDocument(address, document) {
        const response = await this.http.post(`/kyc/documents/${address}`, document);
        this.events.emit('kyc:documentUploaded', {
            address,
            documentType: document.type,
            documentId: response.data.documentId
        });
        return response.data;
    }
    /**
     * Get uploaded documents for an address
     */
    async getDocuments(address) {
        const response = await this.http.get(`/kyc/documents/${address}`);
        return response.data.documents;
    }
    /**
     * Get KYC requirements for a specific level
     */
    async getRequirements(level) {
        const url = level ? `/kyc/requirements?level=${level}` : '/kyc/requirements';
        const response = await this.http.get(url);
        return response.data.requirements;
    }
    /**
     * Request KYC level upgrade
     */
    async requestUpgrade(address, targetLevel) {
        const response = await this.http.post('/kyc/upgrade', { address, targetLevel });
        this.events.emit('kyc:upgradeRequested', {
            address,
            targetLevel,
            requestId: response.data.requestId
        });
        return response.data;
    }
    /**
     * Verify KYC attestation on-chain
     */
    async verifyOnChain(address, chainId) {
        const response = await this.http.get(`/kyc/verify-onchain/${address}?chainId=${chainId}`);
        return response.data;
    }
    /**
     * Renew expiring KYC
     */
    async renew(address) {
        const response = await this.http.post(`/kyc/renew/${address}`);
        this.events.emit('kyc:renewed', { address });
        return response.data;
    }
    /**
     * Check if KYC is expiring soon
     */
    async checkExpiry(address) {
        const response = await this.http.get(`/kyc/expiry/${address}`);
        return response.data;
    }
}
exports.KYCService = KYCService;
//# sourceMappingURL=kyc.js.map