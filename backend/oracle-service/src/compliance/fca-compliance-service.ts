/**
 * AMTTP FCA Compliance Service - Air-gapped Architecture
 * Separate service with isolated DB schema and write-only ingestion
 * 
 * This service runs independently from the main oracle service to ensure:
 * 1. Regulatory isolation - compliance data cannot be modified by decision logic
 * 2. Audit integrity - immutable write-only ingestion from decision layer
 * 3. Credential separation - different access controls for compliance staff
 * 4. Schema isolation - separate database/schema for compliance data
 */

import express, { Request, Response, NextFunction } from 'express';
import { createHash, randomUUID } from 'crypto';

// ═══════════════════════════════════════════════════════════════════════════
// TYPES - COMPLIANCE DOMAIN (Isolated from Decision Domain)
// ═══════════════════════════════════════════════════════════════════════════

interface ComplianceDecisionRecord {
  id: string;
  // Ingested from decision layer (write-only)
  decisionId: string;
  transactionHash?: string;
  fromAddress: string;
  toAddress: string;
  amount: number;
  assetType: string;
  jurisdiction: string;
  
  // Decision outcome
  decision: 'ALLOW' | 'BLOCK' | 'REVIEW' | 'ESCALATE';
  riskScore: number;
  triggeredPolicies: string[];
  sarRequired: boolean;
  freezeRequired: boolean;
  
  // Provenance
  explanationHash: string;
  policyVersion: string;
  modelVersion: string;
  oracleSignature: string;
  
  // Timestamps
  decisionTimestamp: Date;
  ingestedAt: Date;
  
  // Compliance processing
  complianceStatus: 'PENDING' | 'REVIEWED' | 'SAR_FILED' | 'CLOSED';
  reviewedBy?: string;
  reviewedAt?: Date;
  sarId?: string;
}

interface SARRecord {
  id: string;
  decisionRecordId: string;
  sarType: string;
  reportingEntity: string;
  filedAt: Date;
  filedBy: string;
  ncaReference?: string;
  status: 'DRAFT' | 'SUBMITTED' | 'ACKNOWLEDGED' | 'CLOSED';
  narrative: string;
  evidenceHashes: string[];
  retentionExpiry: Date; // 5+ years
}

interface AuditEntry {
  id: string;
  timestamp: Date;
  action: string;
  entityType: string;
  entityId: string;
  userId: string;
  details: object;
  ipAddress: string;
  integrityHash: string;
  previousHash: string;
}

// ═══════════════════════════════════════════════════════════════════════════
// ISOLATED DATA STORE (In production: separate PostgreSQL schema)
// ═══════════════════════════════════════════════════════════════════════════

class ComplianceDataStore {
  private decisions: Map<string, ComplianceDecisionRecord> = new Map();
  private sars: Map<string, SARRecord> = new Map();
  private auditChain: AuditEntry[] = [];
  private lastAuditHash: string = '0'.repeat(64);

  // ── WRITE-ONLY INGESTION ────────────────────────────────────────────────
  
  /**
   * Ingest decision from main oracle service (write-only, no modification)
   * This is the ONLY entry point for decision data
   */
  ingestDecision(decision: Omit<ComplianceDecisionRecord, 'id' | 'ingestedAt' | 'complianceStatus'>): ComplianceDecisionRecord {
    const id = randomUUID();
    const record: ComplianceDecisionRecord = {
      ...decision,
      id,
      ingestedAt: new Date(),
      complianceStatus: decision.sarRequired ? 'PENDING' : 'CLOSED',
    };

    // Verify signature before ingesting (in production)
    // if (!this.verifyOracleSignature(record)) throw new Error('Invalid oracle signature');

    this.decisions.set(id, record);
    this.addAuditEntry('DECISION_INGESTED', 'decision', id, 'SYSTEM', {
      decisionId: decision.decisionId,
      decision: decision.decision,
      sarRequired: decision.sarRequired,
    }, '0.0.0.0');

    return record;
  }

