/**
 * Compliance Report Service
 * 
 * Sprint 11: Compliance Reporting & Export System
 * 
 * Ground Truth Reference:
 * - PDF/JSON export for regulators
 * - Snapshot explorer for audit replay
 * - Evidence linking for complete audit trails
 * - Chain replay tool for UI state reconstruction
 */

import { useState, useCallback, useEffect } from 'react';
import {
  UISnapshot,
  SnapshotFilter,
  Evidence,
  EvidenceType,
  EvidenceStatus,
  EvidenceLink,
  ComplianceReport,
  ReportType,
  ReportFormat,
  ReportStatus,
  ReportTemplate,
  ReplaySession,
  ReplayStep,
  SnapshotDiff,
  ExportConfig,
  ExportResult,
} from '@/types/compliance-report';

// ═══════════════════════════════════════════════════════════════════════════════
// MOCK DATA
// ═══════════════════════════════════════════════════════════════════════════════

const mockSnapshots: UISnapshot[] = [
  {
    id: 'snap-001',
    timestamp: new Date(Date.now() - 3600000).toISOString(),
    userId: 'user-001',
    sessionId: 'session-001',
    screenId: 'focus-transfer',
    screenName: 'Focus Mode - Transfer',
    version: '1.2.3',
    stateHash: '0x7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b',
    previousHash: '0x1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b',
    components: [
      {
        id: 'trust-check-001',
        type: 'TrustCheckInterstitial',
        name: 'Trust Verification',
        props: { recipientAddress: '0x742d35Cc6634C0532925a3b844Bc9e7595f1c7D8' },
        state: { pillarsVerified: 3, totalPillars: 4 },
        visible: true,
        interacted: true,
      },
      {
        id: 'amount-input-001',
        type: 'AmountInput',
        name: 'Transfer Amount',
        props: { currency: 'ETH', maxAmount: 100 },
        state: { value: '25.5' },
        visible: true,
        interacted: true,
      },
    ],
    userContext: {
      role: 'R1_END_USER',
      permissions: ['transfer.initiate', 'trust.view'],
      mode: 'focus',
      activeView: 'transfer',
    },
    transactionContext: {
      transactionId: 'tx-001',
      action: 'TRANSFER',
      amount: '25.5 ETH',
      recipient: '0x742d35Cc6634C0532925a3b844Bc9e7595f1c7D8',
    },
    integrityProof: {
      merkleRoot: '0xabcd1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab',
      merkleProof: [
        '0x1111222233334444555566667777888899990000aaaabbbbccccddddeeee1111',
        '0x2222333344445555666677778888999900001111bbbbccccddddeeee11112222',
      ],
      onChainAnchor: '0x9876543210fedcba9876543210fedcba9876543210fedcba9876543210fedcba',
      blockNumber: 18500000,
      verified: true,
    },
  },
  {
    id: 'snap-002',
    timestamp: new Date(Date.now() - 7200000).toISOString(),
    userId: 'user-002',
    sessionId: 'session-002',
    screenId: 'war-room-detection',
    screenName: 'War Room - Detection Studio',
    version: '1.2.3',
    stateHash: '0x2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c',
    previousHash: '0x7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b',
    components: [
      {
        id: 'graph-explorer-001',
        type: 'GraphExplorer',
        name: 'Transaction Graph',
        props: { depth: 3, maxNodes: 50 },
        state: { selectedNode: 'node-123', zoom: 1.2 },
        visible: true,
        interacted: true,
      },
    ],
    userContext: {
      role: 'R3_OPS',
      permissions: ['detection.view', 'detection.flag', 'graph.explore'],
      mode: 'war-room',
      activeView: 'detection-studio',
    },
    integrityProof: {
      merkleRoot: '0xdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abc',
      merkleProof: [
        '0x3333444455556666777788889999000011112222ccccddddeeee111122223333',
      ],
      onChainAnchor: '0xfedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210',
      blockNumber: 18499500,
      verified: true,
    },
  },
  {
    id: 'snap-003',
    timestamp: new Date(Date.now() - 10800000).toISOString(),
    userId: 'user-003',
    sessionId: 'session-003',
    screenId: 'war-room-policies',
    screenName: 'War Room - Policy Engine',
    version: '1.2.3',
    stateHash: '0x3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d',
    previousHash: '0x2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c',
    components: [
      {
        id: 'policy-editor-001',
        type: 'PolicyRuleEditor',
        name: 'Policy Rule Editor',
        props: { policyId: 'policy-001' },
        state: { draft: true, conditions: 3 },
        visible: true,
        interacted: true,
      },
    ],
    userContext: {
      role: 'R4_COMPLIANCE',
      permissions: ['policy.read', 'policy.write', 'policy.approve'],
      mode: 'war-room',
      activeView: 'policies',
    },
    integrityProof: {
      merkleRoot: '0x456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123',
      merkleProof: [],
      verified: false, // Pending verification
    },
  },
];

