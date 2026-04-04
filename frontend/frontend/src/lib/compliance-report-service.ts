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

const mockSnapshots: UISnapshot[] = []; // Loaded on-demand from backend

const mockEvidence: Evidence[] = []; // Loaded on-demand from backend

const mockReports: ComplianceReport[] = []; // Created interactively

const mockTemplates: ReportTemplate[] = [
  {
    id: 'tmpl-daily',
    name: 'Daily AML Compliance Report',
    type: ReportType.COMPLIANCE,
    description: 'Standard daily compliance report covering all flagged transactions, risk distributions, and enforcement actions.',
    sections: ['Summary', 'Flagged Transactions', 'Risk Analysis', 'Actions Taken'],
    defaultFormat: ReportFormat.PDF,
    isDefault: true,
  },
  {
    id: 'tmpl-regulatory',
    name: 'Regulatory Filing (FCA/FinCEN)',
    type: ReportType.REGULATORY,
    description: 'Pre-formatted filing for FCA or FinCEN regulatory submissions with required data fields.',
    sections: ['Entity Information', 'Suspicious Activity', 'Transaction Details', 'Supporting Evidence'],
    defaultFormat: ReportFormat.PDF,
    isDefault: false,
  },
  {
    id: 'tmpl-transaction',
    name: 'Transaction Monitoring Report',
    type: ReportType.TRANSACTION,
    description: 'Detailed transaction analysis including velocity patterns, risk scoring, and counterparty mapping.',
    sections: ['Transaction Summary', 'Velocity Analysis', 'Graph Relationships', 'Risk Scores'],
    defaultFormat: ReportFormat.PDF,
    isDefault: false,
  },
  {
    id: 'tmpl-audit',
    name: 'Audit Trail Export',
    type: ReportType.AUDIT,
    description: 'Complete audit trail for a specified time period with evidence chain and UI snapshots.',
    sections: ['Audit Events', 'Evidence Chain', 'UI Snapshots', 'Integrity Proofs'],
    defaultFormat: ReportFormat.JSON,
    isDefault: false,
  },
  {
    id: 'tmpl-incident',
    name: 'Incident Response Report',
    type: ReportType.INCIDENT,
    description: 'Post-incident analysis including timeline, impact assessment, and remediation steps.',
    sections: ['Incident Timeline', 'Impact Assessment', 'Root Cause', 'Remediation'],
    defaultFormat: ReportFormat.PDF,
    isDefault: false,
  },
  {
    id: 'tmpl-custom',
    name: 'Custom Investigation Report',
    type: ReportType.CUSTOM,
    description: 'Flexible template for ad-hoc investigations with configurable sections.',
    sections: ['Overview', 'Findings', 'Recommendations'],
    defaultFormat: ReportFormat.PDF,
    isDefault: false,
  },
  {
    id: 'tmpl-sar',
    name: 'Suspicious Activity Report (SAR)',
    type: ReportType.SAR,
    description: 'FinCEN/FCA-compliant SAR filing with subject information, suspicious activity narrative, and supporting documentation.',
    sections: ['Filing Institution', 'Subject Information', 'Suspicious Activity', 'Transaction Details', 'Narrative', 'Supporting Documentation'],
    defaultFormat: ReportFormat.PDF,
    isDefault: false,
  },
];

// ═══════════════════════════════════════════════════════════════════════════════
// REPORT CONTENT BUILDERS
// ═══════════════════════════════════════════════════════════════════════════════

