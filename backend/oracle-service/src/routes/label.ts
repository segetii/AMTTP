/**
 * AMTTP Label Routes
 * REST API for label submission with RBAC and dual-control
 */

import { Router, Request, Response, NextFunction } from 'express';
import { getLabelSafeguards, User, LabelType, Role } from '../labels/label-safeguards.js';

export const labelRouter = Router();

// Mock authentication middleware (replace with real auth in production)
function authenticateUser(req: Request, res: Response, next: NextFunction): void {
  // In production: verify JWT, session, or API key
  const userId = req.headers['x-user-id'] as string;
  const userRoles = (req.headers['x-user-roles'] as string || 'ANALYST').split(',') as Role[];
  
  if (!userId) {
    res.status(401).json({ error: 'Authentication required' });
    return;
  }

  (req as any).user = {
    id: userId,
    email: `${userId}@amttp.io`,
    roles: userRoles,
    department: 'Compliance',
    createdAt: new Date(),
    lastActive: new Date(),
    mfaEnabled: req.headers['x-mfa-verified'] === 'true',
  } as User;

  next();
}

// GET /label - API info
labelRouter.get('/', (req, res) => {
  res.json({
    message: 'AMTTP Label Submission API',
    endpoints: {
      'POST /label/submit': 'Submit a new label (requires authentication)',
      'GET /label/pending': 'Get pending labels for review',
      'POST /label/:id/approve': 'Approve a label submission',
      'POST /label/:id/reject': 'Reject a label submission',
      'GET /label/audit': 'View audit log (requires permission)',
      'GET /label/export': 'Export labels for FCA audit',
      'GET /label/stats': 'Get labeling statistics',
    },
    labelTypes: [
      'FRAUD', 'LEGITIMATE', 'SUSPICIOUS', 'FALSE_POSITIVE',
      'FALSE_NEGATIVE', 'SANCTIONED', 'PEP', 'HIGH_RISK', 'LOW_RISK',
    ],
    requiredHeaders: {
      'x-user-id': 'User identifier',
      'x-user-roles': 'Comma-separated roles (ANALYST, SENIOR_ANALYST, COMPLIANCE_OFFICER, MLRO)',
      'x-mfa-verified': 'true/false - required for high-impact labels',
    },
  });
});

// POST /label/submit - Submit a new label
labelRouter.post('/submit', authenticateUser, async (req, res) => {
  try {
    const user = (req as any).user as User;
    const safeguards = getLabelSafeguards();

    const record = await safeguards.submitLabel(user, {
      transactionId: req.body.transactionId,
      addressLabeled: req.body.addressLabeled || req.body.address,
      labelType: req.body.labelType as LabelType,
      confidence: req.body.confidence ?? 0.8,
      evidence: req.body.evidence || '',
      ipAddress: req.ip || '0.0.0.0',
      userAgent: req.headers['user-agent'] || 'unknown',
      sessionId: req.headers['x-session-id'] as string || 'unknown',
    });

    res.status(201).json({
      success: true,
      labelId: record.submission.id,
      status: record.status,
      impact: record.impact,
      requiredApprovals: record.requiredApprovals,
      message: record.impact === 'HIGH' 
        ? 'High-impact label submitted. Requires dual-control approval.'
        : 'Label submitted successfully.',
    });
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    res.status(400).json({ error: msg });
  }
});

// GET /label/pending - Get pending labels for review
labelRouter.get('/pending', authenticateUser, (req, res) => {
  try {
    const user = (req as any).user as User;
    const safeguards = getLabelSafeguards();

    if (!safeguards.hasPermission(user, 'canApproveLabels')) {
      res.status(403).json({ error: 'Insufficient permissions to view pending labels' });
      return;
    }

    const impact = req.query.impact as 'HIGH' | 'MEDIUM' | 'LOW' | undefined;
    const pending = safeguards.getPendingLabels(impact);

    res.json({
      count: pending.length,
      labels: pending.map(r => ({
        id: r.submission.id,
        transactionId: r.submission.transactionId,
        labelType: r.submission.labelType,
        confidence: r.submission.confidence,
        impact: r.impact,
        requiredApprovals: r.requiredApprovals,
        currentApprovals: r.approvals.filter(a => a.decision === 'APPROVED').length,
        submittedBy: r.submission.submittedBy,
        submittedAt: r.submission.submittedAt,
      })),
    });
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    res.status(500).json({ error: msg });
  }
});

// POST /label/:id/approve - Approve a label
labelRouter.post('/:id/approve', authenticateUser, async (req, res) => {
  try {
    const user = (req as any).user as User;
    const safeguards = getLabelSafeguards();

    const record = await safeguards.approveLabel(
      user,
      req.params.id,
      'APPROVED',
      req.body.comments || '',
      req.ip || '0.0.0.0'
    );

    res.json({
      success: true,
      labelId: req.params.id,
      status: record.status,
      approvalCount: record.approvals.filter(a => a.decision === 'APPROVED').length,
      requiredApprovals: record.requiredApprovals,
      message: record.status === 'APPROVED' 
        ? 'Label fully approved and ready for model application.'
        : `Approval recorded. ${record.requiredApprovals - record.approvals.filter(a => a.decision === 'APPROVED').length} more approval(s) needed.`,
    });
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    res.status(400).json({ error: msg });
  }
});

// POST /label/:id/reject - Reject a label
labelRouter.post('/:id/reject', authenticateUser, async (req, res) => {
  try {
    const user = (req as any).user as User;
    const safeguards = getLabelSafeguards();

    if (!req.body.comments) {
      res.status(400).json({ error: 'Rejection requires comments explaining the reason' });
      return;
    }

    const record = await safeguards.approveLabel(
      user,
      req.params.id,
      'REJECTED',
      req.body.comments,
      req.ip || '0.0.0.0'
    );

    res.json({
      success: true,
      labelId: req.params.id,
      status: record.status,
      message: 'Label rejected.',
    });
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    res.status(400).json({ error: msg });
  }
});

// GET /label/audit - View audit log
labelRouter.get('/audit', authenticateUser, (req, res) => {
  try {
    const user = (req as any).user as User;
    const safeguards = getLabelSafeguards();

    const log = safeguards.getAuditLog(user, {
      labelId: req.query.labelId as string,
      userId: req.query.userId as string,
      action: req.query.action as string,
    });

    res.json({
      count: log.length,
      entries: log,
    });
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    res.status(403).json({ error: msg });
  }
});

// GET /label/export - Export for FCA audit
labelRouter.get('/export', authenticateUser, (req, res) => {
  try {
    const user = (req as any).user as User;
    const safeguards = getLabelSafeguards();

    const export_ = safeguards.exportForAudit(user);
    res.json(export_);
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    res.status(403).json({ error: msg });
  }
});

// GET /label/stats - Get statistics
labelRouter.get('/stats', authenticateUser, (req, res) => {
  try {
    const safeguards = getLabelSafeguards();
    res.json(safeguards.getStats());
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    res.status(500).json({ error: msg });
  }
});

export default labelRouter;