const mockEvidence: Evidence[] = [
  {
    id: 'ev-001',
    type: EvidenceType.UI_SNAPSHOT,
    status: EvidenceStatus.VERIFIED,
    timestamp: new Date(Date.now() - 3600000).toISOString(),
    relatedSnapshots: ['snap-001'],
    relatedTransactions: ['tx-001'],
    relatedAuditEvents: ['audit-001', 'audit-002'],
    title: 'Transfer Authorization Snapshot',
    description: 'UI state captured at the moment of transfer authorization',
    contentHash: '0x7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b',
    submittedBy: 'system',
    submittedAt: new Date(Date.now() - 3600000).toISOString(),
    verifiedBy: 'integrity-service',
    verifiedAt: new Date(Date.now() - 3500000).toISOString(),
    onChainReference: '0x9876543210fedcba9876543210fedcba9876543210fedcba9876543210fedcba',
    blockNumber: 18500000,
  },
  {
    id: 'ev-002',
    type: EvidenceType.TRANSACTION,
    status: EvidenceStatus.VERIFIED,
    timestamp: new Date(Date.now() - 3550000).toISOString(),
    relatedSnapshots: ['snap-001'],
    relatedTransactions: ['tx-001'],
    relatedAuditEvents: ['audit-003'],
    title: 'On-chain Transfer Record',
    description: 'Blockchain transaction record for 25.5 ETH transfer',
    contentHash: '0x4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e',
    submittedBy: 'chain-indexer',
    submittedAt: new Date(Date.now() - 3550000).toISOString(),
    verifiedBy: 'chain-verifier',
    verifiedAt: new Date(Date.now() - 3545000).toISOString(),
    onChainReference: '0xabc123def456789abc123def456789abc123def456789abc123def456789abc1',
    blockNumber: 18500001,
  },
  {
    id: 'ev-003',
    type: EvidenceType.SIGNATURE,
    status: EvidenceStatus.VERIFIED,
    timestamp: new Date(Date.now() - 3580000).toISOString(),
    relatedSnapshots: ['snap-001'],
    relatedTransactions: ['tx-001'],
    relatedAuditEvents: ['audit-002'],
    title: 'EIP-712 User Signature',
    description: 'User signature including UI state hash commitment',
    contentHash: '0x5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f',
    submittedBy: 'user-001',
    submittedAt: new Date(Date.now() - 3580000).toISOString(),
    verifiedBy: 'signature-verifier',
    verifiedAt: new Date(Date.now() - 3575000).toISOString(),
    onChainReference: '0xabc123def456789abc123def456789abc123def456789abc123def456789abc1',
    blockNumber: 18500001,
  },
  {
    id: 'ev-004',
    type: EvidenceType.AUDIT_LOG,
    status: EvidenceStatus.PENDING,
    timestamp: new Date(Date.now() - 7200000).toISOString(),
    relatedSnapshots: ['snap-002'],
    relatedTransactions: [],
    relatedAuditEvents: ['audit-010'],
    title: 'Detection Flag Audit',
    description: 'Audit log for transaction flagging by detection system',
    contentHash: '0x6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a',
    submittedBy: 'detection-service',
    submittedAt: new Date(Date.now() - 7200000).toISOString(),
  },
];

