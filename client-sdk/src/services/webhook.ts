/**
 * Webhook Service
 * Wraps /webhook endpoints for webhook management
 */

import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
import { BaseService } from './base';

export type WebhookEventType = 
  | 'transaction.created'
  | 'transaction.completed'
  | 'transaction.failed'
  | 'risk.high_score'
  | 'risk.critical'
  | 'kyc.verified'
  | 'kyc.rejected'
  | 'dispute.created'
  | 'dispute.resolved'
  | 'pep.match'
  | 'edd.required'
  | 'monitoring.alert';

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

export class WebhookService extends BaseService {
  constructor(http: AxiosInstance, events: EventEmitter) {
    super(http, events);
  }

  /**
   * Create a new webhook
   */
  async create(request: WebhookCreateRequest): Promise<Webhook & { secret: string }> {
    const response = await this.http.post<Webhook & { secret: string }>('/webhook', request);
    return response.data;
  }

  /**
   * List all webhooks
   */
  async list(options?: {
    enabled?: boolean;
    limit?: number;
    offset?: number;
  }): Promise<{
    webhooks: Webhook[];
    total: number;
  }> {
    const params = new URLSearchParams();
    if (options?.enabled !== undefined) params.append('enabled', options.enabled.toString());
    if (options?.limit) params.append('limit', options.limit.toString());
    if (options?.offset) params.append('offset', options.offset.toString());

    const response = await this.http.get<{
      webhooks: Webhook[];
      total: number;
    }>(`/webhook?${params.toString()}`);

    return response.data;
  }

  /**
   * Get webhook by ID
   */
  async get(id: string): Promise<Webhook> {
    const response = await this.http.get<Webhook>(`/webhook/${id}`);
    return response.data;
  }

  /**
   * Update a webhook
   */
  async update(id: string, updates: Partial<WebhookCreateRequest>): Promise<Webhook> {
    const response = await this.http.put<Webhook>(`/webhook/${id}`, updates);
    return response.data;
  }

  /**
   * Delete a webhook
   */
  async delete(id: string): Promise<void> {
    await this.http.delete(`/webhook/${id}`);
  }

  /**
   * Enable a webhook
   */
  async enable(id: string): Promise<Webhook> {
    const response = await this.http.post<Webhook>(`/webhook/${id}/enable`);
    return response.data;
  }

  /**
   * Disable a webhook
   */
  async disable(id: string): Promise<Webhook> {
    const response = await this.http.post<Webhook>(`/webhook/${id}/disable`);
    return response.data;
  }

  /**
   * Rotate webhook secret
   */
  async rotateSecret(id: string): Promise<{ secret: string }> {
    const response = await this.http.post<{ secret: string }>(`/webhook/${id}/rotate-secret`);
    return response.data;
  }

  /**
   * Test a webhook
   */
  async test(id: string, event?: WebhookEventType): Promise<{
    success: boolean;
    statusCode?: number;
    responseTime?: number;
    error?: string;
  }> {
    const response = await this.http.post(`/webhook/${id}/test`, { event });
    return response.data;
  }

  /**
   * Get webhook deliveries
   */
  async getDeliveries(webhookId: string, options?: {
    status?: 'pending' | 'delivered' | 'failed';
    event?: WebhookEventType;
    limit?: number;
    offset?: number;
    startDate?: Date;
    endDate?: Date;
  }): Promise<{
    deliveries: WebhookDelivery[];
    total: number;
  }> {
    const params = new URLSearchParams();
    if (options?.status) params.append('status', options.status);
    if (options?.event) params.append('event', options.event);
    if (options?.limit) params.append('limit', options.limit.toString());
    if (options?.offset) params.append('offset', options.offset.toString());
    if (options?.startDate) params.append('startDate', options.startDate.toISOString());
    if (options?.endDate) params.append('endDate', options.endDate.toISOString());

    const response = await this.http.get<{
      deliveries: WebhookDelivery[];
      total: number;
    }>(`/webhook/${webhookId}/deliveries?${params.toString()}`);

    return response.data;
  }

  /**
   * Retry a failed delivery
   */
  async retryDelivery(webhookId: string, deliveryId: string): Promise<WebhookDelivery> {
    const response = await this.http.post<WebhookDelivery>(
      `/webhook/${webhookId}/deliveries/${deliveryId}/retry`
    );
    return response.data;
  }

  /**
   * Get available event types
   */
  async getEventTypes(): Promise<{
    events: {
      type: WebhookEventType;
      description: string;
      samplePayload: Record<string, any>;
    }[];
  }> {
    const response = await this.http.get('/webhook/events');
    return response.data;
  }

  /**
   * Get webhook statistics
   */
  async getStatistics(webhookId?: string): Promise<{
    totalDeliveries: number;
    successfulDeliveries: number;
    failedDeliveries: number;
    averageResponseTime: number;
    byEvent: Record<WebhookEventType, number>;
  }> {
    const url = webhookId ? `/webhook/${webhookId}/statistics` : '/webhook/statistics';
    const response = await this.http.get(url);
    return response.data;
  }

  /**
   * Verify webhook signature
   */
  verifySignature(payload: string, signature: string, secret: string): boolean {
    // HMAC-SHA256 verification
    const crypto = require('crypto');
    const expectedSignature = crypto
      .createHmac('sha256', secret)
      .update(payload)
      .digest('hex');
    return `sha256=${expectedSignature}` === signature;
  }
}
