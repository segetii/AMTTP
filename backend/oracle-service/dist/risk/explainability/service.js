/**
 * Production Explainability Service
 *
 * High-level service providing:
 * - Request/response handling
 * - Caching with LRU eviction
 * - Error handling with fallbacks
 * - Metrics collection
 * - Structured logging
 * - Circuit breaker pattern
 */
import { RiskAction } from './types.js';
import { RiskExplainer } from './explainer.js';
import { loadConfig, getConfigHash } from './config.js';
import { metrics, logger } from './metrics.js';
// ═══════════════════════════════════════════════════════════════════════════════
// LRU CACHE
// ═══════════════════════════════════════════════════════════════════════════════
class LRUCache {
    cache = new Map();
    maxSize;
    ttlMs;
    constructor(options) {
        this.maxSize = options.maxSize;
        this.ttlMs = options.ttlSeconds * 1000;
    }
    get(key) {
        const entry = this.cache.get(key);
        if (!entry)
            return undefined;
        if (Date.now() > entry.expiresAt) {
            this.cache.delete(key);
            return undefined;
        }
        // Move to front (LRU behavior)
        this.cache.delete(key);
        this.cache.set(key, entry);
        return entry.value;
    }
    set(key, value) {
        // Evict if at capacity
        if (this.cache.size >= this.maxSize) {
            const oldestKey = this.cache.keys().next().value;
            if (oldestKey !== undefined) {
                this.cache.delete(oldestKey);
            }
        }
        this.cache.set(key, {
            value,
            expiresAt: Date.now() + this.ttlMs
        });
    }
    has(key) {
        const entry = this.cache.get(key);
        if (!entry)
            return false;
        if (Date.now() > entry.expiresAt) {
            this.cache.delete(key);
            return false;
        }
        return true;
    }
    clear() {
        this.cache.clear();
    }
    get size() {
        return this.cache.size;
    }
}
// ═══════════════════════════════════════════════════════════════════════════════
// CIRCUIT BREAKER
// ═══════════════════════════════════════════════════════════════════════════════
class CircuitBreaker {
    failures = 0;
    lastFailure = 0;
    state = 'CLOSED';
    threshold;
    resetTimeMs;
    constructor(options = {}) {
        this.threshold = options.threshold ?? 5;
        this.resetTimeMs = options.resetTimeMs ?? 30000; // 30 seconds
    }
    canExecute() {
        if (this.state === 'CLOSED')
            return true;
        if (this.state === 'OPEN') {
            // Check if reset time has passed
            if (Date.now() - this.lastFailure > this.resetTimeMs) {
                this.state = 'HALF_OPEN';
                return true;
            }
            return false;
        }
        // HALF_OPEN - allow one attempt
        return true;
    }
    recordSuccess() {
        this.failures = 0;
        this.state = 'CLOSED';
    }
    recordFailure() {
        this.failures++;
        this.lastFailure = Date.now();
        if (this.failures >= this.threshold) {
            this.state = 'OPEN';
        }
    }
    getState() {
        return this.state;
    }
}
// ═══════════════════════════════════════════════════════════════════════════════
// EXPLAINABILITY SERVICE
// ═══════════════════════════════════════════════════════════════════════════════
export class ExplainabilityService {
    config;
    explainer;
    cache;
    circuitBreaker;
    metrics;
    logger;
    ethPriceUsd = 2500;
    constructor(options = {}) {
        this.config = options.config ?? loadConfig();
        this.explainer = new RiskExplainer({ config: this.config });
        this.cache = new LRUCache({
            maxSize: this.config.cache.maxSize,
            ttlSeconds: this.config.cache.ttlSeconds
        });
        this.circuitBreaker = new CircuitBreaker();
        this.metrics = options.metrics ?? metrics;
        this.logger = options.logger ?? logger;
        this.logger.info('ExplainabilityService initialized', {
            configVersion: this.config.version,
            configHash: getConfigHash(this.config),
            cacheEnabled: this.config.cache.enabled,
            metricsEnabled: this.config.metrics.enabled
        });
    }
    /**
     * Update ETH price (should be called periodically)
     */
    setEthPrice(priceUsd) {
        this.ethPriceUsd = priceUsd;
        this.explainer.setEthPrice(priceUsd);
    }
    /**
     * Generate explanation for a risk decision
     */
    async explain(request) {
        const requestId = request.requestId ?? crypto.randomUUID();
        const startTime = performance.now();
        try {
            // Check circuit breaker
            if (!this.circuitBreaker.canExecute()) {
                this.logger.warn('Circuit breaker open, using fallback', { requestId });
                return this.createFallbackResponse(request, requestId, 'Circuit breaker open');
            }
            // Check cache
            if (this.config.cache.enabled) {
                const cacheKey = this.buildCacheKey(request);
                const cached = this.cache.get(cacheKey);
                if (cached) {
                    this.metrics.recordCacheHit();
                    this.logger.debug('Cache hit', { requestId, cacheKey });
                    return {
                        success: true,
                        explanation: cached,
                        cached: true,
                        requestId
                    };
                }
                this.metrics.recordCacheMiss();
            }
            // Generate explanation
            const explanation = this.explainer.explain(request.riskScore, request.features, request.graphContext ?? {}, request.ruleResults ?? [], requestId);
            // Override action if specified
            if (request.overrideAction) {
                explanation.action = request.overrideAction;
                explanation.summary = `[MANUAL OVERRIDE] ${explanation.summary}`;
            }
            // Record metrics
            this.metrics.recordExplanation(explanation);
            this.circuitBreaker.recordSuccess();
            // Cache result
            if (this.config.cache.enabled) {
                const cacheKey = this.buildCacheKey(request);
                this.cache.set(cacheKey, explanation);
            }
            // Log
            const duration = Math.round(performance.now() - startTime);
            this.logger.info('Explanation generated', {
                requestId,
                transactionId: request.transactionId,
                riskScore: request.riskScore,
                action: explanation.action,
                typologies: explanation.typologyMatches.map(t => t.typology),
                durationMs: duration
            });
            return {
                success: true,
                explanation,
                cached: false,
                requestId
            };
        }
        catch (error) {
            const err = error;
            this.circuitBreaker.recordFailure();
            this.metrics.recordError(err.name || 'UnknownError');
            this.logger.error('Explanation generation failed', {
                requestId,
                error: err.message,
                stack: err.stack
            });
            return this.createFallbackResponse(request, requestId, err.message);
        }
    }
    /**
     * Batch explanation (for bulk processing)
     */
    async explainBatch(requests) {
        // Process in parallel with concurrency limit
        const concurrency = 10;
        const results = [];
        for (let i = 0; i < requests.length; i += concurrency) {
            const batch = requests.slice(i, i + concurrency);
            const batchResults = await Promise.all(batch.map(req => this.explain(req)));
            results.push(...batchResults);
        }
        return results;
    }
    /**
     * Get service health status
     */
    getHealth() {
        const cbState = this.circuitBreaker.getState();
        return {
            status: cbState === 'CLOSED' ? 'healthy' : cbState === 'HALF_OPEN' ? 'degraded' : 'unhealthy',
            circuitBreaker: cbState,
            cacheSize: this.cache.size,
            metrics: this.metrics.getMetrics()
        };
    }
    /**
     * Get Prometheus metrics
     */
    getPrometheusMetrics() {
        return this.metrics.toPrometheus(this.config.metrics.prefix);
    }
    /**
     * Clear cache (for testing or manual invalidation)
     */
    clearCache() {
        this.cache.clear();
        this.logger.info('Cache cleared');
    }
    // ─── Private Methods ────────────────────────────────────────────────────────
    buildCacheKey(request) {
        // Create deterministic key from request
        const keyData = {
            score: Math.round(request.riskScore * 100), // Round to reduce cache variations
            amount: request.features.amountEth ?? 0,
            hops: request.graphContext?.hopsToSanctioned,
            mixer: request.graphContext?.mixerInteraction,
            rules: request.ruleResults?.filter(r => r.triggered).map(r => r.ruleType).sort()
        };
        return `${this.config.cache.keyPrefix}${JSON.stringify(keyData)}`;
    }
    createFallbackResponse(request, requestId, errorMessage) {
        // Provide safe fallback that blocks high-risk transactions
        const isHighRisk = request.riskScore >= 0.7;
        const fallbackExplanation = {
            riskScore: request.riskScore,
            action: isHighRisk ? RiskAction.BLOCK : RiskAction.REVIEW,
            summary: `Risk assessment completed in degraded mode - ${isHighRisk ? 'blocked' : 'flagged'} for safety`,
            topReasons: [
                'Risk assessment system operating in degraded mode',
                isHighRisk
                    ? 'High risk score - transaction blocked for safety'
                    : 'Transaction flagged for manual review'
            ],
            factors: [],
            typologyMatches: [],
            graphExplanation: 'Network analysis unavailable - system degraded',
            recommendations: [
                'Retry transaction after system recovery',
                'Contact support if issue persists',
                'Manual review required'
            ],
            confidence: 0.4,
            degradedMode: true,
            degradedComponents: ['explainability-service'],
            metadata: {
                explainerVersion: '2.0.0',
                generatedAt: new Date().toISOString(),
                processingTimeMs: 0,
                requestId,
                modelVersions: { explainer: 'fallback' },
                configHash: 'degraded'
            }
        };
        return {
            success: false,
            explanation: fallbackExplanation,
            error: {
                code: 'EXPLANATION_FAILED',
                message: errorMessage,
                retryable: true
            },
            cached: false,
            requestId
        };
    }
}
// ═══════════════════════════════════════════════════════════════════════════════
// SINGLETON INSTANCE
// ═══════════════════════════════════════════════════════════════════════════════
let serviceInstance = null;
export function getExplainabilityService() {
    if (!serviceInstance) {
        serviceInstance = new ExplainabilityService();
    }
    return serviceInstance;
}
export function resetExplainabilityService() {
    serviceInstance = null;
}
