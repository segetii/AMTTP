/**
 * AMTTP FCA Compliance - zkNAF Integration
 * 
 * This module bridges the zkNAF privacy layer with FCA compliance requirements.
 * 
 * KEY PRINCIPLE:
 * - PUBLIC LAYER: ZK proofs for DeFi protocols (no PII exposed)
 * - REGULATED LAYER: Full records for FCA/NCA (SAR, law enforcement)
 * 
 * MLR 2017 COMPLIANCE:
 * - All proof generation is logged with full underlying data
 * - 5-year retention of proof records with actual values
 * - XAI explanations stored for regulatory disclosure
 * - Proof revocation logged for audit trail
 */

import { createHash, randomUUID } from 'crypto';

// ═══════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════

export interface ZkProofAuditRecord {
  id: string;
  
  // Proof identification
  proofId: string;
  proofType: 'sanctions' | 'risk-low' | 'risk-medium' | 'kyc';
  proofHash: string;
  
  // User identification (full data for regulatory disclosure)
  userAddress: string;
  kycRecordId?: string;
  
  // Actual values (NOT exposed in ZK proof)
  actualRiskScore?: number;
  sanctionsCheckPassed?: boolean;
  kycVerificationStatus?: string;
  isPEP?: boolean;
  
  // Proof validity
  createdAt: Date;
  expiresAt: Date;
  revokedAt?: Date;
  revocationReason?: string;
  
  // Audit trail
  requestIp: string;
  requestUserAgent: string;
  oracleVersion: string;
  
  // Integrity
  integrityHash: string;
  previousRecordHash: string;
}

export interface ZkProofComplianceReport {
  reportId: string;
  generatedAt: Date;
  period: { start: Date; end: Date };
  
  // Statistics
  totalProofsGenerated: number;
  proofsByType: Record<string, number>;
  proofsRevoked: number;
  
  // Risk distribution (actual values, not ZK ranges)
  riskScoreDistribution: {
    low: number;    // 0-39
    medium: number; // 40-69
    high: number;   // 70-100
  };
  
  // Compliance metrics
  sanctionsHits: number;
  pepHits: number;
  sarFiledForProofUsers: number;
}

// ═══════════════════════════════════════════════════════════════════════════
// ZKNAF COMPLIANCE STORE
// ═══════════════════════════════════════════════════════════════════════════

class ZkNAFComplianceStore {
  private proofAuditRecords: Map<string, ZkProofAuditRecord> = new Map();
  private lastRecordHash: string = '0'.repeat(64);
  
  /**
   * Log ZK proof generation with full underlying data
   * Required for FCA compliance - maintains actual values for regulatory disclosure
   */
  logProofGeneration(record: Omit<ZkProofAuditRecord, 'id' | 'integrityHash' | 'previousRecordHash'>): ZkProofAuditRecord {
    const id = randomUUID();
    
    // Compute integrity hash
    const integrityData = JSON.stringify({
      ...record,
      id,
      previousRecordHash: this.lastRecordHash,
    });
    const integrityHash = createHash('sha256').update(integrityData).digest('hex');
    
    const fullRecord: ZkProofAuditRecord = {
      ...record,
      id,
      integrityHash,
      previousRecordHash: this.lastRecordHash,
    };
    
    this.proofAuditRecords.set(id, fullRecord);
    this.lastRecordHash = integrityHash;
    
    console.log(`[FCA-ZKNAF] Proof logged: ${record.proofType} for ${record.userAddress}`);
    
    return fullRecord;
  }
  
  /**
   * Log proof revocation
   */
  logProofRevocation(proofId: string, reason: string): ZkProofAuditRecord | null {
    const record = Array.from(this.proofAuditRecords.values())
      .find(r => r.proofId === proofId);
    
    if (!record) return null;
    
    record.revokedAt = new Date();
    record.revocationReason = reason;
    
    this.proofAuditRecords.set(record.id, record);
    
    console.log(`[FCA-ZKNAF] Proof revoked: ${proofId} - ${reason}`);
    
    return record;
  }
  
  /**
   * Get all proof records for a user address
   * Used for SAR filing and law enforcement requests
   */
  getRecordsByAddress(address: string): ZkProofAuditRecord[] {
    return Array.from(this.proofAuditRecords.values())
      .filter(r => r.userAddress.toLowerCase() === address.toLowerCase())
      .sort((a, b) => b.createdAt.getTime() - a.createdAt.getTime());
  }
  
  /**
   * Get records by actual risk score range
   * For internal compliance analysis (not exposed in ZK proofs)
   */
  getRecordsByActualRiskScore(minScore: number, maxScore: number): ZkProofAuditRecord[] {
    return Array.from(this.proofAuditRecords.values())
      .filter(r => 
        r.actualRiskScore !== undefined && 
        r.actualRiskScore >= minScore && 
        r.actualRiskScore <= maxScore
      );
  }
  
