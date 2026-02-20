/**
 * Webhook Service
 * Wraps /webhook endpoints for webhook management
 */
import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
import { BaseService } from './base';
export type WebhookEventType = 'transaction.created' | 'transaction.completed' | 'transaction.failed' | 'risk.high_score' | 'risk.critical' | 'kyc.verified' | 'kyc.rejected' | 'dispute.created' | 'dispute.resolved' | 'pep.match' | 'edd.required' | 'monitoring.alert';
export interface Webhook {
    id: string;
    url: string;
    events: WebhookEventType[];
    secret?: string;
    enabled: boolean;
    description?: string;
    metadata?: Record<string, any>;
    createdAt: string;
    updatedAt: string;
    lastTriggeredAt?: string;
    failureCount: number;
}
export interface WebhookDelivery {
    id: string;
    webhookId: string;
    event: WebhookEventType;
    payload: Record<string, any>;
    status: 'pending' | 'delivered' | 'failed';
    statusCode?: number;
    responseBody?: string;
    attempts: number;
    nextRetryAt?: string;
    createdAt: string;
    deliveredAt?: string;
}
export interface WebhookCreateRequest {
    url: string;
    events: WebhookEventType[];
    description?: string;
    metadata?: Record<string, any>;
    enabled?: boolean;
}
export declare class WebhookService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Create a new webhook
     */
    create(request: WebhookCreateRequest): Promise<Webhook & {
        secret: string;
    }>;
    /**
     * List all webhooks
     */
    list(options?: {
        enabled?: boolean;
        limit?: number;
        offset?: number;
    }): Promise<{
        webhooks: Webhook[];
        total: number;
    }>;
    /**
     * Get webhook by ID
     */
    get(id: string): Promise<Webhook>;
    /**
     * Update a webhook
     */
    update(id: string, updates: Partial<WebhookCreateRequest>): Promise<Webhook>;
    /**
     * Delete a webhook
     */
    delete(id: string): Promise<void>;
    /**
     * Enable a webhook
     */
    enable(id: string): Promise<Webhook>;
    /**
     * Disable a webhook
     */
    disable(id: string): Promise<Webhook>;
    /**
     * Rotate webhook secret
     */
    rotateSecret(id: string): Promise<{
        secret: string;
    }>;
    /**
     * Test a webhook
     */
    test(id: string, event?: WebhookEventType): Promise<{
        success: boolean;
        statusCode?: number;
        responseTime?: number;
        error?: string;
    }>;
    /**
     * Get webhook deliveries
     */
    getDeliveries(webhookId: string, options?: {
        status?: 'pending' | 'delivered' | 'failed';
        event?: WebhookEventType;
        limit?: number;
        offset?: number;
        startDate?: Date;
        endDate?: Date;
    }): Promise<{
        deliveries: WebhookDelivery[];
        total: number;
    }>;
    /**
     * Retry a failed delivery
     */
    retryDelivery(webhookId: string, deliveryId: string): Promise<WebhookDelivery>;
    /**
     * Get available event types
     */
    getEventTypes(): Promise<{
        events: {
            type: WebhookEventType;
            description: string;
            samplePayload: Record<string, any>;
        }[];
    }>;
    /**
     * Get webhook statistics
     */
    getStatistics(webhookId?: string): Promise<{
        totalDeliveries: number;
        successfulDeliveries: number;
        failedDeliveries: number;
        averageResponseTime: number;
        byEvent: Record<WebhookEventType, number>;
    }>;
    /**
     * Verify webhook signature
     */
    verifySignature(payload: string, signature: string, secret: string): boolean;
}
//# sourceMappingURL=webhook.d.ts.map