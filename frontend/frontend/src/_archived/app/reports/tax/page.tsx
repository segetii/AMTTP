'use client';

import React, { useState, useEffect } from 'react';
import AppLayout from '@/components/AppLayout';

interface TaxReport {
  id: string;
  period: string;
  type: string;
  status: 'completed' | 'pending' | 'draft';
  totalTransactions: number;
  taxableAmount: string;
  generatedAt: string;
}

const sampleReports: TaxReport[] = [
  { id: 'TR-2024-Q4', period: '2024 Q4', type: 'Quarterly Summary', status: 'completed', totalTransactions: 847, taxableAmount: '$2,340,000', generatedAt: '2025-01-05' },
  { id: 'TR-2024-Q3', period: '2024 Q3', type: 'Quarterly Summary', status: 'completed', totalTransactions: 1203, taxableAmount: '$3,120,000', generatedAt: '2024-10-02' },
  { id: 'TR-2024-Q2', period: '2024 Q2', type: 'Quarterly Summary', status: 'completed', totalTransactions: 965, taxableAmount: '$1,870,000', generatedAt: '2024-07-03' },
  { id: 'TR-2024-Q1', period: '2024 Q1', type: 'Quarterly Summary', status: 'completed', totalTransactions: 1102, taxableAmount: '$2,890,000', generatedAt: '2024-04-01' },
  { id: 'TR-2024-ANNUAL', period: '2024 Annual', type: 'Annual Tax Summary', status: 'pending', totalTransactions: 4117, taxableAmount: '$10,220,000', generatedAt: '-' },
];

function TaxReportsContent() {
  const [reports, setReports] = useState<TaxReport[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Simulate fetching tax reports
    const timer = setTimeout(() => {
      setReports(sampleReports);
      setLoading(false);
    }, 800);
    return () => clearTimeout(timer);
  }, []);

  const statusColors: Record<string, string> = {
    completed: 'bg-emerald-500/20 text-emerald-400',
    pending: 'bg-amber-500/20 text-amber-400',
    draft: 'bg-slate-500/20 text-slate-400',
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Tax Reports</h1>
          <p className="text-slate-400 mt-1">Generate and manage tax documentation for your digital asset portfolio</p>
        </div>
        <button className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors font-medium">
          Generate Report
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-4">
          <p className="text-sm text-slate-400">Total Taxable Amount (2024)</p>
          <p className="text-2xl font-bold text-white mt-1">$10,220,000</p>
        </div>
        <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-4">
          <p className="text-sm text-slate-400">Total Transactions</p>
          <p className="text-2xl font-bold text-white mt-1">4,117</p>
        </div>
        <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-4">
          <p className="text-sm text-slate-400">Reports Generated</p>
          <p className="text-2xl font-bold text-white mt-1">4</p>
        </div>
      </div>

      {/* Reports Table */}
      <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-700/50">
          <h2 className="font-semibold text-white">Report History</h2>
        </div>
        {loading ? (
          <div className="p-8 text-center text-slate-400">Loading tax reports...</div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="text-left text-xs text-slate-400 uppercase tracking-wider border-b border-slate-700/50">
                <th className="px-6 py-3">Report ID</th>
                <th className="px-6 py-3">Period</th>
                <th className="px-6 py-3">Type</th>
                <th className="px-6 py-3">Transactions</th>
                <th className="px-6 py-3">Taxable Amount</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3">Generated</th>
                <th className="px-6 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/50">
              {reports.map((report) => (
                <tr key={report.id} className="hover:bg-slate-700/30 transition-colors">
                  <td className="px-6 py-4 text-sm font-mono text-indigo-400">{report.id}</td>
                  <td className="px-6 py-4 text-sm text-white">{report.period}</td>
                  <td className="px-6 py-4 text-sm text-slate-300">{report.type}</td>
                  <td className="px-6 py-4 text-sm text-slate-300">{report.totalTransactions.toLocaleString()}</td>
                  <td className="px-6 py-4 text-sm font-medium text-white">{report.taxableAmount}</td>
                  <td className="px-6 py-4">
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${statusColors[report.status]}`}>
                      {report.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-slate-400">{report.generatedAt}</td>
                  <td className="px-6 py-4">
                    {report.status === 'completed' ? (
                      <button className="text-sm text-indigo-400 hover:text-indigo-300 font-medium">Download</button>
                    ) : (
                      <button className="text-sm text-amber-400 hover:text-amber-300 font-medium">Generate</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default function TaxReportsPage() {
  return (
    <AppLayout>
      <TaxReportsContent />
    </AppLayout>
  );
}
