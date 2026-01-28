'use client';

/**
 * Report Generator Component
 * 
 * Sprint 11: Compliance Reporting & Export System
 * 
 * Ground Truth Reference:
 * - PDF/JSON export for regulators
 * - Compliance report generation
 * - Multiple report templates
 */

import React, { useState, useEffect } from 'react';
import {
  ComplianceReport,
  ReportType,
  ReportFormat,
  ReportStatus,
  ReportTemplate,
  ExportConfig,
  getReportTypeLabel,
  getReportStatusColor,
  formatSnapshotDate,
} from '@/types/compliance-report';
import { useComplianceReports } from '@/lib/compliance-report-service';

// ═══════════════════════════════════════════════════════════════════════════════
// INTERFACES
// ═══════════════════════════════════════════════════════════════════════════════

interface ReportGeneratorProps {
  onExport?: (report: ComplianceReport) => void;
  className?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// REPORT TYPE ICON
// ═══════════════════════════════════════════════════════════════════════════════

function ReportTypeIcon({ type }: { type: ReportType }) {
  const icons: Record<ReportType, string> = {
    [ReportType.REGULATORY]: '🏛️',
    [ReportType.INCIDENT]: '⚠️',
    [ReportType.AUDIT]: '📋',
    [ReportType.TRANSACTION]: '💸',
    [ReportType.COMPLIANCE]: '✅',
    [ReportType.CUSTOM]: '📝',
  };
  
  return <span className="text-lg">{icons[type]}</span>;
}

// ═══════════════════════════════════════════════════════════════════════════════
// TEMPLATE SELECTOR
// ═══════════════════════════════════════════════════════════════════════════════

function TemplateSelector({
  templates,
  selectedId,
  onSelect,
}: {
  templates: ReportTemplate[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {templates.map(template => (
        <div
          key={template.id}
          className={`p-4 bg-slate-800 border rounded-lg cursor-pointer transition-all hover:border-cyan-500/50 ${
            selectedId === template.id
              ? 'border-cyan-400 ring-1 ring-cyan-400/30'
              : 'border-slate-700'
          }`}
          onClick={() => onSelect(template.id)}
        >
          <div className="flex items-center gap-2 mb-2">
            <ReportTypeIcon type={template.type} />
            <h4 className="font-medium text-white">{template.name}</h4>
          </div>
          <p className="text-sm text-slate-400 mb-3">{template.description}</p>
          <div className="flex flex-wrap gap-1">
            {template.sections.map(section => (
              <span key={section} className="px-2 py-0.5 bg-slate-700 rounded text-xs text-slate-300">
                {section}
              </span>
            ))}
          </div>
          {template.isDefault && (
            <div className="mt-2">
              <span className="text-xs text-cyan-400">★ Default Template</span>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// CREATE REPORT MODAL
// ═══════════════════════════════════════════════════════════════════════════════

function CreateReportModal({
  templates,
  onClose,
  onCreate,
}: {
  templates: ReportTemplate[];
  onClose: () => void;
  onCreate: (title: string, type: ReportType, templateId: string, startDate: string, endDate: string) => void;
}) {
  const [title, setTitle] = useState('');
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>(
    templates.find(t => t.isDefault)?.id || templates[0]?.id || ''
  );
  const [startDate, setStartDate] = useState(
    new Date(Date.now() - 86400000).toISOString().slice(0, 16)
  );
  const [endDate, setEndDate] = useState(
    new Date().toISOString().slice(0, 16)
  );
  
  const selectedTemplate = templates.find(t => t.id === selectedTemplateId);
  
  const handleCreate = () => {
    if (!title || !selectedTemplateId || !selectedTemplate) return;
    onCreate(
      title,
      selectedTemplate.type,
      selectedTemplateId,
      new Date(startDate).toISOString(),
      new Date(endDate).toISOString()
    );
    onClose();
  };
  
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-2xl max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="p-4 border-b border-slate-700 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-white">Create New Report</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        
        {/* Content */}
        <div className="p-6 overflow-y-auto max-h-[calc(90vh-140px)] space-y-6">
          {/* Title */}
          <div>
            <label className="block text-sm text-slate-400 mb-2">Report Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g., Daily Compliance Report - January 21, 2025"
              className="w-full px-4 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500"
            />
          </div>
          
          {/* Date Range */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-slate-400 mb-2">Start Date</label>
              <input
                type="datetime-local"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full px-4 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white"
              />
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-2">End Date</label>
              <input
                type="datetime-local"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full px-4 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white"
              />
            </div>
          </div>
          
          {/* Template Selection */}
          <div>
            <label className="block text-sm text-slate-400 mb-2">Select Template</label>
            <TemplateSelector
              templates={templates}
              selectedId={selectedTemplateId}
              onSelect={setSelectedTemplateId}
            />
          </div>
        </div>
        
        {/* Footer */}
        <div className="p-4 border-t border-slate-700 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-slate-400 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleCreate}
            disabled={!title || !selectedTemplateId}
            className="px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Create Report
          </button>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// EXPORT MODAL
// ═══════════════════════════════════════════════════════════════════════════════

function ExportModal({
  report,
  onClose,
  onExport,
  isExporting,
}: {
  report: ComplianceReport;
  onClose: () => void;
  onExport: (config: ExportConfig) => void;
  isExporting: boolean;
}) {
  const [config, setConfig] = useState<ExportConfig>({
    format: report.format,
    includeSnapshots: true,
    includeEvidence: true,
    includeAuditLogs: true,
    includeChainData: true,
    includeSignatures: true,
    letterhead: true,
    digitalSignature: false,
  });
  
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-lg">
        {/* Header */}
        <div className="p-4 border-b border-slate-700 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-white">Export Report</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        
        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Format Selection */}
          <div>
            <label className="block text-sm text-slate-400 mb-2">Export Format</label>
            <div className="grid grid-cols-4 gap-2">
              {Object.values(ReportFormat).map(format => (
                <button
                  key={format}
                  onClick={() => setConfig({ ...config, format })}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    config.format === format
                      ? 'bg-cyan-600 text-white'
                      : 'bg-slate-800 text-slate-400 hover:text-white'
                  }`}
                >
                  {format}
                </button>
              ))}
            </div>
          </div>
          
          {/* Include Options */}
          <div>
            <label className="block text-sm text-slate-400 mb-2">Include Data</label>
            <div className="space-y-2">
              {[
                { key: 'includeSnapshots', label: 'UI Snapshots' },
                { key: 'includeEvidence', label: 'Evidence Chain' },
                { key: 'includeAuditLogs', label: 'Audit Logs' },
                { key: 'includeChainData', label: 'On-Chain Data' },
                { key: 'includeSignatures', label: 'Signatures' },
              ].map(({ key, label }) => (
                <label key={key} className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config[key as keyof ExportConfig] as boolean}
                    onChange={(e) => setConfig({ ...config, [key]: e.target.checked })}
                    className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-cyan-600 focus:ring-cyan-600"
                  />
                  <span className="text-sm text-white">{label}</span>
                </label>
              ))}
            </div>
          </div>
          
          {/* PDF Options */}
          {config.format === ReportFormat.PDF && (
            <div>
              <label className="block text-sm text-slate-400 mb-2">PDF Options</label>
              <div className="space-y-2">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config.letterhead}
                    onChange={(e) => setConfig({ ...config, letterhead: e.target.checked })}
                    className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-cyan-600 focus:ring-cyan-600"
                  />
                  <span className="text-sm text-white">Include Letterhead</span>
                </label>
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config.digitalSignature}
                    onChange={(e) => setConfig({ ...config, digitalSignature: e.target.checked })}
                    className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-cyan-600 focus:ring-cyan-600"
                  />
                  <span className="text-sm text-white">Apply Digital Signature</span>
                </label>
              </div>
            </div>
          )}
        </div>
        
        {/* Footer */}
        <div className="p-4 border-t border-slate-700 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-slate-400 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => onExport(config)}
            disabled={isExporting}
            className="px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 disabled:opacity-50 flex items-center gap-2 transition-colors"
          >
            {isExporting ? (
              <>
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Exporting...
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                Export {config.format}
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// REPORT CARD
// ═══════════════════════════════════════════════════════════════════════════════

function ReportCard({
  report,
  onView,
  onExport,
}: {
  report: ComplianceReport;
  onView: () => void;
  onExport: () => void;
}) {
  return (
    <div className="p-4 bg-slate-800 border border-slate-700 rounded-lg hover:border-slate-600 transition-colors">
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <ReportTypeIcon type={report.type} />
          <div>
            <h4 className="font-medium text-white">{report.title}</h4>
            <p className="text-xs text-slate-400">{getReportTypeLabel(report.type)}</p>
          </div>
        </div>
        <div className={`px-2 py-1 rounded text-xs font-medium ${
          report.status === ReportStatus.READY || report.status === ReportStatus.EXPORTED
            ? 'bg-green-900/50 text-green-400 border border-green-600/30'
            : report.status === ReportStatus.GENERATING
            ? 'bg-cyan-900/50 text-cyan-400 border border-cyan-600/30'
            : report.status === ReportStatus.ERROR
            ? 'bg-red-900/50 text-red-400 border border-red-600/30'
            : 'bg-slate-700 text-slate-400 border border-slate-600'
        }`}>
          {report.status === ReportStatus.GENERATING && (
            <svg className="w-3 h-3 animate-spin inline mr-1" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          )}
          {report.status}
        </div>
      </div>
      
      {/* Period */}
      <div className="flex items-center gap-2 mb-3 text-xs text-slate-400">
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
        <span>{formatSnapshotDate(report.periodStart)} – {formatSnapshotDate(report.periodEnd)}</span>
      </div>
      
      {/* Summary Stats */}
      <div className="grid grid-cols-4 gap-2 mb-3">
        <div className="p-2 bg-slate-900 rounded text-center">
          <p className="text-lg font-bold text-white">{report.summary.totalTransactions.toLocaleString()}</p>
          <p className="text-xs text-slate-500">Transactions</p>
        </div>
        <div className="p-2 bg-slate-900 rounded text-center">
          <p className="text-lg font-bold text-white">{report.summary.totalSnapshots.toLocaleString()}</p>
          <p className="text-xs text-slate-500">Snapshots</p>
        </div>
        <div className="p-2 bg-slate-900 rounded text-center">
          <p className="text-lg font-bold text-white">{report.summary.complianceScore.toFixed(1)}%</p>
          <p className="text-xs text-slate-500">Compliance</p>
        </div>
        <div className="p-2 bg-slate-900 rounded text-center">
          <p className="text-lg font-bold text-white">{report.summary.integrityScore.toFixed(1)}%</p>
          <p className="text-xs text-slate-500">Integrity</p>
        </div>
      </div>
      
      {/* Risk Distribution */}
      <div className="mb-3">
        <div className="flex h-2 rounded overflow-hidden">
          <div 
            className="bg-red-500" 
            style={{ width: `${(report.summary.riskDistribution.high / report.summary.totalTransactions * 100)}%` }} 
          />
          <div 
            className="bg-yellow-500" 
            style={{ width: `${(report.summary.riskDistribution.medium / report.summary.totalTransactions * 100)}%` }} 
          />
          <div 
            className="bg-green-500" 
            style={{ width: `${(report.summary.riskDistribution.low / report.summary.totalTransactions * 100)}%` }} 
          />
        </div>
        <div className="flex justify-between mt-1 text-xs">
          <span className="text-red-400">{report.summary.riskDistribution.high} High</span>
          <span className="text-yellow-400">{report.summary.riskDistribution.medium} Medium</span>
          <span className="text-green-400">{report.summary.riskDistribution.low} Low</span>
        </div>
      </div>
      
      {/* Metadata */}
      <div className="flex items-center justify-between text-xs text-slate-500 mb-3">
        <span>Created: {formatSnapshotDate(report.createdAt)}</span>
        <span>{report.exportCount} export{report.exportCount !== 1 ? 's' : ''}</span>
      </div>
      
      {/* Actions */}
      <div className="flex gap-2">
        <button
          onClick={onView}
          className="flex-1 px-3 py-2 bg-slate-700 text-slate-300 rounded hover:bg-slate-600 text-sm transition-colors"
        >
          View Details
        </button>
        <button
          onClick={onExport}
          disabled={report.status !== ReportStatus.READY && report.status !== ReportStatus.EXPORTED}
          className="flex-1 px-3 py-2 bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed text-sm flex items-center justify-center gap-2 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          Export
        </button>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function ReportGenerator({
  onExport,
  className = '',
}: ReportGeneratorProps) {
  const {
    reports,
    templates,
    isLoading,
    isExporting,
    fetchReports,
    createReport,
    exportReport,
  } = useComplianceReports();
  
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [exportingReport, setExportingReport] = useState<ComplianceReport | null>(null);
  const [filterType, setFilterType] = useState<ReportType | 'ALL'>('ALL');
  
  // Load reports
  useEffect(() => {
    fetchReports();
  }, [fetchReports]);
  
  // Filter reports
  const filteredReports = reports.filter(r => 
    filterType === 'ALL' || r.type === filterType
  );
  
  const handleCreate = async (
    title: string,
    type: ReportType,
    templateId: string,
    startDate: string,
    endDate: string
  ) => {
    await createReport(title, type, templateId, startDate, endDate);
  };
  
  const handleExport = async (config: ExportConfig) => {
    if (!exportingReport) return;
    const result = await exportReport(exportingReport.id, config);
    if (result.success) {
      onExport?.(exportingReport);
      // In real implementation, trigger download
      console.log('Download URL:', result.downloadUrl);
    }
    setExportingReport(null);
  };
  
  return (
    <div className={`flex flex-col h-full ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2 mb-1">
            <span className="text-2xl">📊</span>
            Report Generator
          </h2>
          <p className="text-sm text-slate-400">
            Generate and export compliance reports for regulators
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 flex items-center gap-2 transition-colors"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Report
        </button>
      </div>
      
      {/* Filter */}
      <div className="mb-4">
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value as ReportType | 'ALL')}
          className="px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white text-sm"
        >
          <option value="ALL">All Report Types</option>
          {Object.values(ReportType).map(type => (
            <option key={type} value={type}>{getReportTypeLabel(type)}</option>
          ))}
        </select>
      </div>
      
      {/* Reports Grid */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <svg className="w-8 h-8 animate-spin text-cyan-400 mx-auto mb-2" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <p className="text-slate-400">Loading reports...</p>
            </div>
          </div>
        ) : filteredReports.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <p className="text-slate-400 mb-2">No reports found</p>
              <button
                onClick={() => setShowCreateModal(true)}
                className="text-sm text-cyan-400 hover:text-cyan-300"
              >
                Create your first report
              </button>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {filteredReports.map(report => (
              <ReportCard
                key={report.id}
                report={report}
                onView={() => {}}
                onExport={() => setExportingReport(report)}
              />
            ))}
          </div>
        )}
      </div>
      
      {/* Modals */}
      {showCreateModal && (
        <CreateReportModal
          templates={templates}
          onClose={() => setShowCreateModal(false)}
          onCreate={handleCreate}
        />
      )}
      
      {exportingReport && (
        <ExportModal
          report={exportingReport}
          onClose={() => setExportingReport(null)}
          onExport={handleExport}
          isExporting={isExporting}
        />
      )}
    </div>
  );
}
