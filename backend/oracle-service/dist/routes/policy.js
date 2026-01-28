/**
 * AMTTP Policy Routes
 * REST API for policy engine operations
 */
import { Router } from 'express';
import { getPolicyEngine } from '../policy/policy-engine.js';
export const policyRouter = Router();
// GET /policy - List all policies
policyRouter.get('/', (req, res) => {
    try {
        const engine = getPolicyEngine();
        const policies = engine.getPolicies();
        res.json({
            version: engine.getVersion(),
            count: policies.length,
            policies: policies.map(p => ({
                id: p.id,
                name: p.name,
                description: p.description,
                priority: p.priority,
                action: p.action,
                sarRequired: p.sarRequired,
                freezeRequired: p.freezeRequired,
                enabled: p.enabled,
                jurisdiction: p.jurisdiction,
                effectiveDate: p.effectiveDate.toISOString(),
                expiryDate: p.expiryDate?.toISOString(),
            })),
        });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(500).json({ error: msg });
    }
});
// POST /policy/evaluate - Evaluate policies against a transaction
policyRouter.post('/evaluate', (req, res) => {
    try {
        const context = {
            riskScore: req.body.riskScore ?? 0,
            amount: req.body.amount ?? 0,
            jurisdiction: req.body.jurisdiction ?? 'UK',
            senderAddress: req.body.from ?? req.body.senderAddress ?? '',
            receiverAddress: req.body.to ?? req.body.receiverAddress ?? '',
            assetType: req.body.assetType ?? 'ETH',
            kycLevel: req.body.kycLevel ?? 'none',
            sanctionsMatch: req.body.sanctionsMatch ?? false,
            pepMatch: req.body.pepMatch ?? false,
            transactionVelocity: req.body.transactionVelocity ?? 0,
            cumulativeValue24h: req.body.cumulativeValue24h ?? 0,
            isHighRiskCountry: req.body.isHighRiskCountry ?? false,
            timestamp: new Date(),
        };
        const engine = getPolicyEngine();
        const decision = engine.evaluate(context);
        res.json({
            decision: decision.action,
            reason: decision.reason,
            triggeredPolicies: decision.triggeredPolicies,
            sarRequired: decision.sarRequired,
            freezeRequired: decision.freezeRequired,
            explanationHash: decision.explanationHash,
            policyVersion: decision.policyVersion,
            timestamp: decision.timestamp.toISOString(),
        });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(500).json({ error: msg });
    }
});
// PUT /policy/:id/enable - Enable a policy
policyRouter.put('/:id/enable', (req, res) => {
    try {
        const engine = getPolicyEngine();
        const success = engine.setEnabled(req.params.id, true);
        if (success) {
            res.json({ success: true, policyId: req.params.id, enabled: true });
        }
        else {
            res.status(404).json({ error: `Policy ${req.params.id} not found` });
        }
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(500).json({ error: msg });
    }
});
// PUT /policy/:id/disable - Disable a policy
policyRouter.put('/:id/disable', (req, res) => {
    try {
        const engine = getPolicyEngine();
        const success = engine.setEnabled(req.params.id, false);
        if (success) {
            res.json({ success: true, policyId: req.params.id, enabled: false });
        }
        else {
            res.status(404).json({ error: `Policy ${req.params.id} not found` });
        }
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(500).json({ error: msg });
    }
});
// GET /policy/export - Export policies for audit
policyRouter.get('/export', (req, res) => {
    try {
        const engine = getPolicyEngine();
        const export_ = engine.exportForAudit();
        res.json(export_);
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(500).json({ error: msg });
    }
});
// GET /policy/version - Get current policy version
policyRouter.get('/version', (req, res) => {
    try {
        const engine = getPolicyEngine();
        res.json({ version: engine.getVersion() });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(500).json({ error: msg });
    }
});
export default policyRouter;
