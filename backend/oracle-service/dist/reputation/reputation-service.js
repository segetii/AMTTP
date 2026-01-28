/**
 * AMTTP Reputation System
 * On-chain reputation tracking for repeat good actors
 */
import { Router } from 'express';
import { randomUUID } from 'crypto';
// ═══════════════════════════════════════════════════════════════════════════
// TIER THRESHOLDS
// ═══════════════════════════════════════════════════════════════════════════
const TIER_THRESHOLDS = {
    BRONZE: 0,
    SILVER: 25,
    GOLD: 50,
    PLATINUM: 75,
    DIAMOND: 90,
};
const TIER_BENEFITS = {
    BRONZE: { feeDiscount: 0, priorityQueue: false, maxSwapUSD: 1000 },
    SILVER: { feeDiscount: 5, priorityQueue: false, maxSwapUSD: 5000 },
    GOLD: { feeDiscount: 10, priorityQueue: true, maxSwapUSD: 25000 },
    PLATINUM: { feeDiscount: 15, priorityQueue: true, maxSwapUSD: 100000 },
    DIAMOND: { feeDiscount: 25, priorityQueue: true, maxSwapUSD: 500000 },
};
// ═══════════════════════════════════════════════════════════════════════════
// REPUTATION SERVICE
// ═══════════════════════════════════════════════════════════════════════════
export class ReputationService {
    scores = new Map();
    events = [];
    /**
     * Initialize or get reputation for an address
     */
    getOrCreateReputation(address) {
        const normalizedAddress = address.toLowerCase();
        if (!this.scores.has(normalizedAddress)) {
            const newScore = {
                address: normalizedAddress,
                totalTransactions: 0,
                successfulTransactions: 0,
                failedTransactions: 0,
                disputesAsClaimant: 0,
                disputesAsRespondent: 0,
                disputesWon: 0,
                disputesLost: 0,
                overallScore: 50, // Start neutral
                reliabilityScore: 50,
                speedScore: 50,
                disputeScore: 100, // Perfect until disputes
                tier: 'BRONZE',
                totalVolumeUSD: 0,
                avgTransactionUSD: 0,
                accountAgedays: 0,
                lastActiveAt: new Date(),
                isKYCVerified: false,
                isPEPChecked: false,
                stakedAmount: '0',
                slashingRisk: 0,
            };
            this.scores.set(normalizedAddress, newScore);
        }
        return this.scores.get(normalizedAddress);
    }
    /**
     * Record a successful transaction
     */
    recordSuccessfulTransaction(params) {
        const score = this.getOrCreateReputation(params.address);
        score.totalTransactions++;
        score.successfulTransactions++;
        score.totalVolumeUSD += params.amountUSD;
        score.avgTransactionUSD = score.totalVolumeUSD / score.totalTransactions;
        score.lastActiveAt = new Date();
        if (!score.firstTransactionAt) {
            score.firstTransactionAt = new Date();
        }
        // Update reliability score
        score.reliabilityScore = Math.min(100, (score.successfulTransactions / score.totalTransactions) * 100);
        // Update speed score (faster = better, assuming 60 min baseline)
        const speedBonus = Math.max(0, (60 - params.completionTimeMinutes) / 60 * 20);
        score.speedScore = Math.min(100, score.speedScore + speedBonus * 0.1);
        // Recalculate overall
        this.recalculateOverall(score);
        // Log event
        this.logEvent({
            address: params.address,
            eventType: 'TRANSACTION',
            impact: 2,
            reason: `Successful transaction of $${params.amountUSD}`,
            transactionHash: params.transactionHash,
        });
        this.scores.set(params.address.toLowerCase(), score);
        return score;
    }
    /**
     * Record a failed transaction
     */
    recordFailedTransaction(params) {
        const score = this.getOrCreateReputation(params.address);
        score.totalTransactions++;
        score.failedTransactions++;
        score.lastActiveAt = new Date();
        // Impact reliability
        score.reliabilityScore = Math.max(0, (score.successfulTransactions / score.totalTransactions) * 100);
        this.recalculateOverall(score);
        this.logEvent({
            address: params.address,
            eventType: 'TRANSACTION',
            impact: -5,
            reason: `Failed transaction: ${params.reason}`,
            transactionHash: params.transactionHash,
        });
        this.scores.set(params.address.toLowerCase(), score);
        return score;
    }
    /**
     * Record dispute outcome
     */
    recordDisputeOutcome(params) {
        const score = this.getOrCreateReputation(params.address);
        if (params.role === 'CLAIMANT') {
            score.disputesAsClaimant++;
        }
        else {
            score.disputesAsRespondent++;
        }
        if (params.won) {
            score.disputesWon++;
        }
        else {
            score.disputesLost++;
            // Losing a dispute as respondent is worse
            if (params.role === 'RESPONDENT') {
                score.disputeScore = Math.max(0, score.disputeScore - 20);
                score.slashingRisk = Math.min(100, score.slashingRisk + 10);
            }
        }
        this.recalculateOverall(score);
        this.logEvent({
            address: params.address,
            eventType: 'DISPUTE',
            impact: params.won ? 5 : -10,
            reason: `Dispute ${params.disputeId}: ${params.won ? 'won' : 'lost'} as ${params.role}`,
        });
        this.scores.set(params.address.toLowerCase(), score);
        return score;
    }
    /**
     * Record stake commitment
     */
    recordStake(params) {
        const score = this.getOrCreateReputation(params.address);
        const currentStake = parseFloat(score.stakedAmount);
        const newStake = parseFloat(params.amount);
        score.stakedAmount = (currentStake + newStake).toString();
        // Staking improves overall score
        const stakeBonus = Math.min(10, newStake * 2);
        score.overallScore = Math.min(100, score.overallScore + stakeBonus);
        this.recalculateOverall(score);
        this.logEvent({
            address: params.address,
            eventType: 'STAKE',
            impact: stakeBonus,
            reason: `Staked ${params.amount} ETH`,
            transactionHash: params.transactionHash,
        });
        this.scores.set(params.address.toLowerCase(), score);
        return score;
    }
    /**
     * Apply slashing penalty
     */
    applySlashing(params) {
        const score = this.getOrCreateReputation(params.address);
        const currentStake = parseFloat(score.stakedAmount);
        const slashAmount = parseFloat(params.amount);
        score.stakedAmount = Math.max(0, currentStake - slashAmount).toString();
        // Severe reputation penalty
        score.overallScore = Math.max(0, score.overallScore - 20);
        score.disputeScore = Math.max(0, score.disputeScore - 30);
        score.slashingRisk = Math.min(100, score.slashingRisk + 25);
        this.recalculateOverall(score);
        this.logEvent({
            address: params.address,
            eventType: 'SLASH',
            impact: -20,
            reason: `Slashed ${params.amount} ETH: ${params.reason}`,
            transactionHash: params.transactionHash,
        });
        this.scores.set(params.address.toLowerCase(), score);
        return score;
    }
    /**
     * Record KYC/PEP verification
     */
    recordVerification(params) {
        const score = this.getOrCreateReputation(params.address);
        if (params.verificationType === 'KYC') {
            score.isKYCVerified = params.passed;
        }
        else {
            score.isPEPChecked = true;
        }
        // Verification improves trust
        if (params.passed) {
            score.overallScore = Math.min(100, score.overallScore + 5);
        }
        this.recalculateOverall(score);
        this.logEvent({
            address: params.address,
            eventType: 'VERIFICATION',
            impact: params.passed ? 5 : 0,
            reason: `${params.verificationType} verification: ${params.passed ? 'passed' : 'checked'}`,
        });
        this.scores.set(params.address.toLowerCase(), score);
        return score;
    }
    /**
     * Get tier benefits for an address
     */
    getTierBenefits(address) {
        const score = this.getOrCreateReputation(address);
        return { ...TIER_BENEFITS[score.tier], tier: score.tier };
    }
    /**
     * Get reputation events for an address
     */
    getEvents(address, limit = 50) {
        return this.events
            .filter(e => e.address.toLowerCase() === address.toLowerCase())
            .slice(-limit);
    }
    /**
     * Get leaderboard
     */
    getLeaderboard(limit = 100) {
        return Array.from(this.scores.values())
            .sort((a, b) => b.overallScore - a.overallScore)
            .slice(0, limit);
    }
    /**
     * Get global statistics
     */
    getGlobalStats() {
        const all = Array.from(this.scores.values());
        return {
            totalUsers: all.length,
            byTier: {
                BRONZE: all.filter(s => s.tier === 'BRONZE').length,
                SILVER: all.filter(s => s.tier === 'SILVER').length,
                GOLD: all.filter(s => s.tier === 'GOLD').length,
                PLATINUM: all.filter(s => s.tier === 'PLATINUM').length,
                DIAMOND: all.filter(s => s.tier === 'DIAMOND').length,
            },
            avgScore: all.reduce((s, a) => s + a.overallScore, 0) / all.length || 0,
            totalVolume: all.reduce((s, a) => s + a.totalVolumeUSD, 0),
            totalStaked: all.reduce((s, a) => s + parseFloat(a.stakedAmount), 0),
            kycVerified: all.filter(s => s.isKYCVerified).length,
        };
    }
    // ─────────────────────────────────────────────────────────────────────────
    // PRIVATE HELPERS
    // ─────────────────────────────────────────────────────────────────────────
    recalculateOverall(score) {
        // Weighted average
        score.overallScore = Math.round(score.reliabilityScore * 0.4 +
            score.speedScore * 0.2 +
            score.disputeScore * 0.4);
        // Update account age
        if (score.firstTransactionAt) {
            score.accountAgedays = Math.floor((Date.now() - score.firstTransactionAt.getTime()) / (24 * 60 * 60 * 1000));
        }
        // Update tier
        if (score.overallScore >= TIER_THRESHOLDS.DIAMOND) {
            score.tier = 'DIAMOND';
        }
        else if (score.overallScore >= TIER_THRESHOLDS.PLATINUM) {
            score.tier = 'PLATINUM';
        }
        else if (score.overallScore >= TIER_THRESHOLDS.GOLD) {
            score.tier = 'GOLD';
        }
        else if (score.overallScore >= TIER_THRESHOLDS.SILVER) {
            score.tier = 'SILVER';
        }
        else {
            score.tier = 'BRONZE';
        }
    }
    logEvent(event) {
        this.events.push({
            ...event,
            id: randomUUID(),
            timestamp: new Date(),
        });
    }
}
// ═══════════════════════════════════════════════════════════════════════════
// REST API ROUTES
// ═══════════════════════════════════════════════════════════════════════════
export const reputationRouter = Router();
const reputationService = new ReputationService();
// GET /reputation - API info
reputationRouter.get('/', (req, res) => {
    res.json({
        service: 'AMTTP Reputation System',
        description: 'On-chain reputation tracking for P2P participants',
        tiers: TIER_THRESHOLDS,
        benefits: TIER_BENEFITS,
        endpoints: {
            'GET /reputation/:address': 'Get reputation score',
            'GET /reputation/:address/benefits': 'Get tier benefits',
            'GET /reputation/:address/events': 'Get reputation history',
            'POST /reputation/transaction': 'Record transaction',
            'POST /reputation/dispute': 'Record dispute outcome',
            'POST /reputation/stake': 'Record stake',
            'POST /reputation/verify': 'Record verification',
            'GET /reputation/leaderboard': 'Get top users',
            'GET /reputation/stats': 'Get global statistics',
        },
    });
});
// GET /reputation/:address - Get reputation
reputationRouter.get('/:address', (req, res) => {
    const score = reputationService.getOrCreateReputation(req.params.address);
    res.json(score);
});
// GET /reputation/:address/benefits - Get benefits
reputationRouter.get('/:address/benefits', (req, res) => {
    const benefits = reputationService.getTierBenefits(req.params.address);
    res.json(benefits);
});
// GET /reputation/:address/events - Get history
reputationRouter.get('/:address/events', (req, res) => {
    const limit = parseInt(req.query.limit) || 50;
    const events = reputationService.getEvents(req.params.address, limit);
    res.json({ count: events.length, events });
});
// POST /reputation/transaction - Record transaction
reputationRouter.post('/transaction', (req, res) => {
    try {
        const score = req.body.success
            ? reputationService.recordSuccessfulTransaction({
                address: req.body.address,
                transactionHash: req.body.transactionHash,
                amountUSD: req.body.amountUSD,
                completionTimeMinutes: req.body.completionTimeMinutes || 30,
            })
            : reputationService.recordFailedTransaction({
                address: req.body.address,
                transactionHash: req.body.transactionHash,
                reason: req.body.reason || 'Unknown',
            });
        res.json({
            success: true,
            newScore: score.overallScore,
            tier: score.tier,
        });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(400).json({ error: msg });
    }
});
// POST /reputation/dispute - Record dispute
reputationRouter.post('/dispute', (req, res) => {
    try {
        const score = reputationService.recordDisputeOutcome({
            address: req.body.address,
            role: req.body.role,
            won: req.body.won,
            disputeId: req.body.disputeId,
        });
        res.json({
            success: true,
            newScore: score.overallScore,
            disputeScore: score.disputeScore,
            tier: score.tier,
        });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(400).json({ error: msg });
    }
});
// POST /reputation/stake - Record stake
reputationRouter.post('/stake', (req, res) => {
    try {
        const score = reputationService.recordStake({
            address: req.body.address,
            amount: req.body.amount,
            transactionHash: req.body.transactionHash,
        });
        res.json({
            success: true,
            stakedAmount: score.stakedAmount,
            newScore: score.overallScore,
        });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(400).json({ error: msg });
    }
});
// POST /reputation/slash - Apply slashing
reputationRouter.post('/slash', (req, res) => {
    try {
        const score = reputationService.applySlashing({
            address: req.body.address,
            amount: req.body.amount,
            reason: req.body.reason,
            transactionHash: req.body.transactionHash,
        });
        res.json({
            success: true,
            remainingStake: score.stakedAmount,
            newScore: score.overallScore,
            slashingRisk: score.slashingRisk,
        });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(400).json({ error: msg });
    }
});
// POST /reputation/verify - Record verification
reputationRouter.post('/verify', (req, res) => {
    try {
        const score = reputationService.recordVerification({
            address: req.body.address,
            verificationType: req.body.verificationType,
            passed: req.body.passed,
        });
        res.json({
            success: true,
            isKYCVerified: score.isKYCVerified,
            isPEPChecked: score.isPEPChecked,
            newScore: score.overallScore,
        });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(400).json({ error: msg });
    }
});
// GET /reputation/leaderboard - Get leaderboard
reputationRouter.get('/list/leaderboard', (req, res) => {
    const limit = parseInt(req.query.limit) || 100;
    const leaders = reputationService.getLeaderboard(limit);
    res.json({ count: leaders.length, leaderboard: leaders });
});
// GET /reputation/stats - Get global stats
reputationRouter.get('/global/stats', (req, res) => {
    res.json(reputationService.getGlobalStats());
});
export default reputationRouter;
