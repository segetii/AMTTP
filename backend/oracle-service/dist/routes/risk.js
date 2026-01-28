// backend/src/routes/risk.ts
import { Router } from "express";
import { scoreRisk, scoreDQNTransaction, scoreRiskWithExplanation, getRiskModelStatus } from "../risk/risk.service.js";
import { RiskScoreModel } from "../db/models.js";
import { getManualReviewService, checkAndQueueForReview, MANUAL_REVIEW_THRESHOLD } from "../risk/manual-review.service.js";
export const riskRouter = Router();
// GET /risk - Information endpoint
riskRouter.get("/", (req, res) => {
    res.json({
        message: "AMTTP Risk Scoring API",
        endpoints: {
            "POST /risk/score": "Score transaction risk using DQN model (enhanced)",
            "POST /risk/score-explained": "Score with full human-readable explanation (NEW)",
            "POST /risk/dqn-score": "Direct DQN model scoring with your trained model",
            "GET /risk/models/status": "Get current model status and performance",
            "GET /risk/history/:address": "Get risk scoring history for address",
            "GET /risk/reviews": "Get pending manual reviews (high-risk transactions)",
            "GET /risk/reviews/:id": "Get specific review details",
            "POST /risk/reviews/:id/decision": "Submit review decision",
            "GET /risk/reviews/stats": "Get review queue statistics"
        },
        modelInfo: {
            version: "DQN-v1.0-real-fraud",
            performance: "F1=0.669+ (Production Ready)",
            trainingData: "28,457 real fraud transactions"
        },
        manualReviewThreshold: MANUAL_REVIEW_THRESHOLD,
        explainability: {
            endpoint: "/risk/score-explained",
            description: "Returns human-readable reasons for risk decisions",
            fullApi: "/explainability"
        }
    });
});
// Enhanced risk scoring with DQN integration
riskRouter.post("/score", async (req, res) => {
    try {
        const transactionData = req.body;
        // Use your original scoring for backward compatibility
        const basicScore = await scoreRisk(req.body);
        // Enhance with DQN model scoring
        const dqnScore = await scoreDQNTransaction(transactionData);
        // Combine scores for hybrid approach
        const hybridResult = {
            ...basicScore,
            dqnScore: dqnScore.riskScore,
            dqnConfidence: dqnScore.confidence,
            hybridScore: (basicScore.score * 0.3) + (dqnScore.riskScore * 0.7), // Weight DQN higher
            riskCategory: dqnScore.riskCategory,
            modelVersion: "hybrid-dqn-v1.0"
        };
        // Store in database
        if (transactionData.from && transactionData.to) {
            await RiskScoreModel.create({
                transactionHash: transactionData.transactionHash || null,
                fromAddress: transactionData.from,
                toAddress: transactionData.to,
                amount: transactionData.amount || 0,
                riskScore: hybridResult.hybridScore,
                riskCategory: hybridResult.riskCategory,
                confidence: dqnScore.confidence,
                modelVersion: "hybrid-dqn-v1.0",
                features: dqnScore.features,
                timestamp: new Date()
            });
        }
        res.json(hybridResult);
    }
    catch (error) {
        console.error('Enhanced risk scoring error:', error);
        const msg = error instanceof Error ? error.message : String(error);
        res.status(500).json({
            error: 'Risk scoring failed',
            message: msg
        });
    }
});
// ═══════════════════════════════════════════════════════════════════════════
// EXPLAINABILITY-ENABLED SCORING (PRODUCTION)
// ═══════════════════════════════════════════════════════════════════════════
/**
 * POST /risk/score-explained
 * Score transaction with full human-readable explanation
 *
 * This endpoint provides:
 * - Risk score from ML model
 * - Recommended action (ALLOW/REVIEW/ESCROW/BLOCK)
 * - Human-readable top reasons
 * - Detected AML typologies
 * - Compliance recommendations
 */
