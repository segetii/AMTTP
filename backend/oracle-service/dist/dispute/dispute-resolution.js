/**
 * AMTTP P2P Dispute Resolution Service
 * Kleros integration for decentralized arbitration of failed swaps
 */
import { Router } from 'express';
import { createHash, randomUUID } from 'crypto';
// ═══════════════════════════════════════════════════════════════════════════
// DISPUTE SERVICE
// ═══════════════════════════════════════════════════════════════════════════
export class DisputeResolutionService {
    disputes = new Map();
    evidencePeriodDays = 7;
    klerosCourtId = 0; // General Court
    /**
     * Open a new dispute for a failed swap
     */
    async openDispute(params) {
        // Verify swap exists and is in disputable state
        // In production: query SwapModel from database
        const id = randomUUID();
        const now = new Date();
        const dispute = {
            id,
            swapId: params.swapId,
            transactionHash: params.transactionHash,
            claimant: params.claimant,
            respondent: params.respondent,
            amountInDispute: params.amountInDispute,
            assetType: params.assetType,
            status: 'OPEN',
            outcome: 'PENDING',
            klerosCourtId: this.klerosCourtId,
            arbitrationFee: '0.05', // ETH
            evidence: [],
            openedAt: now,
            evidenceDeadline: new Date(now.getTime() + this.evidencePeriodDays * 24 * 60 * 60 * 1000),
            reason: params.reason,
        };
        this.disputes.set(id, dispute);
        // In production: Create dispute on Kleros contract
        // dispute.klerosDisputeId = await this.createKlerosDispute(dispute);
        return dispute;
    }
    /**
     * Submit evidence for a dispute
     */
    async submitEvidence(params) {
        const dispute = this.disputes.get(params.disputeId);
        if (!dispute)
            throw new Error('Dispute not found');
        // Verify submitter is a party
        if (params.submittedBy !== dispute.claimant && params.submittedBy !== dispute.respondent) {
            throw new Error('Only parties can submit evidence');
        }
        // Check evidence period
        if (new Date() > dispute.evidenceDeadline) {
            throw new Error('Evidence period has ended');
        }
        const evidence = {
            id: randomUUID(),
            disputeId: params.disputeId,
            submittedBy: params.submittedBy,
            evidenceType: params.evidenceType,
            content: params.content,
            contentHash: createHash('sha256').update(params.content).digest('hex'),
            submittedAt: new Date(),
        };
        // In production: Upload to IPFS
        // evidence.ipfsUri = await this.uploadToIPFS(evidence);
        dispute.evidence.push(evidence);
        dispute.status = 'EVIDENCE_PERIOD';
        this.disputes.set(params.disputeId, dispute);
        return evidence;
    }
    /**
     * Move dispute to voting phase (after evidence period)
     */
    async startVoting(disputeId) {
        const dispute = this.disputes.get(disputeId);
        if (!dispute)
            throw new Error('Dispute not found');
        if (new Date() < dispute.evidenceDeadline) {
            throw new Error('Evidence period not yet ended');
        }
        dispute.status = 'VOTING';
        this.disputes.set(disputeId, dispute);
        // In production: Trigger Kleros voting
        // await this.triggerKlerosVoting(dispute.klerosDisputeId);
        return dispute;
    }
    /**
     * Resolve dispute with outcome
     */
    async resolveDispute(disputeId, outcome, resolution) {
        const dispute = this.disputes.get(disputeId);
        if (!dispute)
            throw new Error('Dispute not found');
        dispute.status = 'RESOLVED';
        dispute.outcome = outcome;
        dispute.resolution = resolution;
        dispute.resolvedAt = new Date();
        this.disputes.set(disputeId, dispute);
        // Execute resolution on-chain
        // await this.executeResolution(dispute);
        return dispute;
    }
    /**
     * Get dispute by ID
     */
    getDispute(id) {
        return this.disputes.get(id);
    }
    /**
     * Get disputes by party address
     */
    getDisputesByParty(address) {
        return Array.from(this.disputes.values())
            .filter(d => d.claimant === address || d.respondent === address);
    }
    /**
     * Get open disputes
     */
    getOpenDisputes() {
        return Array.from(this.disputes.values())
            .filter(d => d.status !== 'RESOLVED' && d.status !== 'CLOSED');
    }
    /**
     * Get dispute statistics
     */
    getStats() {
        const all = Array.from(this.disputes.values());
        return {
            total: all.length,
            open: all.filter(d => d.status === 'OPEN').length,
            evidencePeriod: all.filter(d => d.status === 'EVIDENCE_PERIOD').length,
            voting: all.filter(d => d.status === 'VOTING').length,
            resolved: all.filter(d => d.status === 'RESOLVED').length,
            outcomes: {
                claimantWins: all.filter(d => d.outcome === 'CLAIMANT_WINS').length,
                respondentWins: all.filter(d => d.outcome === 'RESPONDENT_WINS').length,
                split: all.filter(d => d.outcome === 'SPLIT').length,
                refund: all.filter(d => d.outcome === 'REFUND').length,
            },
            avgResolutionDays: this.calculateAvgResolutionDays(all),
        };
    }
    calculateAvgResolutionDays(disputes) {
        const resolved = disputes.filter(d => d.resolvedAt);
        if (resolved.length === 0)
            return 0;
        const totalDays = resolved.reduce((sum, d) => {
            const days = (d.resolvedAt.getTime() - d.openedAt.getTime()) / (24 * 60 * 60 * 1000);
            return sum + days;
        }, 0);
        return Math.round(totalDays / resolved.length * 10) / 10;
    }
}
// ═══════════════════════════════════════════════════════════════════════════
// REST API ROUTES
// ═══════════════════════════════════════════════════════════════════════════
export const disputeRouter = Router();
const disputeService = new DisputeResolutionService();
// GET /dispute - API info
disputeRouter.get('/', (req, res) => {
    res.json({
        service: 'AMTTP P2P Dispute Resolution',
        description: 'Kleros-integrated arbitration for failed swaps',
        endpoints: {
            'POST /dispute/open': 'Open a new dispute',
            'POST /dispute/:id/evidence': 'Submit evidence',
            'POST /dispute/:id/vote': 'Start voting phase',
            'POST /dispute/:id/resolve': 'Resolve dispute (admin)',
            'GET /dispute/:id': 'Get dispute details',
            'GET /dispute/party/:address': 'Get disputes by party',
            'GET /dispute/open': 'Get all open disputes',
            'GET /dispute/stats': 'Get dispute statistics',
        },
        klerosInfo: {
            courtId: 0,
            evidencePeriodDays: 7,
            arbitrationFee: '0.05 ETH',
        },
    });
});
// POST /dispute/open - Open new dispute
disputeRouter.post('/open', async (req, res) => {
    try {
        const dispute = await disputeService.openDispute({
            swapId: req.body.swapId,
            transactionHash: req.body.transactionHash,
            claimant: req.body.claimant,
            respondent: req.body.respondent,
            amountInDispute: req.body.amountInDispute,
            assetType: req.body.assetType || 'ETH',
            reason: req.body.reason,
        });
        res.status(201).json({
            success: true,
            disputeId: dispute.id,
            status: dispute.status,
            evidenceDeadline: dispute.evidenceDeadline,
            arbitrationFee: dispute.arbitrationFee,
        });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(400).json({ error: msg });
    }
});
// POST /dispute/:id/evidence - Submit evidence
disputeRouter.post('/:id/evidence', async (req, res) => {
    try {
        const evidence = await disputeService.submitEvidence({
            disputeId: req.params.id,
            submittedBy: req.body.submittedBy,
            evidenceType: req.body.evidenceType || 'TEXT',
            content: req.body.content,
        });
        res.status(201).json({
            success: true,
            evidenceId: evidence.id,
            contentHash: evidence.contentHash,
        });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(400).json({ error: msg });
    }
});
// POST /dispute/:id/vote - Start voting
disputeRouter.post('/:id/vote', async (req, res) => {
    try {
        const dispute = await disputeService.startVoting(req.params.id);
        res.json({ success: true, status: dispute.status });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(400).json({ error: msg });
    }
});
// POST /dispute/:id/resolve - Resolve dispute
disputeRouter.post('/:id/resolve', async (req, res) => {
    try {
        const dispute = await disputeService.resolveDispute(req.params.id, req.body.outcome, req.body.resolution);
        res.json({
            success: true,
            outcome: dispute.outcome,
            resolution: dispute.resolution,
            resolvedAt: dispute.resolvedAt,
        });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(400).json({ error: msg });
    }
});
// GET /dispute/:id - Get dispute
disputeRouter.get('/:id', (req, res) => {
    const dispute = disputeService.getDispute(req.params.id);
    if (!dispute) {
        res.status(404).json({ error: 'Dispute not found' });
        return;
    }
    res.json(dispute);
});
// GET /dispute/party/:address - Get by party
disputeRouter.get('/party/:address', (req, res) => {
    const disputes = disputeService.getDisputesByParty(req.params.address);
    res.json({ count: disputes.length, disputes });
});
// GET /dispute/open - Get open disputes
disputeRouter.get('/list/open', (req, res) => {
    const disputes = disputeService.getOpenDisputes();
    res.json({ count: disputes.length, disputes });
});
// GET /dispute/stats - Get statistics
disputeRouter.get('/stats', (req, res) => {
    res.json(disputeService.getStats());
});
export default disputeRouter;
