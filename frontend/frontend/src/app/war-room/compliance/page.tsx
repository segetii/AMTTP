'use client';

/**
 * War Room - Compliance Reports Page
 * 
 * Sprint 11: Compliance Reporting & Export System
 * 
 * Ground Truth Reference:
 * - PDF/JSON export for regulators
 * - Snapshot explorer for audit replay
 * - Evidence linking for complete audit trails
 * - Chain replay tool for UI state reconstruction
 */

import React, { useState } from 'react';
import {
  SnapshotExplorer,
  EvidenceChain,
  ReportGenerator,
  ChainReplayTool,
} from '@/components/compliance';
import { UISnapshot, Evidence, ComplianceReport } from '@/types/compliance-report';

// ═══════════════════════════════════════════════════════════════════════════════
// VIEW TABS
// ═══════════════════════════════════════════════════════════════════════════════

type ViewTab = 'reports' | 'snapshots' | 'evidence' | 'replay';

const tabs: { id: ViewTab; label: string; icon: string; description: string }[] = [
  { id: 'reports', label: 'Reports', icon: '📊', description: 'Generate and export compliance reports' },
  { id: 'snapshots', label: 'Snapshots', icon: '📸', description: 'Browse and verify UI snapshots' },
  { id: 'evidence', label: 'Evidence', icon: '🔗', description: 'View linked evidence chains' },
  { id: 'replay', label: 'Replay', icon: '🔄', description: 'Replay UI state from snapshots' },
];

// ═══════════════════════════════════════════════════════════════════════════════
// STATS PANEL
// ═══════════════════════════════════════════════════════════════════════════════

function StatsPanel() {
  const stats = [
    { label: 'Total Reports', value: '47', change: '+3 this week', positive: true },
    { label: 'Snapshots Today', value: '1,284', change: '+12% vs yesterday', positive: true },
    { label: 'Evidence Items', value: '892', change: '156 pending', positive: false },
    { label: 'Integrity Score', value: '99.8%', change: 'All verified', positive: true },
  ];
  
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      {stats.map(stat => (
        <div key={stat.label} className="p-4 bg-slate-800 border border-slate-700 rounded-lg">
          <p className="text-xs text-slate-400 mb-1">{stat.label}</p>
          <p className="text-2xl font-bold text-white mb-1">{stat.value}</p>
          <p className={`text-xs ${stat.positive ? 'text-green-400' : 'text-yellow-400'}`}>
            {stat.change}
          </p>
        </div>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// QUICK ACTIONS
// ═══════════════════════════════════════════════════════════════════════════════

function QuickActions({ onAction }: { onAction: (action: string) => void }) {
  const actions = [
    { id: 'daily-report', label: 'Generate Daily Report', icon: '📋' },
    { id: 'verify-all', label: 'Verify All Pending', icon: '✓' },
    { id: 'export-audit', label: 'Export Audit Package', icon: '📦' },
    { id: 'investigate', label: 'Start Investigation', icon: '🔍' },
  ];
  
  return (
    <div className="flex flex-wrap gap-2 mb-6">
      {actions.map(action => (
        <button
          key={action.id}
          onClick={() => onAction(action.id)}
          className="px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-300 hover:bg-slate-700 hover:text-white flex items-center gap-2 transition-colors"
        >
          <span>{action.icon}</span>
          {action.label}
        </button>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ═══════════════════════════════════════════════════════════════════════════════

export default function ComplianceReportsPage() {
  const [activeTab, setActiveTab] = useState<ViewTab>('reports');
  const [selectedSnapshot, setSelectedSnapshot] = useState<UISnapshot | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<Evidence | null>(null);
  
  const handleQuickAction = (action: string) => {
    switch (action) {
      case 'daily-report':
        setActiveTab('reports');
        break;
      case 'verify-all':
        setActiveTab('snapshots');
        break;
      case 'export-audit':
        setActiveTab('reports');
        break;
      case 'investigate':
        setActiveTab('replay');
        break;
    }
  };
  
  const handleSnapshotSelect = (snapshot: UISnapshot) => {
    setSelectedSnapshot(snapshot);
  };
  
  const handleEvidenceSelect = (evidence: Evidence) => {
    setSelectedEvidence(evidence);
  };
  
  const handleReportExport = (report: ComplianceReport) => {
    console.log('Exported report:', report.title);
  };
  
  return (
    <div className="min-h-screen bg-slate-900 text-white p-6">
      {/* Header */}
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-white flex items-center gap-3 mb-2">
          <span className="text-3xl">📊</span>
          Compliance Reports
        </h1>
        <p className="text-slate-400">
          Generate reports, explore snapshots, and verify evidence for regulatory compliance
        </p>
      </header>
      
      {/* Stats */}
      <StatsPanel />
      
      {/* Quick Actions */}
      <QuickActions onAction={handleQuickAction} />
      
      {/* Tab Navigation */}
      <div className="flex gap-1 p-1 bg-slate-800 rounded-xl mb-6">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 px-4 py-3 rounded-lg text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'bg-cyan-600 text-white'
                : 'text-slate-400 hover:text-white hover:bg-slate-700'
            }`}
          >
            <span className="mr-2">{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </div>
      
      {/* Tab Description */}
      <div className="mb-4 p-3 bg-slate-800/50 border border-slate-700 rounded-lg">
        <p className="text-sm text-slate-400">
          {tabs.find(t => t.id === activeTab)?.icon}{' '}
          {tabs.find(t => t.id === activeTab)?.description}
        </p>
      </div>
      
      {/* Tab Content */}
      <div className="min-h-[600px]">
        {activeTab === 'reports' && (
          <ReportGenerator onExport={handleReportExport} />
        )}
        
        {activeTab === 'snapshots' && (
          <SnapshotExplorer onSelectSnapshot={handleSnapshotSelect} />
        )}
        
        {activeTab === 'evidence' && (
          <EvidenceChain
            focusId={selectedSnapshot?.id}
            focusType={selectedSnapshot ? 'snapshot' : undefined}
            onSelectEvidence={handleEvidenceSelect}
          />
        )}
        
        {activeTab === 'replay' && (
          <ChainReplayTool
            initialTransactionId={selectedSnapshot?.transactionContext?.transactionId}
            onSnapshotSelect={handleSnapshotSelect}
          />
        )}
      </div>
      
      {/* Footer Info */}
      <footer className="mt-6 pt-6 border-t border-slate-700">
        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>
            Sprint 11: Compliance Reporting & Export System
          </span>
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 bg-green-500 rounded-full" />
              All systems operational
            </span>
            <span>
              Last sync: {new Date().toLocaleTimeString()}
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}