  // ── READ OPERATIONS ─────────────────────────────────────────────────────

  getDecision(id: string): ComplianceDecisionRecord | undefined {
    return this.decisions.get(id);
  }

  getDecisionsByStatus(status: ComplianceDecisionRecord['complianceStatus']): ComplianceDecisionRecord[] {
    return Array.from(this.decisions.values()).filter(d => d.complianceStatus === status);
  }

  getSARsPending(): SARRecord[] {
    return Array.from(this.sars.values()).filter(s => s.status !== 'CLOSED');
  }

  // ── COMPLIANCE OPERATIONS ───────────────────────────────────────────────

  /**
   * Mark decision as reviewed by compliance officer
   */
  markReviewed(decisionId: string, reviewedBy: string, ipAddress: string): ComplianceDecisionRecord {
    const record = this.decisions.get(decisionId);
    if (!record) throw new Error(`Decision ${decisionId} not found`);

    record.complianceStatus = 'REVIEWED';
    record.reviewedBy = reviewedBy;
    record.reviewedAt = new Date();
    
    this.decisions.set(decisionId, record);
    this.addAuditEntry('DECISION_REVIEWED', 'decision', decisionId, reviewedBy, {
      previousStatus: 'PENDING',
      newStatus: 'REVIEWED',
    }, ipAddress);

    return record;
  }

  /**
   * File SAR for a decision
   */
  fileSAR(
    decisionId: string,
    sarData: Omit<SARRecord, 'id' | 'decisionRecordId' | 'filedAt' | 'status' | 'retentionExpiry'>,
    ipAddress: string
  ): SARRecord {
    const decision = this.decisions.get(decisionId);
    if (!decision) throw new Error(`Decision ${decisionId} not found`);

    const id = randomUUID();
    const sar: SARRecord = {
      ...sarData,
      id,
      decisionRecordId: decisionId,
      filedAt: new Date(),
      status: 'DRAFT',
      retentionExpiry: new Date(Date.now() + 5 * 365 * 24 * 60 * 60 * 1000), // 5 years
    };

    this.sars.set(id, sar);
    
    // Update decision status
    decision.complianceStatus = 'SAR_FILED';
    decision.sarId = id;
    this.decisions.set(decisionId, decision);

    this.addAuditEntry('SAR_FILED', 'sar', id, sarData.filedBy, {
      decisionId,
      sarType: sarData.sarType,
    }, ipAddress);

    return sar;
  }

  /**
   * Submit SAR to NCA
   */
  submitSARToNCA(sarId: string, submittedBy: string, ipAddress: string): SARRecord {
    const sar = this.sars.get(sarId);
    if (!sar) throw new Error(`SAR ${sarId} not found`);

    sar.status = 'SUBMITTED';
    this.sars.set(sarId, sar);

    this.addAuditEntry('SAR_SUBMITTED', 'sar', sarId, submittedBy, {
      submittedAt: new Date().toISOString(),
    }, ipAddress);

    return sar;
  }

  // ── AUDIT CHAIN ─────────────────────────────────────────────────────────

  private addAuditEntry(
    action: string,
    entityType: string,
    entityId: string,
    userId: string,
    details: object,
    ipAddress: string
  ): void {
    const entry: AuditEntry = {
      id: randomUUID(),
      timestamp: new Date(),
      action,
      entityType,
      entityId,
      userId,
      details,
      ipAddress,
      previousHash: this.lastAuditHash,
      integrityHash: '', // Will be computed
    };

    // Compute integrity hash (blockchain-like chaining)
    entry.integrityHash = this.computeAuditHash(entry);
    this.lastAuditHash = entry.integrityHash;
    this.auditChain.push(entry);
  }

