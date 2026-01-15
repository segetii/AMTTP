/**
 * AMTTP Client - Main entry point for SDK
 */
import { EventEmitter } from './events';
import { RiskService } from './services/risk';
import { KYCService } from './services/kyc';
import { TransactionService } from './services/transaction';
import { PolicyService } from './services/policy';
import { DisputeService } from './services/dispute';
import { ReputationService } from './services/reputation';
import { BulkService } from './services/bulk';
import { WebhookService } from './services/webhook';
import { PEPService } from './services/pep';
import { EDDService } from './services/edd';
import { MonitoringService } from './services/monitoring';
import { LabelService } from './services/label';
import { MEVProtection, type MEVConfig } from './mev/protection';
export interface AMTTPClientConfig {
    /** Base URL for the AMTTP API */
    baseUrl: string;
    /** API key for authentication */
    apiKey?: string;
    /** Request timeout in milliseconds */
    timeout?: number;
    /** Number of retry attempts for failed requests */
    retryAttempts?: number;
    /** MEV protection configuration */
    mevConfig?: MEVConfig;
    /** Enable debug logging */
    debug?: boolean;
}
export declare class AMTTPClient {
    private readonly http;
    private readonly config;
    readonly events: EventEmitter;
    readonly risk: RiskService;
    readonly kyc: KYCService;
    readonly transactions: TransactionService;
    readonly policy: PolicyService;
    readonly disputes: DisputeService;
    readonly reputation: ReputationService;
    readonly bulk: BulkService;
    readonly webhooks: WebhookService;
    readonly pep: PEPService;
    readonly edd: EDDService;
    readonly monitoring: MonitoringService;
    readonly labels: LabelService;
    readonly mev: MEVProtection;
    constructor(config: AMTTPClientConfig);
    private setupInterceptors;
    private handleError;
    /**
     * Health check for the API
     */
    healthCheck(): Promise<{
        status: string;
        version: string;
    }>;
    /**
     * Get current API configuration
     */
    getConfig(): Readonly<AMTTPClientConfig>;
    /**
     * Update API key
     */
    setApiKey(apiKey: string): void;
}
//# sourceMappingURL=client.d.ts.map