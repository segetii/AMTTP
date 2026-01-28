'use client';

/**
 * War Room - Audit Log Page
 * 
 * Sprint 9: Audit Trail & Logging
 * 
 * Ground Truth Reference:
 * - Full audit visibility for compliance
 * - Hash-linked integrity verification
 * - Export capability for regulators
 */

import React, { useState, useEffect } from 'react';
import { useAudit } from '@/lib/audit-service';
import { AuditEventList, AuditTrailViewer, AuditStatsPanel } from '@/components/audit';
import { AuditEvent, AuditTrail, AuditStats, AuditReport } from '@/types/audit';

// ═══════════════════════════════════════════════════════════════════════════════
// VIEW TABS
// ═══════════════════════════════════════════════════════════════════════════════

type ViewTab = 'events' | 'trail' | 'reports';

// ═══════════════════════════════════════════════════════════════════════════════
// INTEGRITY BADGE
// ═══════════════════════════════════════════════════════════════════════════════

function IntegrityBadge({ isVerifying, isValid }: { isVerifying: boolean; isValid: boolean | null }) {
  if (isVerifying) {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-800 border border-slate-600 rounded-lg">
        <svg className="w-4 h-4 animate-spin text-cyan-400" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <span className="text-sm text-slate-400">Verifying...</span>
      </div>
    );
  }
  
  if (isValid === null) {
    return null;
  }
  
  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border ${
      isValid 
        ? 'bg-green-900/30 border-green-600/30 text-green-400' 
        : 'bg-red-900/30 border-red-600/30 text-red-400'
    }`}>
      {isValid ? (
        <>
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
          <span className="text-sm">Chain Verified</span>
        </>
      ) : (
        <>
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span className="text-sm">Integrity Error</span>
        </>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ═══════════════════════════════════════════════════════════════════════════════

export default function AuditPage() {
  const {
    events,
    isLoading,
    getAuditTrail,
    getStats,
    generateReport,
    verifyIntegrity,
  } = useAudit();
  
  const [activeTab, setActiveTab] = useState<ViewTab>('events');
  const [selectedEvent, setSelectedEvent] = useState<AuditEvent | null>(null);
  const [auditTrail, setAuditTrail] = useState<AuditTrail | null>(null);
  const [stats, setStats] = useState<AuditStats | null>(null);
  const [integrityValid, setIntegrityValid] = useState<boolean | null>(null);
  const [isVerifying, setIsVerifying] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  
  // Load stats
  useEffect(() => {
    const loadStats = async () => {
      const now = Date.now();
      const dayAgo = now - 24 * 60 * 60 * 1000;
      const statsData = await getStats(dayAgo, now);
      setStats(statsData);
    };
    loadStats();
  }, [getStats, events]);
  
  // Load trail when event selected
  const handleEventSelect = async (event: AuditEvent) => {
    setSelectedEvent(event);
    const trail = await getAuditTrail(event.resourceType, event.resourceId);
    setAuditTrail(trail);
  };
  
  // Verify integrity
  const handleVerifyIntegrity = async () => {
    setIsVerifying(true);
    const result = await verifyIntegrity();
    setIntegrityValid(result.valid);
    setIsVerifying(false);
  };
  
  // Export report
  const handleExport = async (format: 'JSON' | 'CSV' | 'PDF') => {
    setIsExporting(true);
    const now = Date.now();
    const dayAgo = now - 24 * 60 * 60 * 1000;
    const report = await generateReport('Daily Audit Report', dayAgo, now, format);
    
    // Download JSON
    if (format === 'JSON') {
      const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit-report-${new Date().toISOString().split('T')[0]}.json`;
      a.click();
    }
    
    setIsExporting(false);
  };
  
  return (
    <div className="min-h-screen bg-slate-900 text-white p-6">
      {/* Header */}
      <header className="mb-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-3">
              <span className="text-3xl">📋</span>
              Audit Log
            </h1>
            <p className="text-slate-400">Complete audit trail and compliance evidence</p>
          </div>
          
          <div className="flex items-center gap-3">
            <IntegrityBadge isVerifying={isVerifying} isValid={integrityValid} />
            <button
              onClick={handleVerifyIntegrity}
              disabled={isVerifying}
              className="px-4 py-2 text-sm bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 disabled:opacity-50"
            >
              Verify Chain
            </button>
            <div className="relative group">
              <button
                disabled={isExporting}
                className="px-4 py-2 text-sm bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 disabled:opacity-50 flex items-center gap-2"
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
                    Export
                  </>
                )}
              </button>
              <div className="absolute right-0 mt-1 w-32 bg-slate-800 border border-slate-700 rounded-lg shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10">
                <button
                  onClick={() => handleExport('JSON')}
                  className="w-full px-4 py-2 text-left text-sm text-slate-300 hover:bg-slate-700 rounded-t-lg"
                >
                  JSON
                </button>
                <button
                  onClick={() => handleExport('CSV')}
                  className="w-full px-4 py-2 text-left text-sm text-slate-300 hover:bg-slate-700"
                >
                  CSV
                </button>
                <button
                  onClick={() => handleExport('PDF')}
                  className="w-full px-4 py-2 text-left text-sm text-slate-300 hover:bg-slate-700 rounded-b-lg"
                >
                  PDF
                </button>
              </div>
            </div>
          </div>
        </div>
        
        {/* Tabs */}
        <div className="flex gap-1 border-b border-slate-700 pb-4">
          <button
            onClick={() => setActiveTab('events')}
            className={`px-4 py-2 rounded-t-lg text-sm font-medium transition-colors
              ${activeTab === 'events'
                ? 'bg-slate-800 text-white'
                : 'text-slate-400 hover:text-white'}`}
          >
            📝 Events
          </button>
          <button
            onClick={() => setActiveTab('trail')}
            className={`px-4 py-2 rounded-t-lg text-sm font-medium transition-colors
              ${activeTab === 'trail'
                ? 'bg-slate-800 text-white'
                : 'text-slate-400 hover:text-white'}`}
          >
            🔗 Trail View
          </button>
          <button
            onClick={() => setActiveTab('reports')}
            className={`px-4 py-2 rounded-t-lg text-sm font-medium transition-colors
              ${activeTab === 'reports'
                ? 'bg-slate-800 text-white'
                : 'text-slate-400 hover:text-white'}`}
          >
            📊 Statistics
          </button>
        </div>
      </header>
      
      {/* Content */}
      {activeTab === 'events' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <AuditEventList
              events={events}
              onEventSelect={handleEventSelect}
              selectedEventId={selectedEvent?.id}
              isLoading={isLoading}
            />
          </div>
          <div className="lg:col-span-1">
            {selectedEvent ? (
              <div className="bg-slate-800/30 rounded-lg border border-slate-700 p-4">
                <h3 className="text-lg font-medium text-white mb-4">Event Details</h3>
                <div className="space-y-3 text-sm">
                  <div>
                    <span className="text-slate-500">ID:</span>
                    <span className="text-slate-300 ml-2 font-mono">{selectedEvent.id}</span>
                  </div>
                  <div>
                    <span className="text-slate-500">Timestamp:</span>
                    <span className="text-slate-300 ml-2">{new Date(selectedEvent.timestamp).toLocaleString()}</span>
                  </div>
                  <div>
                    <span className="text-slate-500">Category:</span>
                    <span className="text-slate-300 ml-2">{selectedEvent.category}</span>
                  </div>
                  <div>
                    <span className="text-slate-500">Action:</span>
                    <span className="text-slate-300 ml-2">{selectedEvent.action}</span>
                  </div>
                  <div>
                    <span className="text-slate-500">Severity:</span>
                    <span className="text-slate-300 ml-2">{selectedEvent.severity}</span>
                  </div>
                  <div>
                    <span className="text-slate-500">Actor:</span>
                    <span className="text-slate-300 ml-2">{selectedEvent.actorType} ({selectedEvent.actorId})</span>
                  </div>
                  <div>
                    <span className="text-slate-500">Resource:</span>
                    <span className="text-slate-300 ml-2">{selectedEvent.resourceType}:{selectedEvent.resourceId}</span>
                  </div>
                  <div>
                    <span className="text-slate-500">Success:</span>
                    <span className={`ml-2 ${selectedEvent.success ? 'text-green-400' : 'text-red-400'}`}>
                      {selectedEvent.success ? 'Yes' : 'No'}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500">Hash:</span>
                    <span className="text-slate-300 ml-2 font-mono text-xs">{selectedEvent.hash}</span>
                  </div>
                  {selectedEvent.metadata && Object.keys(selectedEvent.metadata).length > 0 && (
                    <div>
                      <span className="text-slate-500 block mb-1">Metadata:</span>
                      <pre className="bg-slate-900 rounded p-2 text-xs overflow-auto">
                        {JSON.stringify(selectedEvent.metadata, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="bg-slate-800/30 rounded-lg border border-slate-700 p-8 text-center">
                <p className="text-slate-500">Select an event to view details</p>
              </div>
            )}
          </div>
        </div>
      )}
      
      {activeTab === 'trail' && (
        <AuditTrailViewer
          trail={auditTrail}
          isLoading={isLoading}
          onClose={() => setAuditTrail(null)}
        />
      )}
      
      {activeTab === 'reports' && (
        <AuditStatsPanel stats={stats} isLoading={isLoading} />
      )}
    </div>
  );
}