  /**
   * Generate FCA compliance report for zkNAF proofs
   */
  generateComplianceReport(startDate: Date, endDate: Date): ZkProofComplianceReport {
    const records = Array.from(this.proofAuditRecords.values())
      .filter(r => r.createdAt >= startDate && r.createdAt <= endDate);
    
    const proofsByType: Record<string, number> = {};
    let low = 0, medium = 0, high = 0;
    let sanctionsHits = 0, pepHits = 0;
    
    for (const record of records) {
      proofsByType[record.proofType] = (proofsByType[record.proofType] || 0) + 1;
      
      if (record.actualRiskScore !== undefined) {
        if (record.actualRiskScore < 40) low++;
        else if (record.actualRiskScore < 70) medium++;
        else high++;
      }
      
      if (record.sanctionsCheckPassed === false) sanctionsHits++;
      if (record.isPEP === true) pepHits++;
    }
    
    return {
      reportId: randomUUID(),
      generatedAt: new Date(),
      period: { start: startDate, end: endDate },
      totalProofsGenerated: records.length,
      proofsByType,
      proofsRevoked: records.filter(r => r.revokedAt).length,
      riskScoreDistribution: { low, medium, high },
      sanctionsHits,
      pepHits,
      sarFiledForProofUsers: 0, // Would be joined with SAR records
    };
  }
  
  /**
   * Verify audit chain integrity
   */
  verifyIntegrity(): { valid: boolean; brokenAt?: string } {
    let previousHash = '0'.repeat(64);
    
    const sortedRecords = Array.from(this.proofAuditRecords.values())
      .sort((a, b) => a.createdAt.getTime() - b.createdAt.getTime());
    
    for (const record of sortedRecords) {
      if (record.previousRecordHash !== previousHash) {
        return { valid: false, brokenAt: record.id };
      }
      previousHash = record.integrityHash;
    }
    
    return { valid: true };
  }
  
  /**
   * Export records for regulatory request
   * Includes full underlying data (actual risk scores, KYC details, etc.)
   */
  exportForRegulatoryRequest(
    requestType: 'SAR' | 'LAW_ENFORCEMENT' | 'FCA_AUDIT',
    addresses?: string[]
  ): {
    records: ZkProofAuditRecord[];
    exportedAt: Date;
    requestType: string;
    integrityValid: boolean;
  } {
    let records: ZkProofAuditRecord[];
    
    if (addresses && addresses.length > 0) {
      records = Array.from(this.proofAuditRecords.values())
        .filter(r => addresses.map(a => a.toLowerCase()).includes(r.userAddress.toLowerCase()));
    } else {
      records = Array.from(this.proofAuditRecords.values());
    }
    
    console.log(`[FCA-ZKNAF] Regulatory export: ${requestType} - ${records.length} records`);
    
    return {
      records,
      exportedAt: new Date(),
      requestType,
      integrityValid: this.verifyIntegrity().valid,
    };
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// SINGLETON INSTANCE
// ═══════════════════════════════════════════════════════════════════════════

export const zkNAFComplianceStore = new ZkNAFComplianceStore();

// ═══════════════════════════════════════════════════════════════════════════
// EXPRESS ROUTES (Add to FCA Compliance API)
// ═══════════════════════════════════════════════════════════════════════════

import { Router } from 'express';

export const zkNAFComplianceRouter = Router();

/**
 * Get zkNAF proof records for an address
 * Restricted to compliance officers
 */
zkNAFComplianceRouter.get('/zknaf/records/:address', (req, res) => {
  const { address } = req.params;
  const records = zkNAFComplianceStore.getRecordsByAddress(address);
  
  res.json({
    address,
    recordCount: records.length,
    records: records.map(r => ({
      id: r.id,
      proofType: r.proofType,
      proofHash: r.proofHash,
      actualRiskScore: r.actualRiskScore,  // Full data for compliance
      sanctionsCheckPassed: r.sanctionsCheckPassed,
      createdAt: r.createdAt,
      expiresAt: r.expiresAt,
      revokedAt: r.revokedAt,
    })),
  });
});

/**
 * Generate zkNAF compliance report
 */
zkNAFComplianceRouter.get('/zknaf/report', (req, res) => {
  const startDate = new Date(req.query.start as string || Date.now() - 30 * 24 * 60 * 60 * 1000);
  const endDate = new Date(req.query.end as string || Date.now());
  
  const report = zkNAFComplianceStore.generateComplianceReport(startDate, endDate);
  
  res.json(report);
});

/**
 * Export records for regulatory request
 */
zkNAFComplianceRouter.post('/zknaf/export', (req, res) => {
  const { requestType, addresses } = req.body;
  
  if (!['SAR', 'LAW_ENFORCEMENT', 'FCA_AUDIT'].includes(requestType)) {
    return res.status(400).json({ error: 'Invalid request type' });
  }
  
  const exportData = zkNAFComplianceStore.exportForRegulatoryRequest(
    requestType,
    addresses
  );
  
  res.json(exportData);
});

/**
 * Verify audit chain integrity
 */
zkNAFComplianceRouter.get('/zknaf/integrity', (req, res) => {
  const result = zkNAFComplianceStore.verifyIntegrity();
  
  res.json({
    valid: result.valid,
    brokenAt: result.brokenAt,
    checkedAt: new Date().toISOString(),
  });
});

export default zkNAFComplianceStore;