const mockReports: ComplianceReport[] = [
  {
    id: 'report-001',
    title: 'Daily Compliance Report - January 21, 2025',
    type: ReportType.COMPLIANCE,
    status: ReportStatus.READY,
    format: ReportFormat.PDF,
    periodStart: new Date(Date.now() - 86400000).toISOString(),
    periodEnd: new Date().toISOString(),
    sections: [
      { id: 'sec-1', title: 'Executive Summary', type: 'summary', content: {}, order: 1 },
      { id: 'sec-2', title: 'Transaction Analysis', type: 'transactions', content: {}, order: 2 },
      { id: 'sec-3', title: 'Audit Trail', type: 'audit', content: {}, order: 3 },
    ],
    summary: {
      totalTransactions: 1247,
      totalSnapshots: 3892,
      totalEvidence: 156,
      totalAuditEvents: 8934,
      riskDistribution: { high: 12, medium: 89, low: 1146 },
      complianceScore: 98.2,
      integrityScore: 99.8,
      verifiedPercentage: 99.1,
      keyFindings: [
        '12 high-risk transactions detected and flagged',
        'All enforcement actions properly authorized via multisig',
        'UI integrity maintained across all sessions',
      ],
      recommendations: [
        'Review velocity alerts for wallet cluster 0x7a8b...',
        'Update OFAC list to latest version',
      ],
    },
    createdBy: 'compliance-team',
    createdAt: new Date().toISOString(),
    exportCount: 3,
    contentHash: '0x8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b',
    signature: '0x1234567890abcdef...',
    signedBy: 'compliance-officer',
    signedAt: new Date().toISOString(),
  },
  {
    id: 'report-002',
    title: 'Incident Report - Suspicious Activity',
    type: ReportType.INCIDENT,
    status: ReportStatus.DRAFT,
    format: ReportFormat.JSON,
    periodStart: new Date(Date.now() - 172800000).toISOString(),
    periodEnd: new Date().toISOString(),
    sections: [
      { id: 'sec-1', title: 'Incident Summary', type: 'summary', content: {}, order: 1 },
      { id: 'sec-2', title: 'Evidence Collection', type: 'evidence', content: {}, order: 2 },
    ],
    summary: {
      totalTransactions: 45,
      totalSnapshots: 128,
      totalEvidence: 23,
      totalAuditEvents: 456,
      riskDistribution: { high: 8, medium: 27, low: 10 },
      complianceScore: 85.0,
      integrityScore: 100.0,
      verifiedPercentage: 95.5,
      keyFindings: ['Potential layering pattern detected'],
      recommendations: ['File SAR within 24 hours'],
    },
    createdBy: 'ops-team',
    createdAt: new Date(Date.now() - 3600000).toISOString(),
    exportCount: 0,
    contentHash: '0x9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c',
  },
];

const mockTemplates: ReportTemplate[] = [
  {
    id: 'template-001',
    name: 'Daily Compliance Report',
    type: ReportType.COMPLIANCE,
    description: 'Standard daily compliance report for regulatory submission',
    sections: ['summary', 'transactions', 'audit', 'evidence'],
    defaultFormat: ReportFormat.PDF,
    isDefault: true,
  },
  {
    id: 'template-002',
    name: 'Incident Investigation',
    type: ReportType.INCIDENT,
    description: 'Detailed incident report with evidence chain',
    sections: ['summary', 'evidence', 'snapshots', 'analysis'],
    defaultFormat: ReportFormat.JSON,
    isDefault: false,
  },
  {
    id: 'template-003',
    name: 'Regulatory Audit Package',
    type: ReportType.REGULATORY,
    description: 'Complete audit package for regulatory examination',
    sections: ['summary', 'transactions', 'snapshots', 'evidence', 'audit'],
    defaultFormat: ReportFormat.PDF,
    isDefault: false,
  },
];