riskRouter.post("/score-explained", async (req, res) => {
    const startTime = Date.now();
    const requestId = req.headers['x-request-id'] ||
        `risk-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    try {
        const transactionData = req.body;
        // Validate required fields
        const requiredFields = ['amount', 'from', 'to'];
        const missingFields = requiredFields.filter(f => !transactionData[f]);
        if (missingFields.length > 0) {
            return res.status(400).json({
                error: 'Missing required fields',
                missing: missingFields,
                required: requiredFields,
                example: {
                    amount: 15500000000000000000,
                    from: '0x742d35Cc6634C0532925a3b844Bc9e7595f1e1234',
                    to: '0x8ba1f109551bD432803012645Hac136e8e2b1234'
                }
            });
        }
        // Score with full explanation
        const result = await scoreRiskWithExplanation({
            amount: transactionData.amount,
            from: transactionData.from,
            to: transactionData.to,
            transactionHash: transactionData.transactionHash,
            timestamp: transactionData.timestamp,
            // Enrichment fields for better explanations
            amountEth: transactionData.amountEth,
            avgAmount30d: transactionData.avgAmount30d,
            dormancyDays: transactionData.dormancyDays,
            uniqueRecipients24h: transactionData.uniqueRecipients24h,
            velocity_1h: transactionData.velocity_1h,
            velocity_24h: transactionData.velocity_24h,
            sanctionsMatch: transactionData.sanctionsMatch,
            countryCode: transactionData.countryCode,
            fatfCountryRisk: transactionData.fatfCountryRisk,
            account_age_days: transactionData.account_age_days,
            // Graph context if available
            graphContext: transactionData.graphContext,
            ruleResults: transactionData.ruleResults
        });
        const processingTime = Date.now() - startTime;
        // Store in database with explanation
        if (transactionData.from && transactionData.to) {
            await RiskScoreModel.create({
                transactionHash: transactionData.transactionHash || null,
                fromAddress: transactionData.from,
                toAddress: transactionData.to,
                amount: transactionData.amount || 0,
                riskScore: result.riskScore,
                riskCategory: result.action,
                confidence: result.explanation.confidence,
                modelVersion: result.modelVersion,
                explanation: {
                    action: result.action,
                    summary: result.explanation.summary,
                    topReasons: result.explanation.topReasons,
                    typologyMatches: result.explanation.typologyMatches.map(t => t.typology)
                },
                timestamp: new Date()
            });
        }
        // Check if manual review is needed
        if (result.action === 'REVIEW' || result.action === 'ESCROW') {
            await checkAndQueueForReview(result.riskScore, {
                transactionHash: transactionData.transactionHash || requestId,
                buyer: transactionData.from,
                seller: transactionData.to,
                amountWei: String(transactionData.amount),
                riskCategory: result.action,
                mlExplanation: result.explanation.summary
            });
        }
        res.json({
            success: true,
            requestId,
            processingTimeMs: processingTime,
            // Core risk assessment
            riskScore: result.riskScore,
            action: result.action,
            modelVersion: result.modelVersion,
            // Human-readable explanation
            summary: result.explanation.summary,
            topReasons: result.explanation.topReasons,
            recommendations: result.explanation.recommendations,
            // Detected patterns
            typologyMatches: result.explanation.typologyMatches,
            // Network analysis if available
            graphExplanation: result.explanation.graphExplanation,
            // Metadata for audit
            metadata: {
                confidence: result.explanation.confidence,
                degradedMode: result.explanation.degradedMode,
                generatedAt: result.explanation.metadata.generatedAt,
                explainerVersion: result.explanation.metadata.explainerVersion
            }
        });
    }
    catch (error) {
        console.error(`[${requestId}] Score-explained error:`, error);
        const msg = error instanceof Error ? error.message : String(error);
        res.status(500).json({
            success: false,
            requestId,
            error: 'Risk scoring with explanation failed',
            message: msg,
            fallback: {
                riskScore: 1.0,
                action: 'BLOCK',
                summary: 'Risk assessment failed - transaction blocked for safety'
            }
        });
    }
});
// Direct DQN model scoring endpoint
riskRouter.post("/dqn-score", async (req, res) => {
    try {
        const transactionData = req.body;
        // Validate required fields
        const requiredFields = ['amount', 'to', 'from'];
        for (const field of requiredFields) {
            if (!transactionData[field]) {
                return res.status(400).json({
                    error: `Missing required field: ${field}`,
                    required: requiredFields
                });
            }
        }
        // Score using your trained DQN model
        const dqnResult = await scoreDQNTransaction(transactionData);
        res.json({
            ...dqnResult,
            modelInfo: {
                version: "DQN-v1.0-real-fraud",
                f1Score: 0.669,
                trainingData: "28,457 real fraud transactions",
                performance: "Production Ready"
            }
        });
    }
    catch (error) {
        console.error('DQN scoring error:', error);
        const msg = error instanceof Error ? error.message : String(error);
        res.status(500).json({
            error: 'DQN scoring failed',
            message: msg
        });
    }
});
// Get model status and performance
riskRouter.get("/models/status", async (req, res) => {
    try {
        const modelStatus = await getRiskModelStatus();
        res.json(modelStatus);
    }
    catch (error) {
        console.error('Model status error:', error);
        const msg = error instanceof Error ? error.message : String(error);
        res.status(500).json({
            error: 'Failed to get model status',
            message: msg
        });
    }
});
// ═══════════════════════════════════════════════════════════════════════════
// MANUAL REVIEW ENDPOINTS (for high-risk transactions)
// ═══════════════════════════════════════════════════════════════════════════
// Get review queue statistics
riskRouter.get("/reviews/stats", async (req, res) => {
    try {
        const service = getManualReviewService();
        const stats = service.getStats();
        res.json({
            ...stats,
            threshold: MANUAL_REVIEW_THRESHOLD,
            timestamp: new Date().toISOString()
        });
    }
    catch (error) {
        console.error('Review stats error:', error);
        res.status(500).json({ error: 'Failed to get review stats' });
    }
});
// Get all pending reviews
riskRouter.get("/reviews", async (req, res) => {
    try {
        const service = getManualReviewService();
        const reviews = service.getPendingReviews();
        res.json({
            count: reviews.length,
            reviews,
            threshold: MANUAL_REVIEW_THRESHOLD
        });
    }
    catch (error) {
        console.error('Get reviews error:', error);
        res.status(500).json({ error: 'Failed to get reviews' });
    }
});
// Get specific review
riskRouter.get("/reviews/:id", async (req, res) => {
    try {
        const service = getManualReviewService();
        const review = service.getReview(req.params.id);
        if (!review) {
            return res.status(404).json({ error: 'Review not found' });
        }
        // Include audit trail
        const auditLog = service.getAuditLog(req.params.id);
        res.json({
            review,
            auditLog
        });
    }
    catch (error) {
        console.error('Get review error:', error);
        res.status(500).json({ error: 'Failed to get review' });
    }
});
// Assign review to a reviewer
riskRouter.post("/reviews/:id/assign", async (req, res) => {
    try {
        const { reviewerId } = req.body;
        if (!reviewerId) {
            return res.status(400).json({ error: 'reviewerId is required' });
        }
        const service = getManualReviewService();
        const review = await service.assignReview(req.params.id, reviewerId);
        if (!review) {
            return res.status(404).json({ error: 'Review not found or already completed' });
        }
        res.json({ success: true, review });
    }
    catch (error) {
        console.error('Assign review error:', error);
        res.status(500).json({ error: 'Failed to assign review' });
    }
});
// Start reviewing
riskRouter.post("/reviews/:id/start", async (req, res) => {
    try {
        const { reviewerId } = req.body;
        if (!reviewerId) {
            return res.status(400).json({ error: 'reviewerId is required' });
        }
        const service = getManualReviewService();
        const review = await service.startReview(req.params.id, reviewerId);
        if (!review) {
            return res.status(404).json({ error: 'Review not found or already completed' });
        }
        res.json({ success: true, review });
    }
    catch (error) {
        console.error('Start review error:', error);
        res.status(500).json({ error: 'Failed to start review' });
    }
});
// Submit review decision
riskRouter.post("/reviews/:id/decision", async (req, res) => {
    try {
        const { decision, reason, reviewerId, additionalNotes } = req.body;
        if (!decision || !reason || !reviewerId) {
            return res.status(400).json({
                error: 'Missing required fields',
                required: ['decision', 'reason', 'reviewerId'],
                validDecisions: ['approve', 'reject', 'escalate', 'request_info']
            });
        }
        if (!['approve', 'reject', 'escalate', 'request_info'].includes(decision)) {
            return res.status(400).json({
                error: 'Invalid decision',
                validDecisions: ['approve', 'reject', 'escalate', 'request_info']
            });
        }
        const service = getManualReviewService();
        const review = await service.submitDecision({
            reviewId: req.params.id,
            decision,
            reason,
            reviewerId,
            additionalNotes
        });
        if (!review) {
            return res.status(404).json({ error: 'Review not found' });
        }
        res.json({
            success: true,
            review,
            message: `Transaction ${decision === 'approve' ? 'approved' : decision === 'reject' ? 'rejected' : 'escalated'}`
        });
    }
    catch (error) {
        console.error('Submit decision error:', error);
        res.status(500).json({ error: error.message || 'Failed to submit decision' });
    }
});
// Get audit log
riskRouter.get("/reviews/:id/audit", async (req, res) => {
    try {
        const service = getManualReviewService();
        const auditLog = service.getAuditLog(req.params.id);
        res.json({ auditLog });
    }
    catch (error) {
        console.error('Get audit log error:', error);
        res.status(500).json({ error: 'Failed to get audit log' });
    }
});
