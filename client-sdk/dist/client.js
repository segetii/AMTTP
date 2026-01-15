"use strict";
/**
 * AMTTP Client - Main entry point for SDK
 */
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.AMTTPClient = void 0;
const axios_1 = __importDefault(require("axios"));
const errors_1 = require("./errors");
const events_1 = require("./events");
const risk_1 = require("./services/risk");
const kyc_1 = require("./services/kyc");
const transaction_1 = require("./services/transaction");
const policy_1 = require("./services/policy");
const dispute_1 = require("./services/dispute");
const reputation_1 = require("./services/reputation");
const bulk_1 = require("./services/bulk");
const webhook_1 = require("./services/webhook");
const pep_1 = require("./services/pep");
const edd_1 = require("./services/edd");
const monitoring_1 = require("./services/monitoring");
const label_1 = require("./services/label");
const protection_1 = require("./mev/protection");
class AMTTPClient {
    constructor(config) {
        this.config = {
            baseUrl: config.baseUrl,
            apiKey: config.apiKey,
            timeout: config.timeout ?? 30000,
            retryAttempts: config.retryAttempts ?? 3,
            mevConfig: config.mevConfig,
            debug: config.debug ?? false,
        };
        // Initialize HTTP client
        this.http = axios_1.default.create({
            baseURL: this.config.baseUrl,
            timeout: this.config.timeout,
            headers: {
                'Content-Type': 'application/json',
                ...(this.config.apiKey && { 'X-API-Key': this.config.apiKey }),
            },
        });
        // Add request/response interceptors
        this.setupInterceptors();
        // Initialize event emitter
        this.events = new events_1.EventEmitter();
        // Initialize services
        this.risk = new risk_1.RiskService(this.http, this.events);
        this.kyc = new kyc_1.KYCService(this.http, this.events);
        this.transactions = new transaction_1.TransactionService(this.http, this.events);
        this.policy = new policy_1.PolicyService(this.http, this.events);
        this.disputes = new dispute_1.DisputeService(this.http, this.events);
        this.reputation = new reputation_1.ReputationService(this.http, this.events);
        this.bulk = new bulk_1.BulkService(this.http, this.events);
        this.webhooks = new webhook_1.WebhookService(this.http, this.events);
        this.pep = new pep_1.PEPService(this.http, this.events);
        this.edd = new edd_1.EDDService(this.http, this.events);
        this.monitoring = new monitoring_1.MonitoringService(this.http, this.events);
        this.labels = new label_1.LabelService(this.http, this.events);
        this.mev = new protection_1.MEVProtection(this.http, this.events);
        // Apply MEV config if provided
        if (this.config.mevConfig) {
            this.mev.setConfig(this.config.mevConfig);
        }
        if (this.config.debug) {
            console.log('[AMTTP] Client initialized', { baseUrl: this.config.baseUrl });
        }
    }
    setupInterceptors() {
        // Request interceptor for logging
        this.http.interceptors.request.use((config) => {
            if (this.config.debug) {
                console.log(`[AMTTP] ${config.method?.toUpperCase()} ${config.url}`, config.data);
            }
            return config;
        }, (error) => Promise.reject(error));
        // Response interceptor for error handling and retry
        this.http.interceptors.response.use((response) => {
            if (this.config.debug) {
                console.log(`[AMTTP] Response:`, response.data);
            }
            return response;
        }, async (error) => {
            const amttpError = this.handleError(error);
            // Retry logic for retryable errors
            const config = error.config;
            if (amttpError.isRetryable() && config && !config._retryCount) {
                config._retryCount = config._retryCount ?? 0;
                if (config._retryCount < this.config.retryAttempts) {
                    config._retryCount++;
                    const delay = Math.pow(2, config._retryCount) * 1000;
                    if (this.config.debug) {
                        console.log(`[AMTTP] Retrying request (attempt ${config._retryCount})...`);
                    }
                    await new Promise(resolve => setTimeout(resolve, delay));
                    return this.http(config);
                }
            }
            this.events.emit('error', amttpError);
            throw amttpError;
        });
    }
    handleError(error) {
        if (error.response) {
            return errors_1.AMTTPError.fromResponse({
                status: error.response.status,
                data: error.response.data,
            });
        }
        if (error.code === 'ECONNABORTED') {
            return new errors_1.AMTTPError('Request timeout', errors_1.AMTTPErrorCode.TIMEOUT);
        }
        return new errors_1.AMTTPError(error.message || 'Network error', errors_1.AMTTPErrorCode.NETWORK_ERROR);
    }
    /**
     * Health check for the API
     */
    async healthCheck() {
        const response = await this.http.get('/health');
        return response.data;
    }
    /**
     * Get current API configuration
     */
    getConfig() {
        return { ...this.config };
    }
    /**
     * Update API key
     */
    setApiKey(apiKey) {
        this.http.defaults.headers['X-API-Key'] = apiKey;
    }
}
exports.AMTTPClient = AMTTPClient;
//# sourceMappingURL=client.js.map