  private computeAuditHash(entry: Omit<AuditEntry, 'integrityHash'>): string {
    const data = JSON.stringify({
      id: entry.id,
      timestamp: entry.timestamp.toISOString(),
      action: entry.action,
      entityType: entry.entityType,
      entityId: entry.entityId,
      userId: entry.userId,
      details: entry.details,
      previousHash: entry.previousHash,
    });
    return createHash('sha256').update(data).digest('hex');
  }

  /**
   * Verify audit chain integrity
   */
  verifyAuditChain(): { valid: boolean; brokenAt?: number } {
    let previousHash = '0'.repeat(64);
    
    for (let i = 0; i < this.auditChain.length; i++) {
      const entry = this.auditChain[i];
      
      if (entry.previousHash !== previousHash) {
        return { valid: false, brokenAt: i };
      }
      
      const { integrityHash: _, ...entryWithoutHash } = entry;
      const computed = this.computeAuditHash(entryWithoutHash);
      
      if (computed !== entry.integrityHash) {
        return { valid: false, brokenAt: i };
      }
      
      previousHash = entry.integrityHash;
    }
    
    return { valid: true };
  }

  getAuditChain(filters?: { entityId?: string; userId?: string; action?: string }): AuditEntry[] {
    let chain = [...this.auditChain];
    if (filters?.entityId) chain = chain.filter(e => e.entityId === filters.entityId);
    if (filters?.userId) chain = chain.filter(e => e.userId === filters.userId);
    if (filters?.action) chain = chain.filter(e => e.action === filters.action);
    return chain;
  }

  // ── STATISTICS ──────────────────────────────────────────────────────────

  getStats(): object {
    const decisions = Array.from(this.decisions.values());
    const sars = Array.from(this.sars.values());
    const now = new Date();
    const last24h = new Date(now.getTime() - 24 * 60 * 60 * 1000);

    return {
      decisions: {
        total: decisions.length,
        pending: decisions.filter(d => d.complianceStatus === 'PENDING').length,
        reviewed: decisions.filter(d => d.complianceStatus === 'REVIEWED').length,
        sarFiled: decisions.filter(d => d.complianceStatus === 'SAR_FILED').length,
        blocked: decisions.filter(d => d.decision === 'BLOCK').length,
        last24h: decisions.filter(d => d.ingestedAt > last24h).length,
      },
      sars: {
        total: sars.length,
        draft: sars.filter(s => s.status === 'DRAFT').length,
        submitted: sars.filter(s => s.status === 'SUBMITTED').length,
        acknowledged: sars.filter(s => s.status === 'ACKNOWLEDGED').length,
      },
      auditChain: {
        entries: this.auditChain.length,
        integrityValid: this.verifyAuditChain().valid,
        lastEntry: this.auditChain[this.auditChain.length - 1]?.timestamp,
      },
    };
  }