// ═══════════════════════════════════════════════════════════════════════════════
// SERVICE HOOKS
// ═══════════════════════════════════════════════════════════════════════════════

export function useSnapshots() {
  const [snapshots, setSnapshots] = useState<UISnapshot[]>(mockSnapshots);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedSnapshot, setSelectedSnapshot] = useState<UISnapshot | null>(null);

  const fetchSnapshots = useCallback(async (filter?: SnapshotFilter) => {
    setIsLoading(true);
    // Simulate API call
    await new Promise(resolve => setTimeout(resolve, 500));
    
    let filtered = [...mockSnapshots];
    
    if (filter?.userId) {
      filtered = filtered.filter(s => s.userId === filter.userId);
    }
    if (filter?.screenId) {
      filtered = filtered.filter(s => s.screenId === filter.screenId);
    }
    if (filter?.verified !== undefined) {
      filtered = filtered.filter(s => s.integrityProof.verified === filter.verified);
    }
    if (filter?.startDate) {
      filtered = filtered.filter(s => new Date(s.timestamp) >= new Date(filter.startDate!));
    }
    if (filter?.endDate) {
      filtered = filtered.filter(s => new Date(s.timestamp) <= new Date(filter.endDate!));
    }
    
    setSnapshots(filtered);
    setIsLoading(false);
    return filtered;
  }, []);

  const verifySnapshot = useCallback(async (snapshotId: string): Promise<boolean> => {
    setIsLoading(true);
    await new Promise(resolve => setTimeout(resolve, 800));
    
    setSnapshots(prev => prev.map(s => 
      s.id === snapshotId 
        ? { ...s, integrityProof: { ...s.integrityProof, verified: true } }
        : s
    ));
    
    setIsLoading(false);
    return true;
  }, []);

  const getSnapshotById = useCallback(async (id: string): Promise<UISnapshot | null> => {
    await new Promise(resolve => setTimeout(resolve, 200));
    return snapshots.find(s => s.id === id) || null;
  }, [snapshots]);

  return {
    snapshots,
    isLoading,
    selectedSnapshot,
    setSelectedSnapshot,
    fetchSnapshots,
    verifySnapshot,
    getSnapshotById,
  };
}