function buildReportPayload(
  report: ComplianceReport,
  stats: Record<string, unknown>,
  flagged: Record<string, unknown>[],
  isSAR: boolean,
) {
  const base = {
    reportId: report.id,
    title: report.title,
    type: report.type,
    periodStart: report.periodStart,
    periodEnd: report.periodEnd,
    generatedAt: new Date().toISOString(),
    generatedBy: 'AMTTP Compliance Engine',
    summary: {
      totalTransactions: stats.totalTransactions || 0,
      flaggedTransactions: stats.flaggedCount || flagged.length,
      averageRiskScore: stats.averageRiskScore || stats.avgRiskScore || 0,
      highRiskWallets: stats.highRiskWallets || 0,
    },
  };

  if (isSAR) {
    const suspiciousTxns = flagged
      .filter((f) => ((f.riskScore as number) || 0) >= 70)
      .slice(0, 20);
    return {
      ...base,
      sarDetails: {
        filingInstitution: {
          name: 'AMTTP Platform',
          type: 'DeFi Compliance Platform',
          regulatoryId: 'AMTTP-SAR-001',
          jurisdiction: 'United Kingdom / United States',
        },
        subjectInformation: suspiciousTxns.map((tx) => ({
          address: tx.address || tx.from || 'Unknown',
          riskScore: tx.riskScore || 0,
          riskLevel: tx.riskLevel || 'high',
          reason: tx.reason || 'Suspicious transaction pattern',
        })),
        suspiciousActivity: {
          totalAmount: suspiciousTxns.reduce((s, t) => s + ((t.amount as number) || (t.value as number) || 0), 0),
          activityType: 'Structuring / Layering / Unusual Pattern',
          dateRange: { start: report.periodStart, end: report.periodEnd },
          description: `${suspiciousTxns.length} suspicious transactions detected by ML risk engine during the reporting period.`,
        },
        transactions: suspiciousTxns.map((tx) => ({
          hash: tx.txHash || tx.hash || 'N/A',
          from: tx.from || tx.address || 'Unknown',
          to: tx.to || 'Unknown',
          amount: tx.amount || tx.value || 0,
          token: tx.token || 'ETH',
          riskScore: tx.riskScore || 0,
          reason: tx.reason || tx.flagReason || 'Flagged by automated screening',
          timestamp: tx.timestamp || '',
        })),
        narrative: `This Suspicious Activity Report is filed pursuant to regulatory requirements. The AMTTP compliance engine identified ${suspiciousTxns.length} transactions exhibiting patterns consistent with potential money laundering, structuring, or other suspicious financial activity during the period ${report.periodStart} to ${report.periodEnd}. All flagged transactions were scored by an ML risk engine and cross-referenced against sanctions lists and behavioral analytics.`,
      },
    };
  }

  return {
    ...base,
    flaggedTransactions: flagged.slice(0, 50).map((tx) => ({
      hash: tx.txHash || tx.hash || 'N/A',
      from: tx.from || tx.address || 'Unknown',
      to: tx.to || 'Unknown',
      amount: tx.amount || tx.value || 0,
      riskScore: tx.riskScore || 0,
      reason: tx.reason || tx.flagReason || '',
      timestamp: tx.timestamp || '',
    })),
  };
}

function buildCSVContent(
  report: ComplianceReport,
  flagged: Record<string, unknown>[],
): string {
  const headers = ['Transaction Hash', 'From', 'To', 'Amount', 'Token', 'Risk Score', 'Risk Level', 'Reason', 'Timestamp'];
  const rows = flagged.slice(0, 200).map((tx) => [
    tx.txHash || tx.hash || '',
    tx.from || tx.address || '',
    tx.to || '',
    tx.amount || tx.value || 0,
    tx.token || 'ETH',
    tx.riskScore || 0,
    tx.riskLevel || '',
    `"${((tx.reason || tx.flagReason || '') as string).replace(/"/g, '""')}"`,
    tx.timestamp || '',
  ]);
  return [
    `# ${report.title}`,
    `# Generated: ${new Date().toISOString()}`,
    `# Period: ${report.periodStart} to ${report.periodEnd}`,
    '',
    headers.join(','),
    ...rows.map((r) => r.join(',')),
  ].join('\n');
}

