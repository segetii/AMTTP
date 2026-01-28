// backend/src/routes/explainability.ts
// Production API routes for risk explainability system
import { Router } from 'express';
import { getExplainabilityService, RiskAction } from '../risk/explainability/index.js';
import { scoreDQNTransaction } from '../risk/risk.service.js';
export const explainabilityRouter = Router();
// Singleton service instance with caching
let service = null;
function getService() {
    if (!service) {
        service = getExplainabilityService();
    }
    return service;
}
// Request ID middleware for correlation
function addRequestId(req, res, next) {
    const requestId = req.headers['x-request-id'] ||
        `exp-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    req.headers['x-request-id'] = requestId;
    res.setHeader('x-request-id', requestId);
    next();
}
explainabilityRouter.use(addRequestId);
// ═══════════════════════════════════════════════════════════════════════════
// API DOCUMENTATION
// ═══════════════════════════════════════════════════════════════════════════
explainabilityRouter.get('/', (_req, res) => {
    res.json({
        service: 'AMTTP Risk Explainability API',
        version: '1.0.0',
        description: 'Human-readable explanations for ML risk decisions',
        endpoints: {
            'POST /explain': 'Get full explanation for a risk score',
            'POST /explain/transaction': 'Score transaction AND get explanation',
            'GET /health': 'Service health check',
            'GET /metrics': 'Prometheus metrics endpoint',
            'GET /config': 'Current explainability configuration',
            'GET /typologies': 'List all detected typology patterns'
        },
        actions: {
            'ALLOW': 'Score < 0.30 - Transaction permitted',
            'REVIEW': 'Score 0.30-0.60 - Requires compliance review',
            'ESCROW': 'Score 0.60-0.85 - Funds held pending verification',
            'BLOCK': 'Score >= 0.85 - Transaction rejected'
        },
        regulatoryReferences: [
            'FATF Recommendation 16 (Wire Transfers)',
            'FCA SYSC 6.1 (Compliance)',
            'OFAC SDN List Screening',
            'AMLD6 Article 18 (EDD Requirements)'
        ]
    });
});
// ═══════════════════════════════════════════════════════════════════════════
// CORE EXPLANATION ENDPOINTS
// ═══════════════════════════════════════════════════════════════════════════
/**
 * POST /explain
 * Generate explanation for a pre-computed risk score
 *
 * Use this when you already have a risk score from the ML model
 * and just need the human-readable explanation.
 */
explainabilityRouter.post('/explain', async (req, res) => {
    const startTime = Date.now();
    const requestId = req.headers['x-request-id'];
    try {
        const { transactionId, riskScore, features, graphContext, ruleResults } = req.body;
        // Validate required fields
        if (riskScore === undefined || riskScore === null) {
            return res.status(400).json({
                error: 'Missing required field: riskScore',
                required: ['riskScore'],
                optional: ['transactionId', 'features', 'graphContext', 'ruleResults'],
                example: {
                    transactionId: 'tx-12345',
                    riskScore: 0.73,
                    features: {
                        amountEth: 15.5,
                        txCount24h: 47,
                        sanctionsMatch: false
                    }
                }
            });
        }
        if (typeof riskScore !== 'number' || riskScore < 0 || riskScore > 1) {
            return res.status(400).json({
                error: 'Invalid riskScore: must be a number between 0 and 1',
                received: riskScore
            });
        }
        // Generate explanation using service (with caching)
        const svc = getService();
        const result = await svc.explain({
            transactionId: transactionId || requestId,
            riskScore,
            features: features || {},
            graphContext: graphContext || {},
            ruleResults: ruleResults || []
        });
        const processingTime = Date.now() - startTime;
        res.json({
            success: result.success,
            requestId,
            processingTimeMs: processingTime,
            cached: result.cached,
            explanation: result.explanation,
            error: result.error
        });
    }
    catch (error) {
        console.error(`[${requestId}] Explanation error:`, error);
        const message = error instanceof Error ? error.message : String(error);
        res.status(500).json({
            success: false,
            requestId,
            error: 'Failed to generate explanation',
            message,
            fallback: {
                action: RiskAction.BLOCK,
                summary: 'Risk assessment unavailable - transaction blocked for safety'
            }
        });
    }
});
/**
 * POST /explain/transaction
 * Score a transaction AND generate full explanation in one call
 *
 * This is the primary endpoint for production use - it runs the ML model
 * and generates the human-readable explanation together.
 */
explainabilityRouter.post('/explain/transaction', async (req, res) => {
    const startTime = Date.now();
    const requestId = req.headers['x-request-id'];
    try {
        const transactionData = req.body;
        // Validate required transaction fields
        const requiredFields = ['amount', 'from', 'to'];
        const missingFields = requiredFields.filter(f => !transactionData[f]);
        if (missingFields.length > 0) {
            return res.status(400).json({
                error: 'Missing required transaction fields',
                missing: missingFields,
                required: requiredFields,
                example: {
                    amount: 15500000000000000000,
                    from: '0x742d35Cc6634C0532925a3b844Bc9e7595f1e1234',
                    to: '0x8ba1f109551bD432803012645Hac136e8e2b1234',
                    // Optional enrichment fields
                    avgAmount30d: 2.5,
                    dormancyDays: 180,
                    velocity_24h: 47,
                    sanctionsMatch: false,
                    countryCode: 'RU'
                }
            });
        }
        // Step 1: Get ML risk score
        const dqnResult = await scoreDQNTransaction(transactionData);
        // Step 2: Prepare features for explanation
        const features = {
            amountEth: transactionData.amountEth ?? transactionData.amount / 1e18,
            amountVsAverage: transactionData.avgAmount30d
                ? (transactionData.amount / 1e18) / transactionData.avgAmount30d
                : undefined,
            avgAmount30d: transactionData.avgAmount30d,
            txCount1h: transactionData.velocity_1h,
            txCount24h: transactionData.velocity_24h,
            uniqueRecipients24h: transactionData.uniqueRecipients24h,
            dormancyDays: transactionData.dormancyDays,
            sanctionsMatch: transactionData.sanctionsMatch,
            countryCode: transactionData.countryCode,
            fatfCountryRisk: transactionData.fatfCountryRisk,
            accountAgeDays: transactionData.account_age_days,
            // Model scores
            xgbProb: dqnResult.riskScore
        };
        // Step 3: Generate explanation
        const svc = getService();
        const explanationResult = await svc.explain({
            transactionId: transactionData.transactionHash || requestId,
            riskScore: dqnResult.riskScore,
            features,
            graphContext: transactionData.graphContext || {},
            ruleResults: transactionData.ruleResults || []
        });
        const processingTime = Date.now() - startTime;
        const explanation = explanationResult.explanation;
        // Return combined result
        res.json({
            success: true,
            requestId,
            processingTimeMs: processingTime,
            // Risk score from ML model
            riskScore: dqnResult.riskScore,
            confidence: dqnResult.confidence,
            modelVersion: dqnResult.modelVersion,
            // Human-readable explanation
            action: explanation?.action ?? RiskAction.BLOCK,
            summary: explanation?.summary ?? 'Explanation unavailable',
            topReasons: explanation?.topReasons ?? [],
            recommendations: explanation?.recommendations ?? [],
            // Full explanation for detailed analysis
            explanation: explanation,
            // For audit trail
            auditData: {
                transactionHash: transactionData.transactionHash,
                from: transactionData.from,
                to: transactionData.to,
                amount: transactionData.amount,
                timestamp: new Date().toISOString(),
                features: Object.keys(features).filter(k => features[k] !== undefined)
            }
        });
    }
    catch (error) {
        console.error(`[${requestId}] Transaction explanation error:`, error);
        const message = error instanceof Error ? error.message : String(error);
        res.status(500).json({
            success: false,
            requestId,
            error: 'Failed to score and explain transaction',
            message,
            fallback: {
                riskScore: 1.0,
                action: RiskAction.BLOCK,
                summary: 'Risk assessment failed - transaction blocked for safety',
                recommendations: ['Retry after system recovery', 'Contact support']
            }
        });
    }
});
// ═══════════════════════════════════════════════════════════════════════════
// OPERATIONAL ENDPOINTS
// ═══════════════════════════════════════════════════════════════════════════
/**
 * GET /health
 * Service health check for load balancers and monitoring
 */
explainabilityRouter.get('/health', async (_req, res) => {
    try {
        const svc = getService();
        const health = svc.getHealth();
        const status = health.status === 'healthy' ? 200 : 503;
        res.status(status).json({
            service: 'explainability',
            ...health,
            timestamp: new Date().toISOString()
        });
    }
    catch (error) {
        res.status(503).json({
            service: 'explainability',
            status: 'unhealthy',
            error: 'Health check failed',
            timestamp: new Date().toISOString()
        });
    }
});
/**
 * GET /metrics
 * Prometheus-compatible metrics endpoint
 */
explainabilityRouter.get('/metrics', async (_req, res) => {
    try {
        const svc = getService();
        const prometheusMetrics = svc.getPrometheusMetrics();
        // Return in Prometheus text format
        res.set('Content-Type', 'text/plain; version=0.0.4');
        res.send(prometheusMetrics);
    }
    catch (error) {
        res.status(500).send('# ERROR: Failed to collect metrics\n');
    }
});
/**
 * GET /config
 * Current explainability configuration (non-sensitive)
 */
explainabilityRouter.get('/config', (_req, res) => {
    res.json({
        version: '1.0.0',
        actionThresholds: {
            ALLOW: '< 0.30',
            REVIEW: '0.30 - 0.60',
            ESCROW: '0.60 - 0.85',
            BLOCK: '>= 0.85'
        },
        features: [
            'amountEth', 'amountVsAverage', 'txCount1h', 'txCount24h',
            'uniqueRecipients24h', 'dormancyDays', 'sanctionsMatch',
            'countryCode', 'fatfCountryRisk', 'accountAgeDays',
            'xgbProb', 'vaeAnomaly', 'gnnCommunityRisk'
        ],
        typologies: [
            'LAYERING', 'STRUCTURING', 'ROUND_TRIPPING', 'DORMANT_ACTIVATION',
            'RAPID_MOVEMENT', 'HIGH_RISK_GEOGRAPHY', 'SANCTIONS_PROXIMITY',
            'UNUSUAL_PATTERN', 'VELOCITY_ANOMALY', 'NETWORK_RISK', 'AMOUNT_ANOMALY'
        ],
        regulatoryReferences: {
            'FATF': 'Recommendations 10, 16, 19, 20',
            'FCA': 'SYSC 6.1, SUP 17',
            'OFAC': 'SDN List, 50% Rule',
            'AMLD6': 'Articles 18, 40'
        },
        caching: {
            enabled: true,
            ttlSeconds: parseInt(process.env.EXPLAINABILITY_CACHE_TTL || '300', 10),
            maxSize: parseInt(process.env.EXPLAINABILITY_CACHE_SIZE || '1000', 10)
        }
    });
});
/**
 * GET /typologies
 * List all detectable AML/fraud typologies with descriptions
 */
explainabilityRouter.get('/typologies', (_req, res) => {
    res.json({
        typologies: [
            {
                id: 'LAYERING',
                name: 'Layering / Integration',
                description: 'Multiple rapid transactions designed to obscure the origin of funds',
                indicators: ['High transaction velocity', 'Multiple recipients', 'Complex routing'],
                severity: 'HIGH',
                regulatoryRef: 'FATF Typology Report 2023'
            },
            {
                id: 'STRUCTURING',
                name: 'Structuring / Smurfing',
                description: 'Breaking large amounts into smaller transactions to avoid reporting thresholds',
                indicators: ['Transactions just below thresholds', 'Round amounts', 'Regular patterns'],
                severity: 'HIGH',
                regulatoryRef: 'AMLD6 Article 18'
            },
            {
                id: 'ROUND_TRIPPING',
                name: 'Round-Tripping',
                description: 'Funds returning to origin through complex paths',
                indicators: ['Circular fund flows', 'Same-day returns', 'Matching amounts'],
                severity: 'CRITICAL',
                regulatoryRef: 'FATF Recommendation 10'
            },
            {
                id: 'DORMANT_ACTIVATION',
                name: 'Dormant Account Activation',
                description: 'Previously inactive account suddenly showing high activity',
                indicators: ['Long dormancy period', 'Sudden large transactions', 'Pattern change'],
                severity: 'MEDIUM',
                regulatoryRef: 'FCA SYSC 6.1.1'
            },
            {
                id: 'RAPID_MOVEMENT',
                name: 'Rapid Fund Movement',
                description: 'Funds moved quickly through account without economic purpose',
                indicators: ['Short holding period', 'Multiple hops', 'No value-add activity'],
                severity: 'HIGH',
                regulatoryRef: 'FATF Recommendation 16'
            },
            {
                id: 'HIGH_RISK_GEOGRAPHY',
                name: 'High-Risk Geography',
                description: 'Transaction involves jurisdictions with weak AML controls',
                indicators: ['FATF grey/black list', 'High corruption index', 'Sanctions nexus'],
                severity: 'HIGH',
                regulatoryRef: 'FATF Statement on High-Risk Jurisdictions'
            },
            {
                id: 'SANCTIONS_PROXIMITY',
                name: 'Sanctions Proximity',
                description: 'Connection to sanctioned entities or jurisdictions',
                indicators: ['SDN list match', 'Sanctioned country', 'Known proxies'],
                severity: 'CRITICAL',
                regulatoryRef: 'OFAC SDN List'
            },
            {
                id: 'UNUSUAL_PATTERN',
                name: 'Unusual Transaction Pattern',
                description: 'Activity inconsistent with established customer profile',
                indicators: ['Deviation from baseline', 'New behavior', 'Profile mismatch'],
                severity: 'MEDIUM',
                regulatoryRef: 'FCA FG 17/6'
            },
            {
                id: 'VELOCITY_ANOMALY',
                name: 'Velocity Anomaly',
                description: 'Transaction frequency significantly exceeds normal patterns',
                indicators: ['High hourly volume', 'Burst patterns', 'Automated behavior'],
                severity: 'MEDIUM',
                regulatoryRef: 'JMLSG Guidance Part II'
            },
            {
                id: 'NETWORK_RISK',
                name: 'Network Risk Exposure',
                description: 'Counterparty or network has elevated risk indicators',
                indicators: ['High-risk counterparties', 'Cluster membership', 'Common exposure'],
                severity: 'HIGH',
                regulatoryRef: 'FATF Recommendation 19'
            },
            {
                id: 'AMOUNT_ANOMALY',
                name: 'Amount Anomaly',
                description: 'Transaction amount significantly deviates from normal range',
                indicators: ['Large single transaction', 'Deviation from average', 'Round numbers'],
                severity: 'MEDIUM',
                regulatoryRef: 'FCA SYSC 6.1.4'
            }
        ],
        totalTypologies: 11,
        lastUpdated: '2026-01-15'
    });
});
/**
 * GET /cache/stats
 * Cache statistics for monitoring
 */
explainabilityRouter.get('/cache/stats', async (_req, res) => {
    try {
        const svc = getService();
        const health = svc.getHealth();
        res.json({
            cacheSize: health.cacheSize,
            circuitBreaker: health.circuitBreaker,
            status: health.status
        });
    }
    catch (error) {
        res.status(500).json({ error: 'Failed to get cache stats' });
    }
});
/**
 * POST /cache/clear
 * Clear the explanation cache (admin operation)
 */
explainabilityRouter.post('/cache/clear', async (req, res) => {
    try {
        // In production, add authentication here
        const adminKey = req.headers['x-admin-key'];
        if (process.env.NODE_ENV === 'production' && adminKey !== process.env.ADMIN_KEY) {
            return res.status(403).json({ error: 'Unauthorized' });
        }
        // Clear cache via service method
        const svc = getService();
        svc.clearCache();
        res.json({
            success: true,
            message: 'Cache cleared',
            timestamp: new Date().toISOString()
        });
    }
    catch (error) {
        res.status(500).json({ error: 'Failed to clear cache' });
    }
});
export default explainabilityRouter;
