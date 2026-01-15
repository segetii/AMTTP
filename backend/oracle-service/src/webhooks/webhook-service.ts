/**
 * AMTTP Webhooks & Streaming Service
 * Real-time event notifications for exchanges
 */

import { Router } from 'express';
import { createHash, randomUUID } from 'crypto';
import { EventEmitter } from 'events';
import { createHmac } from 'crypto';

// ═══════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════

export type EventType = 
  | 'TRANSACTION_SCORED'
  | 'HIGH_RISK_DETECTED'
  | 'SANCTIONS_MATCH'
  | 'PEP_MATCH'
  | 'DISPUTE_OPENED'
  | 'DISPUTE_RESOLVED'
  | 'LABEL_APPLIED'
  | 'BATCH_COMPLETED'
  | 'THRESHOLD_ALERT';

export interface WebhookSubscription {
  id: string;
  url: string;
  events: EventType[];
  secret: string;
  active: boolean;
  
  // Filtering
  minRiskScore?: number;
  addresses?: string[];
  
  // Metadata
  name: string;
  createdAt: Date;
  updatedAt: Date;
  
  // Stats
  deliveryCount: number;
  failureCount: number;
  lastDeliveryAt?: Date;
  lastFailureAt?: Date;
  consecutiveFailures: number;
}

export interface WebhookEvent {
  id: string;
  type: EventType;
  timestamp: Date;
  data: Record<string, unknown>;
}

export interface DeliveryAttempt {
  id: string;
  subscriptionId: string;
  eventId: string;
  timestamp: Date;
  success: boolean;
  statusCode?: number;
  responseTimeMs?: number;
  error?: string;
  retryCount: number;
}

// ═══════════════════════════════════════════════════════════════════════════
// WEBHOOK SERVICE
// ═══════════════════════════════════════════════════════════════════════════

export class WebhookService extends EventEmitter {
  private subscriptions: Map<string, WebhookSubscription> = new Map();
  private deliveryLog: DeliveryAttempt[] = [];
  private maxRetries = 3;
  private retryDelayMs = 5000;
  
  constructor() {
    super();
    this.setMaxListeners(100);
  }

  /**
   * Create a new webhook subscription
   */
  createSubscription(params: {
    url: string;
    events: EventType[];
    name: string;
    minRiskScore?: number;
    addresses?: string[];
  }): WebhookSubscription {
    // Validate URL
    try {
      new URL(params.url);
    } catch {
      throw new Error('Invalid webhook URL');
    }
    
    const id = randomUUID();
    const secret = randomUUID(); // Signing secret
    
    const subscription: WebhookSubscription = {
      id,
      url: params.url,
      events: params.events,
      secret,
      active: true,
      minRiskScore: params.minRiskScore,
      addresses: params.addresses,
      name: params.name,
      createdAt: new Date(),
      updatedAt: new Date(),
      deliveryCount: 0,
      failureCount: 0,
      consecutiveFailures: 0,
    };
    
    this.subscriptions.set(id, subscription);
    return subscription;
  }

  /**
   * Update subscription
   */
  updateSubscription(id: string, updates: Partial<WebhookSubscription>): WebhookSubscription {
    const subscription = this.subscriptions.get(id);
    if (!subscription) throw new Error('Subscription not found');
    
    const allowed = ['url', 'events', 'name', 'active', 'minRiskScore', 'addresses'];
    for (const key of allowed) {
      if (key in updates) {
        (subscription as any)[key] = (updates as any)[key];
      }
    }
    
    subscription.updatedAt = new Date();
    this.subscriptions.set(id, subscription);
    return subscription;
  }

  /**
   * Delete subscription
   */
  deleteSubscription(id: string): boolean {
    return this.subscriptions.delete(id);
  }

  /**
   * Get subscription by ID
   */
  getSubscription(id: string): WebhookSubscription | undefined {
    return this.subscriptions.get(id);
  }

  /**
   * List all subscriptions
   */
  listSubscriptions(): WebhookSubscription[] {
    return Array.from(this.subscriptions.values());
  }

  /**
   * Emit an event to all matching subscriptions
   */
  async emitEvent(type: EventType, data: Record<string, unknown>): Promise<void> {
    const event: WebhookEvent = {
      id: randomUUID(),
      type,
      timestamp: new Date(),
      data,
    };
    
    // Internal event for SSE
    this.emit('event', event);
    
    // Find matching subscriptions
    const matching = Array.from(this.subscriptions.values())
      .filter(sub => sub.active)
      .filter(sub => sub.events.includes(type))
      .filter(sub => this.matchesFilters(sub, data));
    
    // Deliver to each
    await Promise.all(
      matching.map(sub => this.deliver(sub, event))
    );
  }