  /**
   * Export for FCA audit
   */
  exportForFCAAudit(startDate: Date, endDate: Date): object {
    const decisions = Array.from(this.decisions.values())
      .filter(d => d.ingestedAt >= startDate && d.ingestedAt <= endDate);
    
    const sars = Array.from(this.sars.values())
      .filter(s => s.filedAt >= startDate && s.filedAt <= endDate);
    
    const auditEntries = this.auditChain
      .filter(e => e.timestamp >= startDate && e.timestamp <= endDate);

    return {
      exportedAt: new Date().toISOString(),
      period: { start: startDate.toISOString(), end: endDate.toISOString() },
      summary: {
        totalDecisions: decisions.length,
        blockedTransactions: decisions.filter(d => d.decision === 'BLOCK').length,
        sarsFiled: sars.length,
        auditEntries: auditEntries.length,
      },
      decisions: decisions.map(d => ({
        id: d.id,
        decisionId: d.decisionId,
        transactionHash: d.transactionHash,
        decision: d.decision,
        riskScore: d.riskScore,
        triggeredPolicies: d.triggeredPolicies,
        sarRequired: d.sarRequired,
        explanationHash: d.explanationHash,
        decisionTimestamp: d.decisionTimestamp,
        ingestedAt: d.ingestedAt,
        complianceStatus: d.complianceStatus,
      })),
      sars: sars.map(s => ({
        id: s.id,
        sarType: s.sarType,
        filedAt: s.filedAt,
        status: s.status,
        ncaReference: s.ncaReference,
      })),
      auditChainHash: this.lastAuditHash,
      auditChainValid: this.verifyAuditChain().valid,
    };
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// FCA COMPLIANCE API - AIR-GAPPED SERVICE
// ═══════════════════════════════════════════════════════════════════════════

const app = express();
app.use(express.json());

// Isolated data store
const complianceStore = new ComplianceDataStore();

// ── AUTHENTICATION MIDDLEWARE (Separate credentials from main service) ────

interface ComplianceUser {
  id: string;
  role: 'COMPLIANCE_OFFICER' | 'MLRO' | 'AUDITOR' | 'SYSTEM';
}

function authenticateComplianceUser(req: Request, res: Response, next: NextFunction): void {
  // In production: verify JWT with separate compliance identity provider
  const authHeader = req.headers.authorization;
  
  if (!authHeader) {
    res.status(401).json({ error: 'Authorization required' });
    return;
  }

  // Mock user for development
  (req as any).complianceUser = {
    id: 'compliance-user-001',
    role: 'COMPLIANCE_OFFICER',
  } as ComplianceUser;

  next();
}

function requireRole(...roles: ComplianceUser['role'][]) {
  return (req: Request, res: Response, next: NextFunction): void => {
    const user = (req as any).complianceUser as ComplianceUser;
    if (!roles.includes(user.role)) {
      res.status(403).json({ error: 'Insufficient permissions' });
      return;
    }
    next();
  };
}

// ── INGESTION ENDPOINT (Write-only from decision layer) ───────────────────

app.post('/compliance/ingest', async (req: Request, res: Response) => {
  try {
    // Verify ingestion comes from authorized oracle service
    const ingestKey = req.headers['x-ingest-key'];
    if (ingestKey !== process.env.COMPLIANCE_INGEST_KEY) {
      res.status(401).json({ error: 'Invalid ingestion key' });
      return;
    }

    const record = complianceStore.ingestDecision(req.body);
    res.status(201).json({ 
      success: true, 
      id: record.id,
      complianceStatus: record.complianceStatus,
    });
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    res.status(500).json({ error: msg });
  }
});

// ── COMPLIANCE REVIEW ENDPOINTS ───────────────────────────────────────────

app.get('/compliance/pending', 
  authenticateComplianceUser,
  requireRole('COMPLIANCE_OFFICER', 'MLRO'),
  (req: Request, res: Response) => {
    const pending = complianceStore.getDecisionsByStatus('PENDING');
    res.json({ count: pending.length, records: pending });
  }
);

app.post('/compliance/review/:id',
  authenticateComplianceUser,
  requireRole('COMPLIANCE_OFFICER', 'MLRO'),
  (req: Request, res: Response) => {
    try {
      const user = (req as any).complianceUser as ComplianceUser;
      const record = complianceStore.markReviewed(
        req.params.id,
        user.id,
        req.ip || '0.0.0.0'
      );
      res.json({ success: true, record });
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      res.status(400).json({ error: msg });
    }
  }
);

// ── SAR ENDPOINTS ─────────────────────────────────────────────────────────

app.post('/compliance/sar/:decisionId',
  authenticateComplianceUser,
  requireRole('COMPLIANCE_OFFICER', 'MLRO'),
  (req: Request, res: Response) => {
    try {
      const user = (req as any).complianceUser as ComplianceUser;
      const sar = complianceStore.fileSAR(
        req.params.decisionId,
        {
          ...req.body,
          filedBy: user.id,
        },
        req.ip || '0.0.0.0'
      );
      res.status(201).json({ success: true, sar });
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      res.status(400).json({ error: msg });
    }
  }
);

app.post('/compliance/sar/:sarId/submit',
  authenticateComplianceUser,
  requireRole('MLRO'), // Only MLRO can submit to NCA
  (req: Request, res: Response) => {
    try {
      const user = (req as any).complianceUser as ComplianceUser;
      const sar = complianceStore.submitSARToNCA(
        req.params.sarId,
        user.id,
        req.ip || '0.0.0.0'
      );
      res.json({ success: true, sar });
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      res.status(400).json({ error: msg });
    }
  }
);

app.get('/compliance/sars/pending',
  authenticateComplianceUser,
  requireRole('COMPLIANCE_OFFICER', 'MLRO'),
  (req: Request, res: Response) => {
    const pending = complianceStore.getSARsPending();
    res.json({ count: pending.length, sars: pending });
  }
);

// ── AUDIT ENDPOINTS ───────────────────────────────────────────────────────

app.get('/compliance/audit',
  authenticateComplianceUser,
  requireRole('AUDITOR', 'MLRO'),
  (req: Request, res: Response) => {
    const chain = complianceStore.getAuditChain({
      entityId: req.query.entityId as string,
      userId: req.query.userId as string,
      action: req.query.action as string,
    });
    const integrity = complianceStore.verifyAuditChain();
    res.json({ 
      entries: chain.length, 
      integrityValid: integrity.valid,
      chain,
    });
  }
);

app.get('/compliance/audit/verify',
  authenticateComplianceUser,
  requireRole('AUDITOR', 'MLRO'),
  (req: Request, res: Response) => {
    const result = complianceStore.verifyAuditChain();
    res.json(result);
  }
);

// ── EXPORT ENDPOINTS ──────────────────────────────────────────────────────

app.get('/compliance/export/fca',
  authenticateComplianceUser,
  requireRole('MLRO', 'AUDITOR'),
  (req: Request, res: Response) => {
    const startDate = new Date(req.query.startDate as string || '2024-01-01');
    const endDate = new Date(req.query.endDate as string || new Date().toISOString());
    
    const export_ = complianceStore.exportForFCAAudit(startDate, endDate);
    res.json(export_);
  }
);

// ── STATISTICS ────────────────────────────────────────────────────────────

app.get('/compliance/stats',
  authenticateComplianceUser,
  (req: Request, res: Response) => {
    res.json(complianceStore.getStats());
  }
);

// ── HEALTH CHECK ──────────────────────────────────────────────────────────

app.get('/compliance/health', (req: Request, res: Response) => {
  const integrity = complianceStore.verifyAuditChain();
  res.json({ 
    status: integrity.valid ? 'healthy' : 'degraded',
    auditChainValid: integrity.valid,
    timestamp: new Date().toISOString(),
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// STARTUP
// ═══════════════════════════════════════════════════════════════════════════

const COMPLIANCE_PORT = parseInt(process.env.COMPLIANCE_PORT || '8002');

export function startComplianceService(): void {
  app.listen(COMPLIANCE_PORT, () => {
    console.log(`FCA Compliance Service (air-gapped) listening on port ${COMPLIANCE_PORT}`);
    console.log('Endpoints:');
    console.log('  POST /compliance/ingest          - Write-only decision ingestion');
    console.log('  GET  /compliance/pending         - Pending compliance reviews');
    console.log('  POST /compliance/review/:id      - Mark decision reviewed');
    console.log('  POST /compliance/sar/:id         - File SAR');
    console.log('  POST /compliance/sar/:id/submit  - Submit SAR to NCA');
    console.log('  GET  /compliance/audit           - View audit chain');
    console.log('  GET  /compliance/export/fca      - FCA audit export');
  });
}

export { app, complianceStore, ComplianceDataStore };