export function useEvidence() {
  const [evidence, setEvidence] = useState<Evidence[]>(mockEvidence);
  const [links, setLinks] = useState<EvidenceLink[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const fetchEvidence = useCallback(async (relatedId?: string, type?: 'snapshot' | 'transaction' | 'audit') => {
    setIsLoading(true);
    await new Promise(resolve => setTimeout(resolve, 400));
    
    let filtered = [...mockEvidence];
    
    if (relatedId && type) {
      switch (type) {
        case 'snapshot':
          filtered = filtered.filter(e => e.relatedSnapshots.includes(relatedId));
          break;
        case 'transaction':
          filtered = filtered.filter(e => e.relatedTransactions.includes(relatedId));
          break;
        case 'audit':
          filtered = filtered.filter(e => e.relatedAuditEvents.includes(relatedId));
          break;
      }
    }
    
    setEvidence(filtered);
    setIsLoading(false);
    return filtered;
  }, []);

  const linkEvidence = useCallback(async (
    sourceId: string,
    sourceType: EvidenceLink['sourceType'],
    targetId: string,
    targetType: EvidenceLink['targetType'],
    relationship: EvidenceLink['relationship']
  ): Promise<EvidenceLink> => {
    await new Promise(resolve => setTimeout(resolve, 300));
    
    const newLink: EvidenceLink = {
      id: `link-${Date.now()}`,
      sourceId,
      sourceType,
      targetId,
      targetType,
      relationship,
      createdAt: new Date().toISOString(),
      createdBy: 'current-user',
    };
    
    setLinks(prev => [...prev, newLink]);
    return newLink;
  }, []);

  const getEvidenceChain = useCallback(async (startId: string): Promise<Evidence[]> => {
    await new Promise(resolve => setTimeout(resolve, 500));
    // In real implementation, this would traverse the evidence graph
    return evidence.filter(e => 
      e.relatedSnapshots.some(s => s === startId) ||
      e.relatedTransactions.some(t => t === startId)
    );
  }, [evidence]);

  return {
    evidence,
    links,
    isLoading,
    fetchEvidence,
    linkEvidence,
    getEvidenceChain,
  };
}

export function useComplianceReports() {
  const [reports, setReports] = useState<ComplianceReport[]>(mockReports);
  const [templates, setTemplates] = useState<ReportTemplate[]>(mockTemplates);
  const [isLoading, setIsLoading] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  const fetchReports = useCallback(async (type?: ReportType) => {
    setIsLoading(true);
    await new Promise(resolve => setTimeout(resolve, 400));
    
    let filtered = [...mockReports];
    if (type) {
      filtered = filtered.filter(r => r.type === type);
    }
    
    setReports(filtered);
    setIsLoading(false);
    return filtered;
  }, []);

  const createReport = useCallback(async (
    title: string,
    type: ReportType,
    templateId: string,
    periodStart: string,
    periodEnd: string
  ): Promise<ComplianceReport> => {
    setIsLoading(true);
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    const newReport: ComplianceReport = {
      id: `report-${Date.now()}`,
      title,
      type,
      status: ReportStatus.GENERATING,
      format: ReportFormat.PDF,
      periodStart,
      periodEnd,
      sections: [],
      summary: {
        totalTransactions: 0,
        totalSnapshots: 0,
        totalEvidence: 0,
        totalAuditEvents: 0,
        riskDistribution: { high: 0, medium: 0, low: 0 },
        complianceScore: 0,
        integrityScore: 0,
        verifiedPercentage: 0,
        keyFindings: [],
        recommendations: [],
      },
      createdBy: 'current-user',
      createdAt: new Date().toISOString(),
      exportCount: 0,
      contentHash: '',
    };
    
    setReports(prev => [...prev, newReport]);
    
    // Simulate report generation
    setTimeout(() => {
      setReports(prev => prev.map(r => 
        r.id === newReport.id 
          ? { ...r, status: ReportStatus.READY }
          : r
      ));
    }, 2000);
    
    setIsLoading(false);
    return newReport;
  }, []);

  const exportReport = useCallback(async (
    reportId: string,
    config: ExportConfig
  ): Promise<ExportResult> => {
    setIsExporting(true);
    await new Promise(resolve => setTimeout(resolve, 1500));
    
    const report = reports.find(r => r.id === reportId);
    if (!report) {
      setIsExporting(false);
      return {
        success: false,
        format: config.format,
        fileName: '',
        fileSize: 0,
        contentHash: '',
        exportedAt: new Date().toISOString(),
        error: 'Report not found',
      };
    }
    
    const fileName = `${report.title.replace(/[^a-zA-Z0-9]/g, '_')}_${new Date().toISOString().split('T')[0]}.${config.format.toLowerCase()}`;
    
    // Update report export count
    setReports(prev => prev.map(r => 
      r.id === reportId 
        ? { ...r, exportCount: r.exportCount + 1, status: ReportStatus.EXPORTED, exportedAt: new Date().toISOString() }
        : r
    ));
    
    setIsExporting(false);
    
    return {
      success: true,
      format: config.format,
      fileName,
      fileSize: 245678,
      downloadUrl: `/api/reports/${reportId}/download?format=${config.format.toLowerCase()}`,
      contentHash: '0xabc123...',
      exportedAt: new Date().toISOString(),
    };
  }, [reports]);

  return {
    reports,
    templates,
    isLoading,
    isExporting,
    fetchReports,
    createReport,
    exportReport,
  };
}

export function useChainReplay() {
  const [session, setSession] = useState<ReplaySession | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const createReplaySession = useCallback(async (
    name: string,
    startTime: string,
    endTime: string,
    options?: { userId?: string; transactionId?: string; sessionId?: string }
  ): Promise<ReplaySession> => {
    setIsLoading(true);
    await new Promise(resolve => setTimeout(resolve, 800));
    
    // Filter snapshots for the time range
    const relevantSnapshots = mockSnapshots.filter(s => {
      const ts = new Date(s.timestamp).getTime();
      const start = new Date(startTime).getTime();
      const end = new Date(endTime).getTime();
      return ts >= start && ts <= end;
    }).sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
    
    const newSession: ReplaySession = {
      id: `replay-${Date.now()}`,
      name,
      startTime,
      endTime,
      userId: options?.userId,
      transactionId: options?.transactionId,
      sessionId: options?.sessionId,
      status: 'idle',
      currentSnapshotIndex: 0,
      totalSnapshots: relevantSnapshots.length,
      playbackSpeed: 1,
      snapshots: relevantSnapshots,
      createdAt: new Date().toISOString(),
      createdBy: 'current-user',
    };
    
    setSession(newSession);
    setIsLoading(false);
    return newSession;
  }, []);

  const play = useCallback(() => {
    if (!session) return;
    setSession(prev => prev ? { ...prev, status: 'playing' } : null);
  }, [session]);

  const pause = useCallback(() => {
    if (!session) return;
    setSession(prev => prev ? { ...prev, status: 'paused' } : null);
  }, [session]);

  const goToStep = useCallback((index: number) => {
    if (!session) return;
    setSession(prev => prev ? { 
      ...prev, 
      currentSnapshotIndex: Math.max(0, Math.min(index, prev.totalSnapshots - 1)) 
    } : null);
  }, [session]);

  const setPlaybackSpeed = useCallback((speed: number) => {
    if (!session) return;
    setSession(prev => prev ? { ...prev, playbackSpeed: speed } : null);
  }, [session]);

  const getStepDiff = useCallback((fromIndex: number, toIndex: number): SnapshotDiff[] => {
    if (!session || fromIndex < 0 || toIndex >= session.snapshots.length) return [];
    
    const fromSnapshot = session.snapshots[fromIndex];
    const toSnapshot = session.snapshots[toIndex];
    
    const diffs: SnapshotDiff[] = [];
    
    // Compare components
    toSnapshot.components.forEach(toComp => {
      const fromComp = fromSnapshot.components.find(c => c.id === toComp.id);
      
      if (!fromComp) {
        diffs.push({
          componentId: toComp.id,
          componentName: toComp.name,
          field: 'component',
          previousValue: null,
          newValue: toComp,
          changeType: 'added',
        });
      } else {
        // Check state changes
        Object.keys(toComp.state).forEach(key => {
          if (JSON.stringify(fromComp.state[key]) !== JSON.stringify(toComp.state[key])) {
            diffs.push({
              componentId: toComp.id,
              componentName: toComp.name,
              field: `state.${key}`,
              previousValue: fromComp.state[key],
              newValue: toComp.state[key],
              changeType: 'modified',
            });
          }
        });
      }
    });
    
    // Check for removed components
    fromSnapshot.components.forEach(fromComp => {
      if (!toSnapshot.components.find(c => c.id === fromComp.id)) {
        diffs.push({
          componentId: fromComp.id,
          componentName: fromComp.name,
          field: 'component',
          previousValue: fromComp,
          newValue: null,
          changeType: 'removed',
        });
      }
    });
    
    return diffs;
  }, [session]);

  const closeSession = useCallback(() => {
    setSession(null);
  }, []);

  return {
    session,
    isLoading,
    createReplaySession,
    play,
    pause,
    goToStep,
    setPlaybackSpeed,
    getStepDiff,
    closeSession,
  };
}