  /**
   * Get delivery history
   */
  getDeliveryHistory(subscriptionId?: string, limit = 100): DeliveryAttempt[] {
    let history = this.deliveryLog;
    
    if (subscriptionId) {
      history = history.filter(d => d.subscriptionId === subscriptionId);
    }
    
    return history.slice(-limit);
  }

  /**
   * Rotate webhook secret
   */
  rotateSecret(id: string): string {
    const subscription = this.subscriptions.get(id);
    if (!subscription) throw new Error('Subscription not found');
    
    subscription.secret = randomUUID();
    subscription.updatedAt = new Date();
    this.subscriptions.set(id, subscription);
    
    return subscription.secret;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // PRIVATE HELPERS
  // ─────────────────────────────────────────────────────────────────────────

  private matchesFilters(sub: WebhookSubscription, data: Record<string, unknown>): boolean {
    // Check min risk score
    if (sub.minRiskScore !== undefined) {
      const score = data.riskScore as number | undefined;
      if (score === undefined || score < sub.minRiskScore) {
        return false;
      }
    }
    
    // Check addresses
    if (sub.addresses && sub.addresses.length > 0) {
      const from = (data.fromAddress as string)?.toLowerCase();
      const to = (data.toAddress as string)?.toLowerCase();
      const matches = sub.addresses.some(a => 
        a.toLowerCase() === from || a.toLowerCase() === to
      );
      if (!matches) return false;
    }
    
    return true;
  }

  private async deliver(sub: WebhookSubscription, event: WebhookEvent, retryCount = 0): Promise<void> {
    const payload = JSON.stringify(event);
    const signature = this.signPayload(payload, sub.secret);
    
    const startTime = Date.now();
    let success = false;
    let statusCode: number | undefined;
    let error: string | undefined;
    
    try {
      // In production: use fetch/axios
      // Simulating delivery for demo
      const response = await this.simulateDelivery(sub.url, payload, signature);
      statusCode = response.status;
      success = response.status >= 200 && response.status < 300;
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
    
    const responseTimeMs = Date.now() - startTime;
    
    // Log attempt
    const attempt: DeliveryAttempt = {
      id: randomUUID(),
      subscriptionId: sub.id,
      eventId: event.id,
      timestamp: new Date(),
      success,
      statusCode,
      responseTimeMs,
      error,
      retryCount,
    };
    this.deliveryLog.push(attempt);
    
    // Update subscription stats
    if (success) {
      sub.deliveryCount++;
      sub.lastDeliveryAt = new Date();
      sub.consecutiveFailures = 0;
    } else {
      sub.failureCount++;
      sub.lastFailureAt = new Date();
      sub.consecutiveFailures++;
      
      // Auto-disable after too many failures
      if (sub.consecutiveFailures >= 10) {
        sub.active = false;
      }
      
      // Retry
      if (retryCount < this.maxRetries) {
        setTimeout(() => {
          this.deliver(sub, event, retryCount + 1);
        }, this.retryDelayMs * Math.pow(2, retryCount));
      }
    }
    
    this.subscriptions.set(sub.id, sub);
  }

  private signPayload(payload: string, secret: string): string {
    return createHmac('sha256', secret)
      .update(payload)
      .digest('hex');
  }

  private async simulateDelivery(
    url: string, 
    payload: string, 
    signature: string
  ): Promise<{ status: number }> {
    // Simulate network delay
    await new Promise(resolve => setTimeout(resolve, 50 + Math.random() * 100));
    
    // 95% success rate for demo
    if (Math.random() > 0.05) {
      return { status: 200 };
    } else {
      throw new Error('Connection timeout');
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// REST API ROUTES
// ═══════════════════════════════════════════════════════════════════════════

export const webhookRouter = Router();
const webhookService = new WebhookService();

// Event types for documentation
const ALL_EVENT_TYPES: EventType[] = [
  'TRANSACTION_SCORED',
  'HIGH_RISK_DETECTED',
  'SANCTIONS_MATCH',
  'PEP_MATCH',
  'DISPUTE_OPENED',
  'DISPUTE_RESOLVED',
  'LABEL_APPLIED',
  'BATCH_COMPLETED',
  'THRESHOLD_ALERT',
];

// GET /webhook - API info
webhookRouter.get('/', (req, res) => {
  res.json({
    service: 'AMTTP Webhooks & Streaming',
    description: 'Real-time event notifications',
    eventTypes: ALL_EVENT_TYPES,
    endpoints: {
      'POST /webhook/subscribe': 'Create subscription',
      'PUT /webhook/:id': 'Update subscription',
      'DELETE /webhook/:id': 'Delete subscription',
      'GET /webhook/:id': 'Get subscription details',
      'GET /webhook/list': 'List all subscriptions',
      'POST /webhook/:id/rotate': 'Rotate signing secret',
      'GET /webhook/:id/history': 'Get delivery history',
      'GET /webhook/stream': 'SSE event stream',
    },
    security: {
      signing: 'HMAC-SHA256',
      header: 'X-AMTTP-Signature',
      verification: 'HMAC(payload, secret) === signature',
    },
  });
});

// POST /webhook/subscribe - Create subscription
webhookRouter.post('/subscribe', (req, res) => {
  try {
    const subscription = webhookService.createSubscription({
      url: req.body.url,
      events: req.body.events || ALL_EVENT_TYPES,
      name: req.body.name || 'Unnamed subscription',
      minRiskScore: req.body.minRiskScore,
      addresses: req.body.addresses,
    });
    
    res.status(201).json({
      success: true,
      subscription: {
        id: subscription.id,
        secret: subscription.secret, // Only returned on creation
        url: subscription.url,
        events: subscription.events,
        name: subscription.name,
      },
      warning: 'Store the secret securely - it will not be shown again',
    });
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    res.status(400).json({ error: msg });
  }
});

// PUT /webhook/:id - Update subscription
webhookRouter.put('/:id', (req, res) => {
  try {
    const subscription = webhookService.updateSubscription(req.params.id, req.body);
    res.json({ success: true, subscription });
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    res.status(400).json({ error: msg });
  }
});

// DELETE /webhook/:id - Delete subscription
webhookRouter.delete('/:id', (req, res) => {
  const deleted = webhookService.deleteSubscription(req.params.id);
  if (deleted) {
    res.json({ success: true });
  } else {
    res.status(404).json({ error: 'Subscription not found' });
  }
});

// GET /webhook/:id - Get subscription
webhookRouter.get('/:id', (req, res) => {
  const subscription = webhookService.getSubscription(req.params.id);
  if (!subscription) {
    res.status(404).json({ error: 'Subscription not found' });
    return;
  }
  
  // Don't expose secret
  const { secret, ...safe } = subscription;
  res.json(safe);
});

// GET /webhook/list - List subscriptions
webhookRouter.get('/list/all', (req, res) => {
  const subscriptions = webhookService.listSubscriptions().map(sub => {
    const { secret, ...safe } = sub;
    return safe;
  });
  res.json({ count: subscriptions.length, subscriptions });
});

// POST /webhook/:id/rotate - Rotate secret
webhookRouter.post('/:id/rotate', (req, res) => {
  try {
    const newSecret = webhookService.rotateSecret(req.params.id);
    res.json({
      success: true,
      secret: newSecret,
      warning: 'Store the new secret securely - it will not be shown again',
    });
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    res.status(400).json({ error: msg });
  }
});

// GET /webhook/:id/history - Delivery history
webhookRouter.get('/:id/history', (req, res) => {
  const limit = parseInt(req.query.limit as string) || 100;
  const history = webhookService.getDeliveryHistory(req.params.id, limit);
  res.json({ count: history.length, history });
});

// GET /webhook/stream - SSE stream
webhookRouter.get('/stream', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  
  // Send initial connection message
  res.write(`data: ${JSON.stringify({ type: 'connected', timestamp: new Date() })}\n\n`);
  
  // Event handler
  const handler = (event: WebhookEvent) => {
    res.write(`event: ${event.type}\n`);
    res.write(`data: ${JSON.stringify(event)}\n\n`);
  };
  
  webhookService.on('event', handler);
  
  // Cleanup on disconnect
  req.on('close', () => {
    webhookService.off('event', handler);
  });
  
  // Heartbeat every 30s
  const heartbeat = setInterval(() => {
    res.write(`: heartbeat\n\n`);
  }, 30000);
  
  req.on('close', () => clearInterval(heartbeat));
});

// POST /webhook/test - Test event emission (for development)
webhookRouter.post('/test', async (req, res) => {
  try {
    await webhookService.emitEvent(
      req.body.type || 'TRANSACTION_SCORED',
      req.body.data || { test: true, timestamp: new Date() }
    );
    res.json({ success: true, message: 'Test event emitted' });
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    res.status(400).json({ error: msg });
  }
});

// Export service for use by other modules
export { webhookService };
export default webhookRouter;