function buildHTMLReport(
  report: ComplianceReport,
  stats: Record<string, unknown>,
  flagged: Record<string, unknown>[],
  isSAR: boolean,
  config: ExportConfig,
): string {
  const totalTx = (stats.totalTransactions as number) || 0;
  const flaggedCount = (stats.flaggedCount as number) || flagged.length;
  const avgRisk = (stats.averageRiskScore as number) || (stats.avgRiskScore as number) || 0;
  const suspiciousTxns = flagged.filter((f) => ((f.riskScore as number) || 0) >= 70).slice(0, 20);
  const now = new Date().toISOString();

  const sarSection = isSAR
    ? `
    <div class="section" style="border-left:4px solid #dc2626; padding-left:16px; margin:24px 0;">
      <h2 style="color:#dc2626;">SUSPICIOUS ACTIVITY REPORT (SAR)</h2>
      <table class="info-table">
        <tr><td><strong>Filing Institution</strong></td><td>AMTTP Platform — DeFi Compliance Engine</td></tr>
        <tr><td><strong>Regulatory ID</strong></td><td>AMTTP-SAR-001</td></tr>
        <tr><td><strong>Jurisdiction</strong></td><td>United Kingdom / United States</td></tr>
        <tr><td><strong>Activity Type</strong></td><td>Structuring / Layering / Unusual Transaction Patterns</td></tr>
        <tr><td><strong>Subjects Identified</strong></td><td>${suspiciousTxns.length} addresses</td></tr>
        <tr><td><strong>Total Suspicious Amount</strong></td><td>${suspiciousTxns.reduce((s, t) => s + ((t.amount as number) || (t.value as number) || 0), 0).toFixed(4)} ETH</td></tr>
      </table>
      <h3>Narrative</h3>
      <p style="background:#fef2f2; padding:12px; border-radius:8px; line-height:1.6;">
        This Suspicious Activity Report is filed pursuant to regulatory requirements under the Bank Secrecy Act (BSA)
        and UK Money Laundering Regulations. The AMTTP compliance engine identified <strong>${suspiciousTxns.length}</strong>
        transactions exhibiting patterns consistent with potential money laundering, structuring, or other suspicious
        financial activity during the period <strong>${report.periodStart}</strong> to <strong>${report.periodEnd}</strong>.
        All flagged transactions were scored by an ML risk engine (XGBoost ensemble + graph neural network) and
        cross-referenced against OFAC SDN, EU sanctions lists, and behavioral analytics. Transactions exceeding the
        risk threshold of 70 are included in this filing.
      </p>
    </div>`
    : '';

  const txRows = (isSAR ? suspiciousTxns : flagged.slice(0, 50))
    .map(
      (tx) => `
      <tr>
        <td style="font-family:monospace;font-size:12px;">${((tx.txHash || tx.hash || 'N/A') as string).slice(0, 18)}...</td>
        <td style="font-family:monospace;font-size:12px;">${((tx.from || tx.address || '') as string).slice(0, 14)}...</td>
        <td style="font-family:monospace;font-size:12px;">${((tx.to || '') as string).slice(0, 14)}...</td>
        <td>${tx.amount || tx.value || '0'}</td>
        <td>${tx.token || 'ETH'}</td>
        <td><span style="color:${((tx.riskScore as number) || 0) >= 80 ? '#dc2626' : ((tx.riskScore as number) || 0) >= 60 ? '#d97706' : '#16a34a'}; font-weight:bold;">${tx.riskScore || 0}%</span></td>
        <td>${tx.reason || tx.flagReason || ''}</td>
      </tr>`,
    )
    .join('');

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>${report.title}</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #1f2937; background: #fff; padding: 40px; max-width: 1100px; margin: 0 auto; }
    h1 { font-size: 24px; margin-bottom: 4px; }
    h2 { font-size: 18px; margin: 20px 0 12px; color: #374151; }
    h3 { font-size: 15px; margin: 16px 0 8px; color: #4b5563; }
    .header { border-bottom: 3px solid #4f46e5; padding-bottom: 16px; margin-bottom: 24px; }
    ${config.letterhead ? `.header::before { content: 'AMTTP — Anti-Money Laundering Transaction Transfer Protocol'; display: block; font-size: 11px; color: #6b7280; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 8px; }` : ''}
    ${config.watermark ? `body::after { content: '${config.watermark}'; position: fixed; top: 50%; left: 50%; transform: translate(-50%,-50%) rotate(-30deg); font-size: 100px; color: rgba(0,0,0,0.04); pointer-events: none; z-index: -1; }` : ''}
    .meta { display: flex; gap: 24px; color: #6b7280; font-size: 13px; margin-top: 8px; }
    .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 20px 0; }
    .stat-card { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; text-align: center; }
    .stat-card .value { font-size: 28px; font-weight: 700; color: #111827; }
    .stat-card .label { font-size: 12px; color: #6b7280; margin-top: 4px; }
    table { width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px; }
    th { background: #f3f4f6; text-align: left; padding: 10px 12px; border-bottom: 2px solid #d1d5db; font-weight: 600; }
    td { padding: 8px 12px; border-bottom: 1px solid #e5e7eb; }
    tr:hover { background: #f9fafb; }
    .info-table td { padding: 6px 12px; }
    .info-table td:first-child { width: 200px; color: #6b7280; }
    .footer { margin-top: 40px; padding-top: 16px; border-top: 1px solid #e5e7eb; font-size: 11px; color: #9ca3af; text-align: center; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
    .badge-sar { background: #fef2f2; color: #dc2626; border: 1px solid #fca5a5; }
    @media print { body { padding: 20px; } .no-print { display: none; } }
  </style>
</head>
<body>
  <div class="header">
    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
      <div>
        <h1>${report.title}</h1>
        ${isSAR ? '<span class="badge badge-sar">SAR FILING</span>' : ''}
      </div>
      <div style="text-align:right; font-size:12px; color:#6b7280;">
        <div>Report ID: ${report.id}</div>
        <div>Generated: ${now}</div>
      </div>
    </div>
    <div class="meta">
      <span>Period: ${report.periodStart} — ${report.periodEnd}</span>
      <span>Type: ${report.type}</span>
      <span>Format: ${report.format}</span>
    </div>
  </div>

  ${sarSection}

  <h2>Summary Statistics</h2>
  <div class="stats">
    <div class="stat-card">
      <div class="value">${totalTx.toLocaleString()}</div>
      <div class="label">Total Transactions</div>
    </div>
    <div class="stat-card">
      <div class="value" style="color:#dc2626;">${flaggedCount.toLocaleString()}</div>
      <div class="label">Flagged Transactions</div>
    </div>
    <div class="stat-card">
      <div class="value" style="color:${avgRisk >= 60 ? '#d97706' : '#16a34a'};">${avgRisk.toFixed(1)}</div>
      <div class="label">Avg Risk Score</div>
    </div>
    <div class="stat-card">
      <div class="value">${isSAR ? suspiciousTxns.length : flagged.length}</div>
      <div class="label">${isSAR ? 'SAR Subjects' : 'Flagged Addresses'}</div>
    </div>
  </div>

  <h2>${isSAR ? 'Suspicious Transactions' : 'Flagged Transactions'}</h2>
  <table>
    <thead>
      <tr>
        <th>Tx Hash</th>
        <th>From</th>
        <th>To</th>
        <th>Amount</th>
        <th>Token</th>
        <th>Risk</th>
        <th>Reason</th>
      </tr>
    </thead>
    <tbody>
      ${txRows || '<tr><td colspan="7" style="text-align:center;color:#9ca3af;">No transactions in period</td></tr>'}
    </tbody>
  </table>

  <div class="footer">
    <p>This report was generated by the AMTTP Compliance Engine. All data is sourced from on-chain transactions and ML risk scoring.</p>
    ${isSAR ? '<p style="color:#dc2626; margin-top:4px;">CONFIDENTIAL — This SAR filing contains sensitive compliance information. Disclosure is prohibited under 31 USC §5318(g)(2).</p>' : ''}
    <p style="margin-top:4px;">© ${new Date().getFullYear()} AMTTP — Anti-Money Laundering Transaction Transfer Protocol</p>
  </div>

  <script class="no-print">
    // Auto-trigger print dialog for PDF format
    ${config.format === ReportFormat.PDF ? "window.onload = () => { setTimeout(() => window.print(), 500); };" : ''}
  </script>
</body>
</html>`;
}

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

    // Fetch live data for the report content
    let stats: Record<string, unknown> = {};
    let flagged: Record<string, unknown>[] = [];
    try {
      const [statsRes, flaggedRes] = await Promise.all([
        fetch('/app-api/data/stats', { signal: AbortSignal.timeout(5000) }).then(r => r.ok ? r.json() : {}),
        fetch('/app-api/data/flagged', { signal: AbortSignal.timeout(5000) }).then(r => r.ok ? r.json() : []),
      ]);
      stats = statsRes || {};
      flagged = Array.isArray(flaggedRes) ? flaggedRes : [];
    } catch { /* proceed with empty data */ }

    const isSAR = report.type === ReportType.SAR;
    const fileName = `${report.title.replace(/[^a-zA-Z0-9]/g, '_')}_${new Date().toISOString().split('T')[0]}.${config.format.toLowerCase()}`;

    // Build report content
    let content: string;
    let mimeType: string;

    if (config.format === ReportFormat.JSON) {
      const payload = buildReportPayload(report, stats, flagged, isSAR);
      content = JSON.stringify(payload, null, 2);
      mimeType = 'application/json';
    } else if (config.format === ReportFormat.CSV) {
      content = buildCSVContent(report, flagged);
      mimeType = 'text/csv';
    } else {
      // PDF and HTML — generate rich HTML that can be printed to PDF
      content = buildHTMLReport(report, stats, flagged, isSAR, config);
      mimeType = config.format === ReportFormat.HTML ? 'text/html' : 'text/html';
    }

    // Trigger browser download
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = config.format === ReportFormat.PDF ? fileName.replace(/\.pdf$/, '.html') : fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

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
      fileSize: blob.size,
      contentHash: `0x${Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(content)))).map(b => b.toString(16).padStart(2, '0')).join('').slice(0, 16)}`,
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
