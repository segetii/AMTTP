/**
 * AMTTP Client - Main entry point for SDK
 */

import axios, { AxiosInstance, AxiosError } from 'axios';
import { AMTTPError, AMTTPErrorCode } from './errors';
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

// New services
import { ComplianceService } from './services/compliance';
import { ExplainabilityService } from './services/explainability';
import { SanctionsService } from './services/sanctions';
import { GeographicRiskService } from './services/geographic';
import { IntegrityService } from './services/integrity';
import { GovernanceService } from './services/governance';
import { DashboardService } from './services/dashboard';

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

export class AMTTPClient {
  private readonly http: AxiosInstance;
  private readonly config: Required<Omit<AMTTPClientConfig, 'apiKey' | 'mevConfig'>> & Pick<AMTTPClientConfig, 'apiKey' | 'mevConfig'>;
  
  // Event emitter for SDK events
  public readonly events: EventEmitter;
  
  // Service instances
  public readonly risk: RiskService;
  public readonly kyc: KYCService;
  public readonly transactions: TransactionService;
  public readonly policy: PolicyService;
  public readonly disputes: DisputeService;
  public readonly reputation: ReputationService;
  public readonly bulk: BulkService;
  public readonly webhooks: WebhookService;
  public readonly pep: PEPService;
  public readonly edd: EDDService;
  public readonly monitoring: MonitoringService;
  public readonly labels: LabelService;
  public readonly mev: MEVProtection;
  
  // New services
  public readonly compliance: ComplianceService;
  public readonly explainability: ExplainabilityService;
  public readonly sanctions: SanctionsService;
  public readonly geographic: GeographicRiskService;
  public readonly integrity: IntegrityService;
  public readonly governance: GovernanceService;
  public readonly dashboard: DashboardService;

  constructor(config: AMTTPClientConfig) {
    this.config = {
      baseUrl: config.baseUrl,
      apiKey: config.apiKey,
      timeout: config.timeout ?? 30000,
      retryAttempts: config.retryAttempts ?? 3,
      mevConfig: config.mevConfig,
      debug: config.debug ?? false,
    };

    // Initialize HTTP client
    this.http = axios.create({
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
    this.events = new EventEmitter();

    // Initialize services
    this.risk = new RiskService(this.http, this.events);
    this.kyc = new KYCService(this.http, this.events);
    this.transactions = new TransactionService(this.http, this.events);
    this.policy = new PolicyService(this.http, this.events);
    this.disputes = new DisputeService(this.http, this.events);
    this.reputation = new ReputationService(this.http, this.events);
    this.bulk = new BulkService(this.http, this.events);
    this.webhooks = new WebhookService(this.http, this.events);
    this.pep = new PEPService(this.http, this.events);
    this.edd = new EDDService(this.http, this.events);
    this.monitoring = new MonitoringService(this.http, this.events);
    this.labels = new LabelService(this.http, this.events);
    this.mev = new MEVProtection(this.http, this.events);
    
    // Initialize new services
    this.compliance = new ComplianceService(this.http, this.events);
    this.explainability = new ExplainabilityService(this.http, this.events);
    this.sanctions = new SanctionsService(this.http, this.events);
    this.geographic = new GeographicRiskService(this.http, this.events);
    this.integrity = new IntegrityService(this.http, this.events);
    this.governance = new GovernanceService(this.http, this.events);
    this.dashboard = new DashboardService(this.http, this.events);
    
    // Apply MEV config if provided
    if (this.config.mevConfig) {
      this.mev.setConfig(this.config.mevConfig);
    }

    if (this.config.debug) {
      console.log('[AMTTP] Client initialized', { baseUrl: this.config.baseUrl });
    }
  }

  private setupInterceptors(): void {
    // Request interceptor for logging
    this.http.interceptors.request.use(
      (config) => {
        if (this.config.debug) {
          console.log(`[AMTTP] ${config.method?.toUpperCase()} ${config.url}`, config.data);
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Response interceptor for error handling and retry
    this.http.interceptors.response.use(
      (response) => {
        if (this.config.debug) {
          console.log(`[AMTTP] Response:`, response.data);
        }
        return response;
      },
      async (error: AxiosError) => {
        const amttpError = this.handleError(error);
        
        // Retry logic for retryable errors
        const config = error.config as any;
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
      }
    );
  }

  private handleError(error: AxiosError): AMTTPError {
    if (error.response) {
      return AMTTPError.fromResponse({
        status: error.response.status,
        data: error.response.data as any,
      });
    }
    
    if (error.code === 'ECONNABORTED') {
      return new AMTTPError('Request timeout', AMTTPErrorCode.TIMEOUT);
    }
    
    return new AMTTPError(
      error.message || 'Network error',
      AMTTPErrorCode.NETWORK_ERROR
    );
  }

  /**
   * Health check for the API
   */
  async healthCheck(): Promise<{ status: string; version: string }> {
    const response = await this.http.get('/health');
    return response.data;
  }

  /**
   * Get current API configuration
   */
  getConfig(): Readonly<AMTTPClientConfig> {
    return { ...this.config };
  }

  /**
   * Update API key
   */
  setApiKey(apiKey: string): void {
    this.http.defaults.headers['X-API-Key'] = apiKey;
  }
}
