'use client';

import { useState } from 'react';
import Link from 'next/link';

interface Report {
  id: string;
  name: string;
  type: 'compliance' | 'transaction' | 'risk' | 'audit' | 'regulatory';
  description: string;
  frequency: 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'on-demand';
  lastGenerated: string;
  status: 'ready' | 'generating' | 'scheduled' | 'error';
  format: 'PDF' | 'CSV' | 'Excel';
  size?: string;
}

const mockReports: Report[] = [
  {
    id: '1',
    name: 'Daily Transaction Summary',
    type: 'transaction',
    description: 'Summary of all transactions processed in the last 24 hours',
    frequency: 'daily',
    lastGenerated: '2026-01-31 06:00:00',
    status: 'ready',
    format: 'PDF',
    size: '2.4 MB',
  },
  {
    id: '2',
    name: 'Weekly Risk Assessment',
    type: 'risk',
    description: 'ML model performance and risk score distribution analysis',
    frequency: 'weekly',
    lastGenerated: '2026-01-27 00:00:00',
    status: 'ready',
    format: 'PDF',
    size: '5.1 MB',
  },
  {
    id: '3',
    name: 'Monthly Compliance Report',
    type: 'compliance',
    description: 'AML/KYC compliance metrics, sanctions screening results',
    frequency: 'monthly',
    lastGenerated: '2026-01-01 00:00:00',
    status: 'ready',
    format: 'PDF',
    size: '12.3 MB',
  },
  {
    id: '4',
    name: 'Quarterly Regulatory Filing',
    type: 'regulatory',
    description: 'FATF Travel Rule compliance, SAR filing summary',
    frequency: 'quarterly',
    lastGenerated: '2025-12-31 00:00:00',
    status: 'ready',
    format: 'Excel',
    size: '8.7 MB',
  },
  {
    id: '5',
    name: 'Audit Trail Export',
    type: 'audit',
    description: 'Complete audit trail of all system actions',
    frequency: 'on-demand',
    lastGenerated: '2026-01-30 14:00:00',
    status: 'generating',
    format: 'CSV',
  },
];

export default function ReportsPage() {
  const [reports, setReports] = useState(mockReports);
  const [filter, setFilter] = useState<'all' | 'compliance' | 'transaction' | 'risk' | 'audit' | 'regulatory'>('all');

  const filteredReports = filter === 'all' 
    ? reports 
    : reports.filter(r => r.type === filter);

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'compliance': return 'bg-purple-500/20 text-purple-400';
      case 'transaction': return 'bg-green-500/20 text-green-400';
      case 'risk': return 'bg-red-500/20 text-red-400';
      case 'audit': return 'bg-blue-500/20 text-blue-400';
      case 'regulatory': return 'bg-orange-500/20 text-orange-400';
      default: return 'bg-slate-500/20 text-slate-400';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'ready': return 'bg-green-500/20 text-green-400';
      case 'generating': return 'bg-yellow-500/20 text-yellow-400';
      case 'scheduled': return 'bg-blue-500/20 text-blue-400';
      case 'error': return 'bg-red-500/20 text-red-400';
      default: return 'bg-slate-500/20 text-slate-400';
    }
  };

  const handleGenerate = (id: string) => {
    setReports(prev => prev.map(r => 
      r.id === id ? { ...r, status: 'generating' as const } : r
    ));
    // Simulate generation
    setTimeout(() => {
      setReports(prev => prev.map(r => 
        r.id === id ? { ...r, status: 'ready' as const, lastGenerated: new Date().toISOString() } : r
      ));
    }, 3000);
  };

  return (
    <div className="min-h-screen bg-slate-900 text-white p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <Link href="/war-room" className="text-slate-400 hover:text-white">
              ← War Room
            </Link>
          </div>
          <h1 className="text-3xl font-bold">Reports</h1>
          <p className="text-slate-400 mt-1">Generate and download compliance and analytics reports</p>
        </div>
        <button className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg flex items-center gap-2">
          <span>+ Custom Report</span>
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-2 mb-6">
        {(['all', 'compliance', 'transaction', 'risk', 'audit', 'regulatory'] as const).map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-4 py-2 rounded-lg capitalize transition-colors ${
              filter === f 
                ? 'bg-indigo-600 text-white' 
                : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {/* Reports Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredReports.map(report => (
          <div key={report.id} className="bg-slate-800 rounded-xl p-6 border border-slate-700 hover:border-slate-600 transition-colors">
            <div className="flex items-start justify-between mb-4">
              <div className="flex gap-2">
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${getTypeColor(report.type)}`}>
                  {report.type}
                </span>
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${getStatusColor(report.status)}`}>
                  {report.status}
                </span>
              </div>
              <span className="text-xs text-slate-500">{report.format}</span>
            </div>
            
            <h3 className="font-semibold mb-2">{report.name}</h3>
            <p className="text-sm text-slate-400 mb-4">{report.description}</p>
            
            <div className="flex justify-between items-center text-xs text-slate-500 mb-4">
              <span className="capitalize">{report.frequency}</span>
              <span>Last: {report.lastGenerated}</span>
            </div>
            
            <div className="flex gap-2">
              {report.status === 'ready' && (
                <>
                  <button className="flex-1 px-3 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg text-sm">
                    Download {report.size && `(${report.size})`}
                  </button>
                  <button 
                    onClick={() => handleGenerate(report.id)}
                    className="px-3 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm"
                  >
                    Regenerate
                  </button>
                </>
              )}
              {report.status === 'generating' && (
                <button disabled className="flex-1 px-3 py-2 bg-yellow-600/50 rounded-lg text-sm cursor-wait">
                  Generating...
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Scheduled Reports Section */}
      <div className="mt-8">
        <h2 className="text-xl font-semibold mb-4">Scheduled Reports</h2>
        <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
          <div className="grid grid-cols-4 gap-4">
            <div className="text-center">
              <div className="text-3xl font-bold text-green-400">5</div>
              <div className="text-sm text-slate-400">Daily</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-blue-400">3</div>
              <div className="text-sm text-slate-400">Weekly</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-purple-400">2</div>
              <div className="text-sm text-slate-400">Monthly</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-orange-400">1</div>
              <div className="text-sm text-slate-400">Quarterly</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
